"""
customer_success_agent.py — Customer Success Department Agent Intelligence

Provides domain-specific intelligence for:
  - Customer health monitoring
  - Satisfaction and NPS tracking
  - Retention risk assessment
  - Churn prediction
  - Expansion opportunity identification
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


class CustomerSuccessAgent(BaseAgentIntelligence):
    """Customer Success department agent with health, satisfaction, and retention expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build customer success-specific domain knowledge."""
        return DomainKnowledge(
            department="customer_success",
            key_concepts=[
                "customer", "health_score", "satisfaction", "nps", "csat",
                "retention", "churn", "at_risk", "expansion", "upsell",
                "engagement", "usage", "adoption", "training", "support",
                "account", "segment", "lifecycle", "onboarding"
            ],
            keywords={
                "customer": ["customer", "account", "client", "user"],
                "health": ["health", "score", "status", "at_risk"],
                "satisfaction": ["satisfaction", "satisfaction", "nps", "csat"],
                "retention": ["retention", "churn", "renewal", "risk"],
                "expansion": ["expansion", "upsell", "grow", "increase"],
                "engagement": ["engagement", "usage", "adoption", "activity"],
                "support": ["support", "ticket", "issue", "resolution"],
            },
            skill_rules={
                "customer_health": ["sql_query", "calculation", "rag_search"],
                "satisfaction_nps": ["sql_query", "calculation"],
                "retention_risk": ["sql_query", "churn_risk"],
                "churn_prediction": ["churn_risk", "sql_query"],
                "expansion_opportunity": ["sql_query", "calculation"],
            },
            validation_rules={
                "health_score_0_100": True,
                "nps_score_valid": True,
                "churn_risk_0_1": True,
            },
            governance_rules={
                "no_individual_data": True,
                "aggregate_accounts": True,
                "customer_privacy_required": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify customer success query to domain intent."""
        query_lower = query.lower()

        # Customer health (reuse FINANCIAL_HEALTH)
        if any(w in query_lower for w in ["health", "status", "score", "account"]):
            return DomainIntent.FINANCIAL_HEALTH

        # Satisfaction/NPS (reuse CAMPAIGN_PERFORMANCE for metrics)
        if any(w in query_lower for w in ["satisfaction", "nps", "csat", "score"]):
            return DomainIntent.CAMPAIGN_PERFORMANCE

        # Retention risk (reuse RETENTION_RISK)
        if any(w in query_lower for w in ["retention", "at_risk", "renewal", "maintain"]):
            return DomainIntent.RETENTION_RISK

        # Churn prediction (reuse DEAL_CLOSURE)
        if any(w in query_lower for w in ["churn", "predict", "loss", "leave"]):
            return DomainIntent.DEAL_CLOSURE

        # Expansion opportunity (reuse CUSTOMER_INSIGHT)
        if any(w in query_lower for w in ["expansion", "upsell", "grow", "increase"]):
            return DomainIntent.CUSTOMER_INSIGHT

        # Default
        return DomainIntent.FINANCIAL_HEALTH

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract customer success-specific entities."""
        entities = {}

        # Segment/tier
        if "enterprise" in query.lower():
            entities["segment"] = "enterprise"
        elif "mid-market" in query.lower() or "mid market" in query.lower():
            entities["segment"] = "mid-market"
        elif "smb" in query.lower() or "small" in query.lower():
            entities["segment"] = "smb"

        # Lifecycle stage
        if "onboarding" in query.lower():
            entities["lifecycle"] = "onboarding"
        elif "active" in query.lower():
            entities["lifecycle"] = "active"
        elif "at-risk" in query.lower() or "at_risk" in query.lower():
            entities["lifecycle"] = "at_risk"
        elif "churn" in query.lower():
            entities["lifecycle"] = "churned"

        # Metric type
        if "nps" in query.lower():
            entities["metric"] = "nps"
        elif "csat" in query.lower():
            entities["metric"] = "csat"
        elif "usage" in query.lower():
            entities["metric"] = "usage"

        # Time period
        if "month" in query.lower():
            entities["period"] = "monthly"
        elif "quarter" in query.lower():
            entities["period"] = "quarterly"
        elif "year" in query.lower():
            entities["period"] = "annual"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """CS needs real-time for customer health monitoring."""
        return True

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """CS needs CRM for customer data."""
        return True

    def _needs_external(self, intent: DomainIntent) -> bool:
        """CS rarely needs external data."""
        return False

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """CS queries with customer data are sensitive."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for CS queries."""
        clarifications = []

        # Customer health needs segment
        if intent == DomainIntent.FINANCIAL_HEALTH:
            if "segment" not in entities:
                clarifications.append("Customer segment: Enterprise, Mid-Market, or SMB?")

        # Satisfaction needs metric type
        if intent == DomainIntent.CAMPAIGN_PERFORMANCE:
            if "metric" not in entities:
                clarifications.append("Satisfaction metric: NPS, CSAT, or CES?")

        # Retention risk needs threshold
        if intent == DomainIntent.RETENTION_RISK:
            clarifications.append("Risk threshold (0-1)? Default is 0.6.")

        # Expansion opportunity needs product
        if intent == DomainIntent.CUSTOMER_INSIGHT:
            clarifications.append("Which product or feature for expansion analysis?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in CS intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if any(w in query_lower for w in ["health", "status", "account"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["satisfaction", "nps", "csat"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["retention", "at_risk", "renewal"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["churn", "predict", "leave"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["expansion", "upsell", "grow"]):
            confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on CS requirements."""
        adjusted = skills.copy()

        # CS needs real-time monitoring
        if analysis.requires_realtime and "realtime" not in adjusted:
            adjusted.insert(0, "realtime")

        # CS needs churn models for at-risk analysis
        if analysis.domain_intent == DomainIntent.RETENTION_RISK:
            if "churn_risk" not in adjusted:
                adjusted.insert(0, "churn_risk")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for CS queries."""
        # If churn model fails, try SQL
        if "churn_risk" in skills:
            return ["sql_query", "rag_search"]
        # If CRM API fails, try SQL
        if "api_call" in skills:
            return ["sql_query"]
        # Default fallback
        return ["sql_query"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = f"For {analysis.domain_intent.value} query: "

        if "sql_query" in skills:
            rationale += "Query customer database for health and engagement metrics. "
        if "churn_risk" in skills:
            rationale += "Apply churn risk prediction model. "
        if "calculation" in skills:
            rationale += "Calculate satisfaction and health scores. "
        if "rag_search" in skills:
            rationale += "Search CS playbooks and best practices. "
        if "api_call" in skills:
            rationale += "Query CRM for customer account data. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.FINANCIAL_HEALTH:
            return "Customer health score by segment with key metrics and risk indicators"
        elif analysis.domain_intent == DomainIntent.CAMPAIGN_PERFORMANCE:
            return "Satisfaction metrics (NPS/CSAT) by segment with trends"
        elif analysis.domain_intent == DomainIntent.RETENTION_RISK:
            return "At-risk customers with churn score and retention actions"
        elif analysis.domain_intent == DomainIntent.DEAL_CLOSURE:
            return "Churn prediction with risk factors and intervention strategy"
        elif analysis.domain_intent == DomainIntent.CUSTOMER_INSIGHT:
            return "Expansion opportunities by customer segment with upsell potential"

        return "Customer success data with analysis and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for CS results."""
        checks = [
            "health_score_0_100",
            "nps_score_valid",
            "churn_score_0_1",
            "no_individual_data",
            "no_null_values",
            "customer_privacy",
        ]

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """CS-specific validations."""
        issues = []

        # Check health score is 0-100
        if "health_score" in result:
            score = result["health_score"]
            if not (0 <= score <= 100):
                issues.append(f"Health score must be 0-100, got {score}")

        # Check NPS is -100 to 100
        if "nps_score" in result:
            nps = result["nps_score"]
            if not (-100 <= nps <= 100):
                issues.append(f"NPS score must be -100 to 100, got {nps}")

        # Check CSAT is 0-100
        if "csat_score" in result:
            csat = result["csat_score"]
            if not (0 <= csat <= 100):
                issues.append(f"CSAT score must be 0-100, got {csat}")

        # Check churn risk is 0-1
        if "churn_risk" in result:
            risk = result["churn_risk"]
            if not (0.0 <= risk <= 1.0):
                issues.append(f"Churn risk must be 0-1, got {risk}")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (customer privacy, no PII)."""
        issues = []

        # Check for individual customer data
        if "customers" in result and isinstance(result["customers"], list):
            if len(result["customers"]) > 0:
                if isinstance(result["customers"][0], dict):
                    customer = result["customers"][0]
                    dangerous_keys = ["email", "phone", "name", "contact"]
                    for key in customer.keys():
                        if any(dk in key.lower() for dk in dangerous_keys):
                            issues.append(
                                f"Individual customer PII exposed: {key}. Aggregate by segment."
                            )

        # Check data is aggregated
        if "data" in result and isinstance(result["data"], list):
            if "account_id" in str(result["data"]).lower():
                issues.append(
                    "Result contains account-level data - must be aggregated by segment"
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

        # CS results should have summary
        if "summary" not in result and "data" not in result:
            issues.append("Result missing 'summary' or 'data' field")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on CS results."""
        issues = []

        # Health score sanity
        if "health_score" in result:
            score = result["health_score"]
            if score > 95:  # > 95% health
                issues.append(
                    f"Health score {score:.0f} seems unrealistically high - verify"
                )
            if score < 20:  # < 20% health
                issues.append(
                    f"Health score {score:.0f} indicates critical risk - ESCALATE"
                )

        # NPS sanity
        if "nps_score" in result:
            nps = result["nps_score"]
            if nps > 80:  # > 80 NPS
                issues.append(
                    f"NPS {nps} is very high (only top companies) - verify methodology"
                )

        # Churn rate sanity
        if "monthly_churn_rate" in result:
            churn = result["monthly_churn_rate"]
            if churn > 0.3:  # > 30% monthly churn
                issues.append(
                    f"Monthly churn {churn:.0%} is very high - CRISIS SITUATION"
                )

        return issues
