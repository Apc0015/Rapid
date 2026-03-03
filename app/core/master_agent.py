"""
Master Agent — Brain 2

Orchestrates RAG and DB tracks in parallel.
Receives only NL summaries from each track.
Never sees raw data, schema, or governance rules.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any

from app.core.confidence import ConfidenceScorer, ConfidenceResult, HIGH_CONFIDENCE
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class TrackResult:
    track: str                  # "rag" | "db" | "web"
    nl_summary: str             # NL paragraph — the only data field
    sources: list               # source citation objects
    confidence: float
    activated: bool
    error: Optional[str] = None
    # NOTE: No raw data fields — structural privacy guarantee


@dataclass
class FusionResult:
    fused_nl_summary: str
    all_sources: list
    overall_confidence: float
    confidence_result: Optional[ConfidenceResult]
    tracks_activated: List[str]
    # NOTE: No raw data fields — structural privacy guarantee


class MasterAgent:
    """
    Brain 2 — orchestrates RAG + DB tracks and fuses NL summaries.

    The master agent never receives raw data from either track.
    It only receives NL paragraphs (the output of R4 and D5).
    """

    def __init__(
        self,
        rag_track,           # RAGTrack instance
        db_master,           # DBMasterAgent instance
        web_agent,           # WebSearchAgent instance
        confidence_scorer: ConfidenceScorer,
        llm_manager: LLMManager,
    ):
        self.rag = rag_track
        self.db = db_master
        self.web = web_agent
        self.scorer = confidence_scorer
        self.llm = llm_manager

    async def run(
        self,
        raw_query: str,
        tracks_needed: List[str],
        user_context,           # UserContext (username, department, role)
        conn_id: Optional[str] = None,
    ) -> FusionResult:
        """
        Run requested tracks in parallel, fuse NL summaries, score confidence.
        Fires web search if confidence < 0.65.
        """
        track_results: List[TrackResult] = []

        # Run RAG and DB in parallel
        tasks = {}
        if "rag" in tracks_needed or "both" in tracks_needed:
            tasks["rag"] = self._run_rag_track(raw_query)
        if "db" in tracks_needed or "both" in tracks_needed:
            tasks["db"] = self._run_db_track(raw_query, user_context, conn_id)

        if tasks:
            completed = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for track_name, result in zip(tasks.keys(), completed):
                if isinstance(result, Exception):
                    logger.error("Track %s failed: %s", track_name, result)
                    track_results.append(TrackResult(
                        track=track_name, nl_summary="", sources=[],
                        confidence=0.0, activated=True, error=str(result),
                    ))
                else:
                    track_results.append(result)

        # Filter to active results with content
        active_results = [
            r for r in track_results
            if r.activated and r.nl_summary and not r.error
        ]

        if not active_results:
            # General chat or no data found
            return FusionResult(
                fused_nl_summary="",
                all_sources=[],
                overall_confidence=0.0,
                confidence_result=None,
                tracks_activated=[r.track for r in track_results if r.activated],
            )

        # Fuse NL summaries
        fused = self._fuse_summaries(active_results)
        all_sources = [s for r in active_results for s in r.sources]
        avg_confidence = sum(r.confidence for r in active_results) / len(active_results)

        # Score confidence (no raw data — summaries only)
        confidence_result = await self.scorer.score(
            query=raw_query,
            summaries=[r.nl_summary for r in active_results],
            answer=fused,
            llm_manager=self.llm,
            use_llm_faithfulness=True,
        )

        # Web search fallback if below threshold
        if confidence_result.overall < HIGH_CONFIDENCE and self.web:
            logger.info(
                "Master: confidence %.2f below threshold — firing web search",
                confidence_result.overall,
            )
            web_result = await self._run_web_track(raw_query, confidence_result.overall)
            if web_result.nl_summary:
                active_results.append(web_result)
                all_sources.extend(web_result.sources)
                fused = self._fuse_summaries(active_results)
                # Re-score with web content
                confidence_result = await self.scorer.score(
                    query=raw_query,
                    summaries=[r.nl_summary for r in active_results],
                    answer=fused,
                    llm_manager=self.llm,
                    use_llm_faithfulness=False,  # avoid double LLM cost
                )

        return FusionResult(
            fused_nl_summary=fused,
            all_sources=all_sources,
            overall_confidence=confidence_result.overall,
            confidence_result=confidence_result,
            tracks_activated=[r.track for r in track_results if r.activated],
        )

    async def _run_rag_track(self, raw_query: str) -> TrackResult:
        try:
            result = await self.rag.run(raw_query)
            return TrackResult(
                track="rag",
                nl_summary=result.nl_summary,
                sources=result.sources,
                confidence=result.confidence,
                activated=True,
            )
        except Exception as e:
            logger.error("RAG track error: %s", e)
            return TrackResult(
                track="rag", nl_summary="", sources=[],
                confidence=0.0, activated=True, error=str(e),
            )

    async def _run_db_track(self, raw_query: str, user_ctx, conn_id: Optional[str]) -> TrackResult:
        try:
            result = await self.db.process(raw_query, user_ctx, conn_id)
            return TrackResult(
                track="db",
                nl_summary=result.nl_summary,
                sources=[result.sources] if result.sources else [],
                confidence=result.confidence,
                activated=result.activated,
                error=result.error,
            )
        except Exception as e:
            logger.error("DB track error: %s", e)
            return TrackResult(
                track="db", nl_summary="", sources=[],
                confidence=0.0, activated=True, error=str(e),
            )

    async def _run_web_track(self, raw_query: str, current_confidence: float) -> TrackResult:
        try:
            result = await self.web.search_and_summarize(raw_query, current_confidence)
            if result:
                return TrackResult(
                    track="web",
                    nl_summary=result.nl_summary,
                    sources=result.sources,
                    confidence=result.confidence,
                    activated=True,
                )
        except Exception as e:
            logger.warning("Web track error: %s", e)
        return TrackResult(track="web", nl_summary="", sources=[], confidence=0.0, activated=False)

    @staticmethod
    def _fuse_summaries(track_results: List[TrackResult]) -> str:
        """
        Simple NL fusion — labeled sections per track.
        No LLM call for fusion (keeps it fast and deterministic).
        """
        parts = []
        labels = {"rag": "From documents", "db": "From database", "web": "From web search"}

        for result in track_results:
            if result.nl_summary and result.activated:
                label = labels.get(result.track, result.track.upper())
                parts.append(f"{label}: {result.nl_summary}")

        return "\n\n".join(parts) if len(parts) > 1 else (parts[0] if parts else "")
