"""
R2 — Query Rewriter

Converts conversational user queries into formal retrieval queries.
Reduces vocabulary mismatch between user language and document language.
Also generates HyDE (Hypothetical Document Embedding) passage for better recall.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    original_query: str
    rewritten_query: str            # Formal query for retrieval
    hyde_passage: Optional[str]     # Hypothetical document passage
    rewrite_method: str             # "direct" | "hyde" | "fallback"


class QueryRewriter:
    """R2 — rewrites queries for better document retrieval."""

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def rewrite(self, query: str, doc_type: str = "narrative") -> RewriteResult:
        """
        Rewrite the query for retrieval and generate a HyDE passage.

        Args:
            query: Original user question
            doc_type: Document type hint for vocabulary adaptation

        Returns:
            RewriteResult with rewritten_query and optional hyde_passage
        """
        # Step 1: Rewrite for retrieval
        rewritten = await self._rewrite_for_retrieval(query, doc_type)

        # Step 2: Generate HyDE passage (hypothetical ideal answer excerpt)
        hyde = await self._generate_hyde(query, doc_type)

        return RewriteResult(
            original_query=query,
            rewritten_query=rewritten or query,
            hyde_passage=hyde,
            rewrite_method="hyde" if hyde else "direct",
        )

    async def _rewrite_for_retrieval(self, query: str, doc_type: str) -> str:
        """Convert conversational question to formal retrieval terms."""
        prompt = f"""Convert this conversational question into a formal search query for document retrieval.

Document type: {doc_type}
Question: "{query}"

Rules:
- Output ONLY the rewritten search terms (no explanation, no question marks)
- Use formal vocabulary that would appear in the document
- Include synonyms and related terms
- Do not answer the question

Example:
Input: "What's the refund policy?"
Output: "refund processing time limit customer returns policy procedure reimbursement"

Rewritten query:"""

        try:
            result = await self.llm.chat(prompt, max_tokens=100, temperature=0.0)
            result = result.strip().strip('"').strip("'")
            if result and len(result) > 3:
                return result
        except Exception as e:
            logger.warning("R2 rewrite failed: %s", e)

        return query  # fallback to original

    async def _generate_hyde(self, query: str, doc_type: str) -> Optional[str]:
        """Generate a hypothetical document passage that would answer the query."""
        prompt = f"""Write a brief excerpt from a {doc_type} document that would directly answer this question.

Question: "{query}"

Write 2-3 sentences as if from the actual document. Be specific and use formal language.
Do not use phrases like "According to..." or "The document states...".
Output ONLY the passage, nothing else."""

        try:
            passage = await self.llm.chat(prompt, max_tokens=200, temperature=0.1)
            passage = passage.strip()
            if len(passage) > 20:
                return passage
        except Exception as e:
            logger.debug("R2 HyDE generation failed: %s", e)

        return None
