from __future__ import annotations
"""DocumentTool — document knowledge access via the R1-R4 RAG pipeline."""

import logging
from agents.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class DocumentTool(BaseTool):
    name = "search_documents"
    description = (
        "Search department documents (policies, reports, contracts, handbooks). "
        "Returns a natural-language summary — never raw document chunks."
    )

    async def run(
        self,
        query: str,
        dept_tag: str,
        user_permissions: dict,
        doc_type: str = "",
    ) -> str:
        """
        Runs the full R1-R4 RAG pipeline for the given dept and query.
        doc_type is an optional hint (e.g. 'policy', 'report', 'contract').
        Returns the NL summary string or an empty string on failure.
        """
        from pipelines.rag_pipeline import run_rag_pipeline

        # Inject doc_type hint into query if provided
        effective_query = f"{query} [document type: {doc_type}]" if doc_type else query

        try:
            result = await run_rag_pipeline(effective_query, dept_tag, user_permissions)
            return result.summary or ""
        except Exception as exc:
            logger.error(f"DocumentTool failed for dept={dept_tag}: {exc!r}")
            return ""
