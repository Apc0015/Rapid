"""
rd_agent.py — R&D Department Agent Intelligence

Provides domain-specific intelligence for:
  - Product innovation tracking
  - Research progress monitoring
  - Development pipeline management
  - Technology evaluation
  - Feature prioritization
"""

import logging
from typing import Any, Dict, List

from agents.intelligence.base_agent_intelligence import (
    BaseAgentIntelligence,
    DomainIntent,
    DomainKnowledge,
    QueryAnalysis,
    SkillPlan,
)

logger = logging.getLogger(__name__)


class RDAgent(BaseAgentIntelligence):
    """R&D department agent with innovation, research, and development expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build R&D-specific domain knowledge."""
        return DomainKnowledge(
            department="rd",
            key_concepts=[
                "innovation", "research", "development", "product", "feature",
                "pipeline", "roadmap", "priority", "milestone", "release",
                "technology", "evaluation", "poc", "prototype", "testing",
                "patent", "ip", "competitive_analysis", "market_fit"
            ],
            keywords={
                "innovation": ["innovation", "new", "novel", "breakthrough"],
                "research": ["research", "study", "experiment", "analysis"],
                "development": ["development", "build", "code", "implementation"],
                "product": ["product", "feature", "release", "launch"],
                "pipeline": ["pipeline", "roadmap", "milestone", "timeline"],
                "technology": ["technology", "tool", "framework", "library"],
                "testing": ["test", "qa", "quality", "validation"],
            },
            skill_rules={
                "innovation_tracking": ["rag_search", "sql_query"],
                "research_progress": ["sql_query", "calculation"],
                "development_pipeline": ["sql_query", "calculation"],
                "technology_evaluation": ["rag_search", "web_search"],
                "feature_prioritization": ["sql_query", "calculation"],
            },
            validation_rules={
                "priority_valid": True,
                "timeline_reasonable": True,
                "resource_positive": True,
            },
            governance_rules={
                "competitive_sensitive": True,
                "ip_protection_required": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify R&D query to domain intent."""
        query_lower = query.lower()

        # Product innovation (reuse MARKET_TRENDS)
        if any(w in query_lower for w in ["innovation", "new", "novel", "breakthrough"]):
            return DomainIntent.MARKET_TRENDS

        # Research progress (reuse FORECASTING)
        if any(w in query_lower for w in ["research", "study", "progress", "experiment"]):
            return DomainIntent.FORECASTING

        # Development pipeline (reuse PIPELINE_HEALTH)
        if any(w in query_lower for w in ["development", "pipeline", "roadmap", "release"]):
            return DomainIntent.PIPELINE_HEALTH

        # Technology evaluation (reuse COMPETITIVE_THREAT)
        if any(w in query_lower for w in ["technology", "tool", "framework", "evaluate"]):
            return DomainIntent.COMPETITIVE_THREAT

        # Feature prioritization (reuse DEAL_ANALYSIS)
        if any(w in query_lower for w in ["feature", "priority", "prioritize", "impact"]):
            return DomainIntent.DEAL_ANALYSIS

        # Default
        return DomainIntent.PIPELINE_HEALTH

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract R&D-specific entities."""
        entities = {}

        # Project or feature name
        if "project" in query.lower():
            entities["type"] = "project"
        elif "feature" in query.lower():
            entities["type"] = "feature"
        elif "research" in query.lower():
            entities["type"] = "research"

        # Technology type
        techs = ["ai", "ml", "blockchain", "cloud", "edge", "mobile", "web"]
        query_lower = query.lower()
        for tech in techs:
            if tech in query_lower:
                entities["technology"] = tech
                break

        # Phase
        if "poc" in query_lower or "proof" in query_lower:
            entities["phase"] = "poc"
        elif "prototype" in query_lower:
            entities["phase"] = "prototype"
        elif "beta" in query_lower:
            entities["phase"] = "beta"
        elif "production" in query_lower:
            entities["phase"] = "production"

        # Timeline
        if "quarter" in query_lower:
            entities["timeline"] = "quarterly"
        elif "year" in query_lower:
            entities["timeline"] = "annual"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """R&D needs real-time for progress tracking."""
        return True

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """R&D might need CRM for customer feedback."""
        return intent == DomainIntent.MARKET_TRENDS

    def _needs_external(self, intent: DomainIntent) -> bool:
        """R&D needs external data for market/tech trends."""
        return intent in [
            DomainIntent.MARKET_TRENDS,
            DomainIntent.COMPETITIVE_THREAT,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """R&D queries are sensitive (IP, competitive advantage)."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for R&D queries."""
        clarifications = []

        if "type" not in entities:
            clarifications.append("What type: Project, Feature, or Research?")

        if "phase" not in entities and intent == DomainIntent.PIPELINE_HEALTH:
            clarifications.append("What phase: POC, Prototype, Beta, or Production?")

        if intent == DomainIntent.MARKET_TRENDS:
            clarifications.append("Market segment or customer type?")

        if intent == DomainIntent.FORECASTING:
            clarifications.append("Timeline: Quarterly, Annual, or Multi-year?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in R&D intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if any(w in query_lower for w in ["innovation", "novel", "breakthrough"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["research", "study", "progress"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["development", "pipeline", "roadmap"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["technology", "evaluate", "framework"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["feature", "priority", "impact"]):
            confidence = 0.8

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on R&D requirements."""
        adjusted = skills.copy()

        # For all R&D, add IP protection
        if "ip_protection" not in adjusted:
            adjusted.append("ip_protection")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for R&D queries."""
        # If web search fails, try RAG
        if "web_search" in skills:
            return ["rag_search"]
        # If SQL fails, try RAG
        if "sql_query" in skills:
            return ["rag_search"]
        # Default fallback
        return ["rag_search"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = "For R&D query: "

        if "sql_query" in skills:
            rationale += "Query development database for project status and metrics. "
        if "rag_search" in skills:
            rationale += "Search research documents and technical specifications. "
        if "web_search" in skills:
            rationale += "Search for technology and market trends. "
        if "calculation" in skills:
            rationale += "Calculate development metrics and timelines. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        return "R&D pipeline with project status, timelines, resources, and risks"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for R&D results."""
        checks = [
            "ip_protected",
            "no_competitive_disclosure",
            "priority_valid",
            "timeline_reasonable",
            "no_null_values",
        ]

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """R&D-specific validations."""
        issues = []

        # Check priority is valid (1-5 scale or similar)
        if "priority" in result:
            priority = result["priority"]
            if isinstance(priority, int):
                if not (1 <= priority <= 5):
                    issues.append(f"Priority must be 1-5, got {priority}")

        # Check timeline is reasonable
        if "timeline_days" in result:
            timeline = result["timeline_days"]
            if timeline <= 0:
                issues.append("Timeline must be positive days")

        # Check resource requirement is positive
        if "resources_required" in result:
            resources = result["resources_required"]
            if isinstance(resources, int) and resources <= 0:
                issues.append("Resource requirement must be positive")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (IP protection, competitive sensitivity)."""
        issues = []

        # Check result is marked as confidential
        if "confidential" not in str(result).lower():
            issues.append(
                "R&D result must be marked CONFIDENTIAL - contains competitive IP"
            )

        # Check no competitive details are exposed
        dangerous_patterns = ["competitor", "feature_comparison", "benchmark"]
        result_str = str(result).lower()
        for pattern in dangerous_patterns:
            if pattern in result_str:
                issues.append(
                    f"Result contains competitive disclosure: {pattern} - REDACT"
                )

        return issues

    def _validate_format(
        self,
        result: Dict[str, Any],
        plan: SkillPlan,
    ) -> List[str]:
        """Validate result format matches expected output."""
        issues = []

        if not result:
            issues.append("Result is empty")
            return issues

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on R&D results."""
        issues = []

        # Timeline sanity
        if "timeline_days" in result:
            timeline = result["timeline_days"]
            if timeline < 7:  # < 1 week
                issues.append(f"Timeline {timeline} days seems unrealistically short")
            if timeline > 1825:  # > 5 years
                issues.append(
                    f"Timeline {timeline} days (5+ years) seems very long - verify feasibility"
                )

        # Resource sanity
        if "team_size" in result:
            team = result["team_size"]
            if team > 50:  # > 50 people
                issues.append(
                    f"Team size {team} seems large for typical project - verify"
                )

        # Priority sanity
        if "priority" in result:
            priority = result["priority"]
            if priority == 5 and "timeline_days" in result:
                if result["timeline_days"] > 365:
                    issues.append(
                        "High priority (5) with >1 year timeline - inconsistent"
                    )

        return issues
