from __future__ import annotations
"""
infrastructure/pipeline_loader.py
─────────────────────────────────────────────────────────────────────────────
Loads a department's complete pipeline from its config.yaml.
Each department gets its own independent DeptPipeline instance.

  DeptPipeline.run_structured(query, context)   → StructuredResult
  DeptPipeline.run_unstructured(query, context) → UnstructuredResult
  DeptPipeline.run(query, context)              → fused AgentResult

Config drives everything:
  departments/<dept_id>/config.yaml → structured_pipeline + unstructured_pipeline
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from infrastructure.governance_engine import get_governance_engine

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class StructuredResult:
    dept_id:    str
    nl_summary: str
    sources:    list[str] = field(default_factory=list)
    confidence: float     = 1.0
    row_count:  int       = 0
    error:      str       = ""

    @property
    def ok(self) -> bool:
        return bool(self.nl_summary) and not self.error


@dataclass
class UnstructuredResult:
    dept_id:    str
    nl_summary: str
    sources:    list[str] = field(default_factory=list)
    confidence: float     = 1.0
    chunk_count: int      = 0
    error:       str      = ""

    @property
    def ok(self) -> bool:
        return bool(self.nl_summary) and not self.error


@dataclass
class PipelineResult:
    dept_id:        str
    structured:     Optional[StructuredResult]   = None
    unstructured:   Optional[UnstructuredResult] = None
    fused_summary:  str   = ""
    sources:        list[str] = field(default_factory=list)
    confidence:     float = 1.0
    error:          str   = ""

    @property
    def ok(self) -> bool:
        return bool(self.fused_summary) and not self.error


# ── Pipeline stages ───────────────────────────────────────────────────────────

class StructuredPipeline:
    """
    D1 → D2 → D3 → D4 → D5 for one department.
    Loaded entirely from config; no hardcoded dept logic here.
    """

    def __init__(self, dept_id: str, cfg: dict):
        self.dept_id = dept_id
        self.cfg     = cfg
        self._gov    = get_governance_engine()

    async def run(self, query: str, user_role: str = "employee") -> StructuredResult:
        if not self.cfg.get("enabled", False):
            return StructuredResult(dept_id=self.dept_id, nl_summary="",
                                    error="structured pipeline disabled")
        try:
            return await self._execute(query, user_role)
        except Exception as e:
            logger.error(f"[structured/{self.dept_id}] {e}")
            return StructuredResult(dept_id=self.dept_id, nl_summary="",
                                    error=str(e))

    async def _execute(self, query: str, user_role: str) -> StructuredResult:
        from infrastructure.db_master import DBMasterAgent
        schema_cfg = self.cfg.get("schema", {})
        gov_cfg    = self.cfg.get("governance", {})
        writer_cfg = self.cfg.get("sql_writer", {})

        # Build connection params from env vars defined in config
        conn_id, conn_params = self._resolve_connection(schema_cfg)
        if not conn_params:
            return StructuredResult(dept_id=self.dept_id, nl_summary="",
                                    error="no DB connection configured")

        permitted_tables = self._get_permitted_tables(schema_cfg)

        db_agent = DBMasterAgent()
        result   = await db_agent.run(
            query           = query,
            conn_id         = conn_id,
            permitted_tables = permitted_tables,
            user_role       = user_role,
            dept_id         = self.dept_id,
        )

        # Apply field-level governance on the result
        if hasattr(result, "rows") and result.rows:
            governed_rows = []
            for row in result.rows:
                governed, _ = self._gov.apply_field_rules(row, self.dept_id, user_role)
                governed_rows.append(governed)
        else:
            governed_rows = []

        nl_summary = getattr(result, "nl_summary", "") or getattr(result, "answer", "")
        sources    = getattr(result, "sources", [])

        return StructuredResult(
            dept_id    = self.dept_id,
            nl_summary = nl_summary,
            sources    = sources,
            confidence = getattr(result, "confidence", 0.8),
            row_count  = len(governed_rows),
        )

    def _resolve_connection(self, schema_cfg: dict) -> tuple[str, dict]:
        """Read DB connection params from env vars specified in config."""
        databases = schema_cfg.get("databases", {})
        for db_name, db_cfg in databases.items():
            params = {
                "type":     db_cfg.get("type", "sqlite"),
                "host":     os.getenv(db_cfg.get("host_env", ""), ""),
                "port":     os.getenv(db_cfg.get("port_env", ""), "5432"),
                "database": os.getenv(db_cfg.get("name_env", ""), ""),
                "username": os.getenv(db_cfg.get("user_env", ""), ""),
                "password": os.getenv(db_cfg.get("pass_env", ""), ""),
                "ssl":      db_cfg.get("ssl", False),
            }
            if params["host"] or params["type"] == "sqlite":
                return db_name, params
        return "", {}

    def _get_permitted_tables(self, schema_cfg: dict) -> list[str]:
        tables = []
        for db_cfg in schema_cfg.get("databases", {}).values():
            tables.extend(db_cfg.get("permitted_tables", {}).keys())
        return tables


class UnstructuredPipeline:
    """
    R1 → R2 → R3 → R4 for one department.
    Loaded entirely from config; no hardcoded dept logic here.
    """

    def __init__(self, dept_id: str, cfg: dict):
        self.dept_id = dept_id
        self.cfg     = cfg
        self._gov    = get_governance_engine()

    async def run(self, query: str, user_role: str = "employee") -> UnstructuredResult:
        if not self.cfg.get("enabled", False):
            return UnstructuredResult(dept_id=self.dept_id, nl_summary="",
                                      error="unstructured pipeline disabled")
        try:
            return await self._execute(query, user_role)
        except Exception as e:
            logger.error(f"[unstructured/{self.dept_id}] {e}")
            return UnstructuredResult(dept_id=self.dept_id, nl_summary="",
                                      error=str(e))

    async def _execute(self, query: str, user_role: str) -> UnstructuredResult:
        from infrastructure.faiss_store import get_dept_index
        from infrastructure.embedding_service import get_embedder
        from infrastructure.llm_client import get_llm

        retriever_cfg  = self.cfg.get("retriever", {})
        summarizer_cfg = self.cfg.get("summarizer", {})
        rewriter_cfg   = self.cfg.get("rewriter",   {})

        # R2 — rewrite query with dept domain context
        rewritten_query = await self._rewrite(query, rewriter_cfg)

        # R3 — retrieve from dept FAISS index
        index     = get_dept_index(self.dept_id)
        embedder  = get_embedder()
        top_k     = retriever_cfg.get("top_k", 8)
        query_vec = await embedder.embed(rewritten_query)
        chunks    = index.search(query_vec, top_k=top_k) if index else []

        if not chunks:
            return UnstructuredResult(
                dept_id=self.dept_id, nl_summary="",
                error="no relevant documents found"
            )

        # R4 — summarize (data firewall: chunks destroyed after summary)
        llm      = get_llm()
        persona  = self._gov.get_dept_persona(self.dept_id)
        max_tkns = summarizer_cfg.get("max_summary_tokens", 500)

        chunk_texts = "\n\n---\n\n".join(
            c.get("text", "") for c in chunks[:summarizer_cfg.get("max_input_chunks", 4)]
        )
        prompt = (
            f"{persona}\n\n"
            f"Using ONLY the following document excerpts, answer the question.\n"
            f"Do NOT include raw data. Provide a concise NL summary.\n\n"
            f"QUESTION: {query}\n\n"
            f"EXCERPTS:\n{chunk_texts}"
        )
        summary = await llm.chat(prompt, max_tokens=max_tkns)

        # Redact PII from summary
        summary = self._gov.redact_pii(summary)

        sources = list({c.get("source", "") for c in chunks if c.get("source")})

        return UnstructuredResult(
            dept_id     = self.dept_id,
            nl_summary  = summary,
            sources     = sources,
            confidence  = 0.8,
            chunk_count = len(chunks),
        )

    async def _rewrite(self, query: str, cfg: dict) -> str:
        """R2 — inject domain context into the query."""
        if not cfg.get("inject_domain_context", False):
            return query
        domain_ctx = cfg.get("domain_context", "")
        abbrevs    = cfg.get("abbreviations", {})
        rewritten  = query
        for abbr, full in abbrevs.items():
            rewritten = rewritten.replace(abbr, full)
        return f"{rewritten} [Context: {domain_ctx[:200]}]" if domain_ctx else rewritten


# ── Department Pipeline ───────────────────────────────────────────────────────

class DeptPipeline:
    """
    Complete pipeline for one department.
    Loads config.yaml once; both sub-pipelines share it.
    """

    def __init__(self, dept_id: str):
        self.dept_id = dept_id
        cfg_path     = Path(f"departments/{dept_id}/config.yaml")
        full_cfg: dict = {}
        if cfg_path.exists():
            try:
                full_cfg = yaml.safe_load(cfg_path.read_text()) or {}
            except Exception as e:
                logger.error(f"[pipeline/{dept_id}] Failed to load config: {e}")

        self.structured   = StructuredPipeline(
            dept_id, full_cfg.get("structured_pipeline", {})
        )
        self.unstructured = UnstructuredPipeline(
            dept_id, full_cfg.get("unstructured_pipeline", {})
        )
        self._gov = get_governance_engine()

    async def run(self, query: str, user_role: str = "employee") -> PipelineResult:
        """Run both pipelines in parallel and fuse the results."""
        s_task = self.structured.run(query, user_role)
        u_task = self.unstructured.run(query, user_role)

        s_result, u_result = await asyncio.gather(s_task, u_task,
                                                   return_exceptions=False)

        fused   = self._fuse(query, s_result, u_result)
        sources = list(set(
            (s_result.sources if s_result.ok else []) +
            (u_result.sources if u_result.ok else [])
        ))
        confidence = max(
            s_result.confidence if s_result.ok else 0.0,
            u_result.confidence if u_result.ok else 0.0,
        )

        return PipelineResult(
            dept_id       = self.dept_id,
            structured    = s_result,
            unstructured  = u_result,
            fused_summary = fused,
            sources       = sources,
            confidence    = confidence,
        )

    async def run_structured(self, query: str, user_role: str = "employee") -> StructuredResult:
        return await self.structured.run(query, user_role)

    async def run_unstructured(self, query: str, user_role: str = "employee") -> UnstructuredResult:
        return await self.unstructured.run(query, user_role)

    def _fuse(self, query: str,
              s: StructuredResult,
              u: UnstructuredResult) -> str:
        parts: list[str] = []
        if s.ok:
            parts.append(f"**Data insight:** {s.nl_summary}")
        if u.ok:
            parts.append(f"**Document insight:** {u.nl_summary}")
        if not parts:
            return ""
        return "\n\n".join(parts)


# ── Registry of loaded pipelines ─────────────────────────────────────────────

_pipelines: dict[str, DeptPipeline] = {}


def get_dept_pipeline(dept_id: str) -> DeptPipeline:
    """Return cached DeptPipeline for dept_id, loading on first call."""
    if dept_id not in _pipelines:
        _pipelines[dept_id] = DeptPipeline(dept_id)
    return _pipelines[dept_id]


def all_dept_pipelines() -> dict[str, DeptPipeline]:
    """Load and return pipelines for all known departments."""
    known = [
        "finance", "hr", "legal", "sales", "marketing",
        "ops", "it", "procurement", "rd", "customer_success",
    ]
    for dept in known:
        get_dept_pipeline(dept)
    return _pipelines
