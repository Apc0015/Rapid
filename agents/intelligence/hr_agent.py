"""
hr_agent.py — HR Department Agent Intelligence

Provides domain-specific intelligence for:
  - Retention risk analysis
  - Hiring needs and planning
  - Compensation analysis
  - Compliance and labor law
  - Culture and engagement
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


class HRAgent(BaseAgentIntelligence):
    """HR department agent with retention, hiring, and compensation expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build HR-specific domain knowledge."""
        return DomainKnowledge(
            department="hr",
            key_concepts=[
                "employee", "retention", "churn", "engagement", "culture",
                "hiring", "recruitment", "pipeline", "interview", "offer",
                "compensation", "salary", "equity", "benefits", "cost",
                "compliance", "labor_law", "policy", "diversity", "inclusion"
            ],
            keywords={
                "retention": ["retention", "churn", "at_risk", "leaving", "exit"],
                "hiring": ["hiring", "recruitment", "open_roles", "candidates", "pipeline"],
                "compensation": ["salary", "compensation", "equity", "bonus", "benefits"],
                "compliance": ["compliance", "labor", "law", "policy", "audit"],
                "engagement": ["engagement", "satisfaction", "morale", "culture"],
                "diversity": ["diversity", "inclusion", "d&i", "underrepresented"],
            },
            skill_rules={
                "retention_risk": ["sql_query", "churn_risk", "rag_search"],
                "hiring_need": ["sql_query", "rag_search", "calculation"],
                "compensation": ["sql_query", "calculation"],
                "compliance": ["rag_search", "sql_query"],
                "culture": ["rag_search", "calculation"],
            },
            validation_rules={
                "retention_score_0_1": True,
                "churn_risk_0_1": True,
                "headcount_positive": True,
                "no_salary_exposure": True,
            },
            governance_rules={
                "no_individual_salary": True,
                "no_personal_medical_data": True,
                "no_performance_reviews": True,
                "aggregate_only": True,
                "gdpr_compliant": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify HR query to domain intent."""
        query_lower = query.lower()

        # Retention risk
        if any(w in query_lower for w in ["retention", "churn", "at_risk", "leaving"]):
            return DomainIntent.RETENTION_RISK

        # Hiring need
        if any(w in query_lower for w in ["hiring", "recruitment", "open_roles", "headcount"]):
            return DomainIntent.HIRING_NEED

        # Compensation
        if any(w in query_lower for w in ["salary", "compensation", "equity", "bonus"]):
            return DomainIntent.COMPENSATION

        # Compliance
        if any(w in query_lower for w in ["compliance", "labor", "policy", "audit"]):
            return DomainIntent.COMPLIANCE

        # Culture
        if any(w in query_lower for w in ["culture", "engagement", "satisfaction", "morale"]):
            return DomainIntent.CULTURE

        # Default
        return DomainIntent.HIRING_NEED

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract HR-specific entities."""
        entities = {}

        # Department
        departments = ["engineering", "sales", "marketing", "finance", "ops", "legal", "hr"]
        query_lower = query.lower()
        for dept in departments:
            if dept in query_lower:
                entities["department"] = dept
                break

        # Experience level
        if "junior" in query_lower:
            entities["level"] = "junior"
        elif "mid" in query_lower:
            entities["level"] = "mid"
        elif "senior" in query_lower:
            entities["level"] = "senior"
        elif "staff" in query_lower:
            entities["level"] = "staff"

        # Role type
        if "manager" in query_lower:
            entities["role_type"] = "manager"
        elif "ic" in query_lower or "individual" in query_lower:
            entities["role_type"] = "ic"

        # Time period
        if "quarter" in query_lower or "q1" in query_lower:
            entities["period"] = "quarterly"
        elif "year" in query_lower or "annual" in query_lower:
            entities["period"] = "annual"
        else:
            entities["period"] = "current"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """HR needs real-time for engagement/culture monitoring."""
        return intent in [
            DomainIntent.RETENTION_RISK,
            DomainIntent.CULTURE,
        ]

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """HR queries rarely need CRM."""
        return False

    def _needs_external(self, intent: DomainIntent) -> bool:
        """HR might need external compliance/labor law info."""
        return intent == DomainIntent.COMPLIANCE

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """HR always handles sensitive employee data."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for HR queries."""
        clarifications = []

        # Retention needs department
        if intent == DomainIntent.RETENTION_RISK:
            if "department" not in entities:
                clarifications.append(
                    "Retention risk in which department? Or company-wide?"
                )
            clarifications.append("What risk threshold (0.0-1.0)? Default is 0.6.")

        # Hiring needs department and level
        if intent == DomainIntent.HIRING_NEED:
            if "department" not in entities:
                clarifications.append("Hiring for which department?")
            if "level" not in entities:
                clarifications.append("What experience level: Junior, Mid, Senior, Staff?")

        # Compensation needs role type
        if intent == DomainIntent.COMPENSATION:
            if "role_type" not in entities:
                clarifications.append("Role type: Manager, Individual Contributor, or both?")

        # Compliance needs specific law/policy
        if intent == DomainIntent.COMPLIANCE:
            clarifications.append("Which compliance area: Labor Law, Privacy (GDPR), DEI, or other?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in HR intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if intent == DomainIntent.RETENTION_RISK:
            keywords = ["retention", "churn", "at_risk", "leaving"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.HIRING_NEED:
            keywords = ["hiring", "recruitment", "open_roles", "headcount"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.COMPENSATION:
            keywords = ["salary", "compensation", "equity", "bonus"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.COMPLIANCE:
            keywords = ["compliance", "labor", "policy", "audit"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.CULTURE:
            keywords = ["culture", "engagement", "satisfaction", "morale"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.8

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on HR requirements."""
        adjusted = skills.copy()

        # For retention risk, prioritize churn risk model
        if analysis.domain_intent == DomainIntent.RETENTION_RISK:
            if "churn_risk" not in adjusted:
                adjusted.insert(0, "churn_risk")

        # For all HR queries, ensure validation is last
        if "validation_check" not in adjusted:
            adjusted.append("validation_check")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for HR queries."""
        # If churn model fails, try SQL + RAG
        if "churn_risk" in skills:
            return ["sql_query", "rag_search"]
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
        rationale = f"For {analysis.domain_intent.value} query: "

        if "sql_query" in skills:
            rationale += "Query HR database for employee and hiring data. "
        if "churn_risk" in skills:
            rationale += "Apply churn risk scoring model. "
        if "calculation" in skills:
            rationale += "Calculate HR metrics (cost per hire, retention rate). "
        if "rag_search" in skills:
            rationale += "Search HR policies and compliance documents. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.RETENTION_RISK:
            return "At-risk employee segments with churn risk score, primary drivers, and retention actions"
        elif analysis.domain_intent == DomainIntent.HIRING_NEED:
            return "Hiring demand by department and level with timeline, budget, and candidate pipeline"
        elif analysis.domain_intent == DomainIntent.COMPENSATION:
            return "Compensation analysis by role with range, percentiles, and equity position"
        elif analysis.domain_intent == DomainIntent.COMPLIANCE:
            return "Compliance status report with gaps, remediation actions, and timeline"
        elif analysis.domain_intent == DomainIntent.CULTURE:
            return "Culture/engagement metrics with scores, trends, and improvement areas"

        return "HR data with analysis and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for HR results."""
        checks = [
            "no_individual_salary",
            "no_personal_data",
            "aggregated_data",
            "no_null_values",
        ]

        if analysis.domain_intent == DomainIntent.RETENTION_RISK:
            checks.append("churn_score_0_1")

        if analysis.domain_intent == DomainIntent.HIRING_NEED:
            checks.append("headcount_positive")

        checks.append("gdpr_compliant")

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """HR-specific validations."""
        issues = []

        # Check retention score is 0-1
        if "retention_score" in result:
            score = result["retention_score"]
            if not (0.0 <= score <= 1.0):
                issues.append(f"Retention score must be 0-1, got {score}")

        # Check churn risk is 0-1
        if "churn_risk" in result:
            risk = result["churn_risk"]
            if not (0.0 <= risk <= 1.0):
                issues.append(f"Churn risk must be 0-1, got {risk}")

        # Check headcount is positive
        if "headcount" in result:
            if isinstance(result["headcount"], int):
                if result["headcount"] < 0:
                    issues.append("Headcount cannot be negative")

        # Check hiring cost per hire is reasonable
        if "cost_per_hire" in result:
            cost = result["cost_per_hire"]
            if cost > 500_000:  # > $500K seems high
                issues.append(f"Cost per hire ${cost:,.0f} seems unusually high")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance rules (GDPR, PII, no individual data)."""
        issues = []

        # Dangerous keys to check
        dangerous_keys = [
            "name", "email", "phone", "ssn", "dob", "salary", "performance",
            "medical", "religion", "political", "union", "personal_contact"
        ]

        for key in result.keys():
            if any(dk in key.lower() for dk in dangerous_keys):
                issues.append(
                    f"Individual employee PII exposed: {key}. "
                    "Must be aggregated/anonymized or removed."
                )

        # Check data is aggregated (not row-level employee data)
        if "employees" in result and isinstance(result["employees"], list):
            if len(result["employees"]) > 0:
                if isinstance(result["employees"][0], dict):
                    item = result["employees"][0]
                    if "salary" in item or "email" in item:
                        issues.append(
                            "Result contains row-level employee data with PII. "
                            "Aggregate to department/role level."
                        )

        # GDPR compliance
        if "personal_data" in str(result).lower() and "anonymized" not in str(result).lower():
            issues.append("Personal data must be anonymized for GDPR compliance")

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

        # Check for required keys
        if "data" not in result and "results" not in result:
            issues.append("Result missing 'data' or 'results' field")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on HR results."""
        issues = []

        # Retention rate sanity
        if "retention_rate" in result:
            rate = result["retention_rate"]
            if rate > 0.99:  # > 99% retention
                issues.append(
                    f"Retention rate {rate:.0%} seems unrealistically high - verify data"
                )
            if rate < 0.5:  # < 50% retention
                issues.append(
                    f"Retention rate {rate:.0%} seems unusually low - verify data"
                )

        # Hiring pipeline sanity
        if "hiring_pipeline" in result:
            pipeline = result["hiring_pipeline"]
            if isinstance(pipeline, dict):
                if "candidates" in pipeline and "open_roles" in pipeline:
                    ratio = pipeline.get("candidates", 1) / max(
                        pipeline.get("open_roles", 1), 1
                    )
                    if ratio < 2:  # < 2 candidates per role
                        issues.append(
                            f"Candidate-to-role ratio {ratio:.1f} is thin - may face hiring challenges"
                        )

        # Cost per hire sanity
        if "cost_per_hire" in result:
            cost = result["cost_per_hire"]
            # Typical is $10K-$50K
            if cost < 5_000:
                issues.append(
                    f"Cost per hire ${cost:,.0f} seems low - may indicate incomplete costing"
                )

        return issues
