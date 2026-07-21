"""Request/response models for the grounded /ask endpoint.

This module was formerly the home of the multi-agent *bidding* pipeline
(``run_query``): a query fanned out to competing department agents that bid on
confidence, and the winners were merged. That engine was removed in the Phase 0
cleanup — governed retrieval now runs through a single deterministic path
(``pipelines.rag_pipeline`` for /ask, ``infrastructure.intelligence_gateway``
for the product surfaces). See DECISIONS.md for why the bidding mesh was cut.

Only the transport models remain here, still used by main.py's lean grounded
/ask endpoint.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []
    attached_file_b64: Optional[str] = None
    attached_file_name: Optional[str] = None
    use_web: bool = False
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    query_id: str
    answer: str
    confidence: float
    warning: Optional[str] = None
    sources: list[str] = []
    dept_tags: list[str] = []
    action_taken: str
    provider_used: Optional[str] = None
