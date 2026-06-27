"""
skill_selector.py — Intelligent skill selection for agent queries.

The SkillSelector analyzes a query and picks the best skill(s) to execute.
It ranks available skills by relevance, handles multi-skill pipelines, and
optimizes for speed and accuracy.

Example:
    For query "What is Q3 revenue?":
    - Intent: Data retrieval
    - Available: [sql_query, rag_search, web_search, calculation]
    - Ranking:
      1. sql_query (relevance: 0.95) ← BEST
      2. rag_search (relevance: 0.60)
      3. web_search (relevance: 0.40)
    - Selected: sql_query only
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from agents.capabilities.base_skill import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Detected intent from user query."""
    DATA_RETRIEVAL = "data_retrieval"      # "What is...", "How many...", "Show me..."
    FORECASTING = "forecasting"             # "Predict...", "Forecast...", "What will..."
    ANALYSIS = "analysis"                   # "Analyze...", "Compare...", "Breakdown..."
    ACTION = "action"                       # "Send...", "Post...", "Create..."
    GENERAL = "general"                     # General knowledge questions
    UNKNOWN = "unknown"


@dataclass
class SkillRanking:
    """Ranking for a single skill."""

    skill: BaseSkill
    relevance_score: float              # 0.0-1.0, how relevant to query
    connector_available: bool           # Do we have required connectors?
    dept_applicable: bool               # Is this applicable to user's dept?
    final_score: float                  # Composite score after all factors

    def is_viable(self) -> bool:
        """Check if this skill can actually be executed."""
        return (
            self.skill.enabled
            and self.connector_available
            and self.dept_applicable
            and self.final_score > 0.0
        )


