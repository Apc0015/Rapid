from __future__ import annotations
"""
agent_contract.py — Formal interface every agent must satisfy.

This module defines:
  - AgentContract   abstract base class (bid + execute)
  - Re-exports BidObject and NLResult from models/ so callers
    can do `from agents.base.agent_contract import BidObject, NLResult`

Nothing here contains logic — purely types and protocol.
"""

from abc import ABC, abstractmethod

# Re-export the canonical model definitions so downstream code has a single
# import point.  The source of truth remains models/.
from models.bid_object import BidObject          # noqa: F401
from models.nl_result  import NLResult           # noqa: F401


class AgentContract(ABC):
    """
    Every department agent and every C-suite agent must satisfy this contract.

    The contract intentionally keeps the interface minimal:
      - agent_id  → unique identifier used by registry and mesh bus
      - bid()     → can this agent handle the query, and how confident?
      - execute() → run the full pipeline, return an NL summary only

    Extensions (e.g. handle_escalation for C-suite agents) are defined in
    their own base classes and are NOT part of this core contract.
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique string identifier, e.g. 'finance', 'cfo'."""
        ...

    @abstractmethod
    async def bid(self, query: str) -> BidObject:
        """
        Evaluate whether this agent can handle `query`.
        Must be fast (no DB/LLM calls) — keyword matching or simple heuristics only.
        """
        ...

    @abstractmethod
    async def execute(self, query: str, user_permissions: dict) -> NLResult:
        """
        Run the full pipeline for this agent.
        Must return an NLResult with summary, confidence, and citations.
        Raw rows, chunks, or schema must NEVER be included in the result.
        """
        ...
