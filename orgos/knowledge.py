"""
orgos/knowledge.py — the bridge from orgos departments to RAPID's document
RAG pipeline (pipelines/rag_pipeline.py, over data/documents).

orgos handlers are synchronous; the RAG pipeline is async. ask_knowledge_base
runs the pipeline on a dedicated event loop in a worker thread, so it works
both inside the FastAPI event loop and in plain scripts/tests.

Degradation contract: returns None when the pipeline cannot run at all
(Ollama down, import failure, timeout). Callers must record an HONEST
fallback — never pretend an answer was found. A pipeline that ran but found
no relevant documents is NOT None: it returns the honest "nothing found"
summary with empty citations, which is a real answer about the KB's state.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_PIPELINE_TIMEOUT = 120.0  # local Ollama on CPU can be slow; cap it hard


def ask_knowledge_base(question: str, department: str) -> Optional[dict]:
    """
    Ask the department's document knowledge base a question.

    Returns {"answer": str, "citations": [str], "confidence": float}
    or None when the knowledge backend is unavailable.
    """
    if not question.strip():
        return None
    try:
        from pipelines.rag_pipeline import run_rag_pipeline

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(
                asyncio.run, run_rag_pipeline(question, department, {})
            )
            result = fut.result(timeout=_PIPELINE_TIMEOUT)
        return {
            "answer": result.summary,
            "citations": list(result.citations or []),
            "confidence": float(result.confidence),
        }
    except Exception as e:
        logger.warning(
            "Knowledge base unavailable for %s question (%s)", department, e
        )
        return None


def list_indexed_sources(department: str) -> set:
    """
    Independent read of the department's document index — used by VERIFIERS
    to confirm that cited sources really exist, without trusting anything the
    answering handler recorded. Returns an empty set if the index is
    unreadable (which makes any citation check fail, the safe direction).
    """
    try:
        from infrastructure.doc_master import get_doc_master

        return set(get_doc_master().list_sources(department))
    except Exception as e:
        logger.warning("Could not read %s document index (%s)", department, e)
        return set()