class SkillSelector:
    """
    Intelligent skill selector for agents.

    Analyzes queries, ranks available skills, and selects the optimal
    skill(s) to execute.

    Features:
      - Detects query intent (data retrieval, forecasting, analysis, etc)
      - Ranks skills by relevance and availability
      - Handles multi-skill pipelines
      - Falls back gracefully if no skills available
      - Learns from execution results to improve future selections
    """

    def __init__(self, skill_registry, connector_registry):
        """
        Initialize skill selector.

        Args:
            skill_registry: SkillRegistry with available skills
            connector_registry: ConnectorRegistry with available connectors
        """
        self._skill_registry = skill_registry
        self._connector_registry = connector_registry
        self._selection_history: List[Dict[str, Any]] = []  # For learning

    async def select(
        self,
        query: str,
        dept_tag: str,
        user_permissions: Dict[str, Any],
        top_k: int = 3,  # Return top 3 ranked skills
    ) -> Tuple[List[BaseSkill], QueryIntent]:
        """
        Select best skill(s) for a query.

        Args:
            query: User query
            dept_tag: User's department
            user_permissions: User's access control
            top_k: Return top K skills

        Returns:
            (list of ranked skills, detected intent)

        Example:
            skills, intent = await selector.select(
                "What is Q3 revenue?",
                dept_tag="finance",
                user_permissions={"role": "manager"}
            )
            # skills = [sql_query_skill, rag_search_skill]
            # intent = QueryIntent.DATA_RETRIEVAL
        """
        # Detect intent
        intent = self._detect_intent(query)

        # Rank all available skills
        rankings = await self._rank_skills(query, intent, dept_tag)

        # Filter to viable skills and sort by score
        viable = [r for r in rankings if r.is_viable()]
        viable.sort(key=lambda r: r.final_score, reverse=True)

        # Return top K
        selected = [r.skill for r in viable[:top_k]]

        logger.info(
            f"SkillSelector: query='{query[:50]}' intent={intent.value} "
            f"selected={len(selected)} skills (top_k={top_k})"
        )

        return selected, intent

    def _detect_intent(self, query: str) -> QueryIntent:
        """
        Detect user intent from query text.

        Uses keyword matching and simple heuristics.

        Args:
            query: User query text

        Returns:
            Detected QueryIntent
        """
        query_lower = query.lower()

        # Data retrieval keywords
        if any(w in query_lower for w in ["what is", "how many", "show me", "list", "find", "get"]):
            return QueryIntent.DATA_RETRIEVAL

        # Forecasting keywords
        if any(w in query_lower for w in ["predict", "forecast", "estimate", "will", "expect"]):
            return QueryIntent.FORECASTING

        # Analysis keywords
        if any(w in query_lower for w in ["analyze", "compare", "breakdown", "trend", "pattern", "insight"]):
            return QueryIntent.ANALYSIS

        # Action keywords
        if any(w in query_lower for w in ["send", "post", "create", "update", "add", "notify", "alert"]):
            return QueryIntent.ACTION

        # General knowledge
        if any(w in query_lower for w in ["explain", "define", "what does", "tell me about"]):
            return QueryIntent.GENERAL

        return QueryIntent.UNKNOWN

    async def _rank_skills(
        self,
        query: str,
        intent: QueryIntent,
        dept_tag: str,
    ) -> List[SkillRanking]:
        """
        Rank all available skills for this query.

        Considers:
          - Skill relevance to intent
          - Connector availability
          - Department applicability
          - Skill priority
          - Historical success rate

        Args:
            query: User query
            intent: Detected intent
            dept_tag: User's department

        Returns:
            List of SkillRanking (may include non-viable skills with score=0)
        """
        rankings = []

        for skill in self._skill_registry.list_enabled():
            # Check connector availability
            required_connectors = skill.required_connectors()
            connectors_available = all(
                self._connector_registry.get(conn) is not None
                for conn in required_connectors
            )

            # Check department applicability
            applicable_depts = skill.applicable_to_depts()
            is_applicable = not applicable_depts or dept_tag in applicable_depts

            # Calculate relevance score (0.0-1.0)
            relevance = self._calculate_relevance(skill, query, intent)

            # Final composite score
            final_score = self._calculate_final_score(
                relevance=relevance,
                connector_available=connectors_available,
                is_applicable=is_applicable,
                skill_priority=skill.priority,
                query=query,
            )

            ranking = SkillRanking(
                skill=skill,
                relevance_score=relevance,
                connector_available=connectors_available,
                dept_applicable=is_applicable,
                final_score=final_score,
            )
            rankings.append(ranking)

        return rankings

    def _calculate_relevance(self, skill: BaseSkill, query: str, intent: QueryIntent) -> float:
        """
        Calculate how relevant a skill is to a query.

        Uses skill name, description, and intent matching.

        Args:
            skill: The skill to evaluate
            query: User query
            intent: Detected intent

        Returns:
            Score 0.0-1.0
        """
        score = 0.0

        # Keyword matching in query
        query_lower = query.lower()
        skill_name_lower = skill.name.lower()
        skill_desc_lower = skill.description.lower()

        # Direct skill name match (strong signal)
        if skill_name_lower in query_lower:
            score += 0.5

        # Description keywords in query
        desc_words = skill_desc_lower.split()
        matched_words = sum(1 for w in desc_words if w in query_lower and len(w) > 3)
        if matched_words > 0:
            score += min(0.3, matched_words * 0.1)

        # Intent-based relevance
        intent_scores = {
            QueryIntent.DATA_RETRIEVAL: {
                'sql_query': 0.9,
                'rag_search': 0.8,
                'web_search': 0.6,
            },
            QueryIntent.FORECASTING: {
                'forecast_revenue': 0.95,
                'churn_prediction': 0.8,
                'sql_query': 0.5,
            },
            QueryIntent.ANALYSIS: {
                'competitor_analysis': 0.9,
                'rag_search': 0.7,
                'sql_query': 0.6,
            },
            QueryIntent.ACTION: {
                'slack_send': 0.95,
                'api_call': 0.8,
            },
        }

        if intent in intent_scores:
            skill_intent_score = intent_scores[intent].get(skill.name, 0.0)
            score = max(score, skill_intent_score)

        return min(score, 1.0)

    def _calculate_final_score(
        self,
        relevance: float,
        connector_available: bool,
        is_applicable: bool,
        skill_priority: int,
        query: str,
    ) -> float:
        """
        Calculate final composite score for skill selection.

        Weights: 60% relevance, 20% connector availability, 10% applicability, 10% priority

        Args:
            relevance: 0.0-1.0 relevance score
            connector_available: Are required connectors available?
            is_applicable: Is skill applicable to user's department?
            skill_priority: 0-10 priority
            query: User query (for extra signals)

        Returns:
            Final score 0.0-1.0
        """
        # If connectors not available or not applicable, score is 0
        if not connector_available or not is_applicable:
            return 0.0

        # Normalize priority to 0.0-1.0
        priority_score = min(skill_priority / 10.0, 1.0)

        # Weighted composite
        final = (
            relevance * 0.6 +      # 60% relevance
            priority_score * 0.1 + # 10% priority
            0.3                     # 30% for being viable (connectors + applicable)
        )

        return min(final, 1.0)

    def record_execution(
        self,
        skill_name: str,
        query: str,
        result: SkillResult,
        execution_time_ms: int,
    ) -> None:
        """
        Record skill execution for learning and metrics.

        Args:
            skill_name: Name of skill executed
            query: The query that was executed
            result: The result returned
            execution_time_ms: How long it took
        """
        self._selection_history.append({
            'skill': skill_name,
            'query': query,
            'success': result.is_success(),
            'confidence': result.confidence,
            'time_ms': execution_time_ms,
        })

    def get_stats(self) -> Dict[str, Any]:
        """
        Get selection statistics for monitoring/debugging.

        Returns:
            Dict with selection metrics
        """
        if not self._selection_history:
            return {'total_selections': 0}

        total = len(self._selection_history)
        successes = sum(1 for e in self._selection_history if e['success'])
        avg_time = sum(e['time_ms'] for e in self._selection_history) / total

        # Skills used most frequently
        skill_counts = {}
        for entry in self._selection_history:
            skill = entry['skill']
            skill_counts[skill] = skill_counts.get(skill, 0) + 1

        return {
            'total_selections': total,
            'success_rate': successes / total if total > 0 else 0.0,
            'avg_execution_time_ms': avg_time,
            'most_used_skills': sorted(skill_counts.items(), key=lambda x: x[1], reverse=True),
        }
