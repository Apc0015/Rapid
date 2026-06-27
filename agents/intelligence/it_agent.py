"""
it_agent.py — IT Department Agent Intelligence

Provides domain-specific intelligence for:
  - Infrastructure management
  - Security and compliance
  - System uptime and performance
  - Incident response
  - Technology roadmap planning
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


class ITAgent(BaseAgentIntelligence):
    """IT department agent with infrastructure, security, and systems expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build IT-specific domain knowledge."""
        return DomainKnowledge(
            department="it",
            key_concepts=[
                "infrastructure", "server", "database", "network", "cloud",
                "security", "vulnerability", "threat", "compliance", "audit",
                "uptime", "availability", "performance", "latency", "incident",
                "deployment", "release", "version", "patch", "update"
            ],
            keywords={
                "infrastructure": ["server", "database", "cloud", "infrastructure"],
                "security": ["security", "vulnerability", "threat", "encryption"],
                "uptime": ["uptime", "availability", "incident", "outage"],
                "performance": ["performance", "latency", "throughput", "cpu"],
                "deployment": ["deployment", "release", "version", "patch"],
                "compliance": ["compliance", "audit", "pci", "soc2"],
            },
            skill_rules={
                "infrastructure_management": ["sql_query", "api_call", "rag_search"],
                "security_compliance": ["sql_query", "api_call", "rag_search"],
                "uptime_performance": ["sql_query", "api_call"],
                "incident_response": ["sql_query", "api_call"],
                "roadmap_planning": ["rag_search", "calculation"],
            },
            validation_rules={
                "uptime_0_to_100": True,
                "latency_positive": True,
                "no_security_exposure": True,
            },
            governance_rules={
                "no_secrets_in_result": True,
                "security_focus_required": True,
                "audit_trail_required": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify IT query to domain intent."""
        query_lower = query.lower()

        # Infrastructure management
        if any(w in query_lower for w in ["infrastructure", "server", "database", "cloud"]):
            return DomainIntent.PROCESS_OPTIMIZATION  # Reuse as infrastructure optimization

        # Security and compliance
        if any(w in query_lower for w in ["security", "vulnerability", "compliance", "audit"]):
            return DomainIntent.COMPLIANCE_CHECK

        # Uptime and performance
        if any(w in query_lower for w in ["uptime", "availability", "incident", "outage"]):
            return DomainIntent.FINANCIAL_HEALTH  # Reuse as system health

        # Deployment and releases
        if any(w in query_lower for w in ["deployment", "release", "version", "patch"]):
            return DomainIntent.BUDGET_PLANNING  # Reuse for deployment planning

        # Default
        return DomainIntent.PROCESS_OPTIMIZATION

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract IT-specific entities."""
        entities = {}

        # System type
        if "kubernetes" in query.lower() or "k8s" in query.lower():
            entities["system_type"] = "kubernetes"
        elif "docker" in query.lower():
            entities["system_type"] = "docker"
        elif "vm" in query.lower() or "virtual" in query.lower():
            entities["system_type"] = "vm"
        elif "database" in query.lower():
            entities["system_type"] = "database"

        # Cloud platform
        if "aws" in query.lower():
            entities["cloud"] = "aws"
        elif "gcp" in query.lower() or "google" in query.lower():
            entities["cloud"] = "gcp"
        elif "azure" in query.lower():
            entities["cloud"] = "azure"

        # Severity
        if "critical" in query.lower():
            entities["severity"] = "critical"
        elif "high" in query.lower():
            entities["severity"] = "high"
        elif "medium" in query.lower():
            entities["severity"] = "medium"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """IT needs real-time for uptime and security monitoring."""
        return True

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """IT rarely needs CRM."""
        return False

    def _needs_external(self, intent: DomainIntent) -> bool:
        """IT might need external security/patch databases."""
        return True

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """IT always handles sensitive security and infrastructure data."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for IT queries."""
        clarifications = []

        if "system_type" not in entities:
            clarifications.append(
                "System type: Kubernetes, Docker, VM, Database, or Network?"
            )

        if "cloud" not in entities and "infrastructure" in query.lower():
            clarifications.append("Cloud platform: AWS, GCP, Azure, or On-premise?")

        clarifications.append("Time period or affected systems?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in IT intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if any(w in query_lower for w in ["infrastructure", "server", "cloud"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["security", "vulnerability", "compliance"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["uptime", "incident", "outage"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["deployment", "release", "patch"]):
            confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on IT requirements."""
        adjusted = skills.copy()

        # All IT needs security validation
        if "security_check" not in adjusted:
            adjusted.append("security_check")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for IT queries."""
        # If API call fails, try SQL
        if "api_call" in skills:
            return ["sql_query", "rag_search"]
        # Default fallback
        return ["rag_search"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = "For IT query: "

        if "api_call" in skills:
            rationale += "Query infrastructure APIs for real-time status. "
        if "sql_query" in skills:
            rationale += "Query IT systems database. "
        if "rag_search" in skills:
            rationale += "Search IT documentation and runbooks. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        return "System status with uptime metrics, security posture, and incident summary"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for IT results."""
        checks = [
            "uptime_0_100",
            "no_secrets",
            "no_credentials",
            "no_private_keys",
            "security_focus",
        ]

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """IT-specific validations."""
        issues = []

        # Check uptime is 0-100
        if "uptime" in result:
            uptime = result["uptime"]
            if not (0 <= uptime <= 100):
                issues.append(f"Uptime must be 0-100, got {uptime}")

        # Check latency is positive
        if "latency_ms" in result:
            latency = result["latency_ms"]
            if latency < 0:
                issues.append("Latency cannot be negative")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (no secrets, security focus)."""
        issues = []

        # Check for exposed secrets
        dangerous_strings = ["password", "api_key", "secret", "token", "credential"]
        result_str = str(result).lower()
        for danger in dangerous_strings:
            if danger in result_str:
                issues.append(
                    f"SECURITY: Result contains sensitive {danger} - redact before sharing"
                )

        # Check for private key exposure
        if "private" in result_str and "key" in result_str:
            issues.append("SECURITY: Result may contain private keys - MUST REDACT")

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
        """Sanity checks on IT results."""
        issues = []

        # Uptime sanity
        if "uptime" in result:
            uptime = result["uptime"]
            if uptime > 99.99:  # > 99.99% is rare
                issues.append(
                    f"Uptime {uptime:.2f}% seems unrealistically high - verify measurement"
                )
            if uptime < 50:  # < 50% is critical
                issues.append(
                    f"Uptime {uptime:.0f}% is critically low - INCIDENT ESCALATION required"
                )

        # Latency sanity
        if "latency_ms" in result:
            latency = result["latency_ms"]
            if latency > 10000:  # > 10 seconds
                issues.append(
                    f"Latency {latency}ms is very high - PERFORMANCE ISSUE"
                )

        return issues
