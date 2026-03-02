"""
Query Router for RAPID.

Two routing strategies are available:

1. **QueryRouter** — original regex-based router (fast, ~0 ms, no dependencies).
   Still used as a quick pre-filter and as the default when embeddings are not
   available.

2. **EmbeddingBasedRouter** — computes cosine similarity between the query
   embedding and pre-computed route-description embeddings.  More accurate for
   ambiguous queries (~10 ms with a local SentenceTransformer vs ~200 ms for an
   LLM).  Falls back to QueryRouter if embeddings fail.

Usage::

    from app.services.query_router import EmbeddingBasedRouter
    router = EmbeddingBasedRouter()
    result = router.route("What is our Q3 revenue?")
    # result["strategy"] -> "internal_only" | "web_only" | "parallel"
"""

import logging
import math
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 1. Original regex router ───────────────────────────────────────────────────

class QueryRouter:
    """Decide if a query needs web search, internal docs, or both."""

    WEB_INDICATORS = [
        r"\b(latest|current|recent|today|2026|2025|news|trending)\b",
        r"\b(what is|who is|how to|explain)\b",
        r"\b(internet|online|web|google|search)\b",
    ]

    INTERNAL_INDICATORS = [
        r"\b(our|my|company|organization|internal)\b",
        r"\b(policy|procedure|document|report|compliance)\b",
        r"\b(database|codebase|repository|project)\b",
    ]

    def route(self, query: str) -> Dict:
        query_lower = query.lower()
        needs_web = any(re.search(p, query_lower, re.IGNORECASE) for p in self.WEB_INDICATORS)
        needs_internal = any(re.search(p, query_lower, re.IGNORECASE) for p in self.INTERNAL_INDICATORS)

        if not needs_web and not needs_internal:
            needs_internal = True

        if needs_web and needs_internal:
            strategy = "parallel"
        elif needs_web:
            strategy = "web_only"
        else:
            strategy = "internal_only"

        return {
            "needs_web": needs_web,
            "needs_internal": needs_internal,
            "strategy": strategy,
            "confidence": 0.8,
        }


# ── 2. Embedding-based router ──────────────────────────────────────────────────

# Route descriptions: each route has a short natural-language description that
# captures the kinds of queries it handles.  The router picks the route whose
# description embedding is closest to the query embedding.
_ROUTE_DESCRIPTIONS: List[Dict] = [
    {
        "strategy": "internal_only",
        "needs_web": False,
        "needs_internal": True,
        "description": (
            "Questions about internal company documents, policies, procedures, "
            "reports, compliance, databases, codebases, or proprietary data."
        ),
    },
    {
        "strategy": "web_only",
        "needs_web": True,
        "needs_internal": False,
        "description": (
            "Questions about current events, latest news, trending topics, "
            "real-time information, or general world knowledge."
        ),
    },
    {
        "strategy": "parallel",
        "needs_web": True,
        "needs_internal": True,
        "description": (
            "Questions that require BOTH internal documents AND up-to-date web "
            "information, such as comparing our policy to industry standards or "
            "combining internal data with recent market trends."
        ),
    },
]


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class EmbeddingBasedRouter:
    """
    Route queries by comparing their embeddings against route-description
    embeddings using cosine similarity.

    Falls back to regex-based QueryRouter when embedding inference fails.

    Args:
        model_name: SentenceTransformer model to use.  Default is the same
                    lightweight model used throughout RAPID.
        min_confidence: If the best cosine score is below this threshold,
                        fall back to the regex router.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        min_confidence: float = 0.35,
    ):
        self.model_name = model_name
        self.min_confidence = min_confidence
        self._fallback = QueryRouter()
        self._model = None
        self._route_embeddings: Optional[List[List[float]]] = None

    # ── Lazy init ──────────────────────────────────────────────────────────────

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info("EmbeddingBasedRouter: loaded model '%s'", self.model_name)
            except Exception as exc:
                logger.warning(
                    "EmbeddingBasedRouter: cannot load SentenceTransformer: %s "
                    "— falling back to regex router",
                    exc,
                )
                self._model = None
        return self._model

    def _get_route_embeddings(self) -> Optional[List[List[float]]]:
        """Lazily compute and cache route-description embeddings."""
        if self._route_embeddings is not None:
            return self._route_embeddings
        model = self._load_model()
        if model is None:
            return None
        try:
            descs = [r["description"] for r in _ROUTE_DESCRIPTIONS]
            vecs = model.encode(descs, convert_to_numpy=False)
            self._route_embeddings = [list(map(float, v)) for v in vecs]
            return self._route_embeddings
        except Exception as exc:
            logger.warning("EmbeddingBasedRouter: route embedding failed: %s", exc)
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def embed_query(self, query: str) -> Optional[List[float]]:
        """Return the embedding for a single query string, or None on failure."""
        model = self._load_model()
        if model is None:
            return None
        try:
            vec = model.encode([query], convert_to_numpy=False)[0]
            return list(map(float, vec))
        except Exception as exc:
            logger.debug("EmbeddingBasedRouter.embed_query failed: %s", exc)
            return None

    def route(self, query: str) -> Dict:
        """
        Route a query.

        Returns the same dict shape as QueryRouter.route():
            {needs_web, needs_internal, strategy, confidence}

        The ``confidence`` field is the cosine similarity score (0–1).
        """
        route_embs = self._get_route_embeddings()
        query_emb = self.embed_query(query) if route_embs else None

        if route_embs is None or query_emb is None:
            logger.debug("EmbeddingBasedRouter: using regex fallback")
            return self._fallback.route(query)

        # Find best matching route
        scores = [_cosine(query_emb, re_) for re_ in route_embs]
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_score = scores[best_idx]

        if best_score < self.min_confidence:
            # Low confidence — fallback
            logger.debug(
                "EmbeddingBasedRouter: low confidence (%.3f) → regex fallback", best_score
            )
            return self._fallback.route(query)

        route = _ROUTE_DESCRIPTIONS[best_idx]
        logger.debug(
            "EmbeddingBasedRouter: strategy='%s' (sim=%.3f)",
            route["strategy"], best_score,
        )
        return {
            "needs_web": route["needs_web"],
            "needs_internal": route["needs_internal"],
            "strategy": route["strategy"],
            "confidence": round(best_score, 4),
        }
