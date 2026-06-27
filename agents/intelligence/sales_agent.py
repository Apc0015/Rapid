"""
sales_agent.py — Sales Department Agent Intelligence

Provides domain-specific intelligence for:
  - Deal analysis and pipeline health
  - Customer insights and segmentation
  - Competitive threat detection
  - Deal closure prediction
  - Win/loss analysis
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


class SalesAgent(BaseAgentIntelligence):
    """Sales department agent with deal, pipeline, and customer expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build sales-specific domain knowledge."""
        return DomainKnowledge(
            department="sales",
            key_concepts=[
                "deal", "opportunity", "pipeline", "stage", "forecast",
                "customer", "account", "segment", "churn", "win_rate",
                "sales_cycle", "conversion", "quota", "territory",
                "competitor", "threat", "win_loss", "sales_velocity"
            ],
            keywords={
                "deal": ["deal", "opportunity", "prospect", "pipeline"],
                "stage": ["stage", "qualify", "proposal", "negotiation", "close"],
                "customer": ["customer", "account", "buyer", "contact", "prospect"],
                "pipeline": ["pipeline", "funnel", "forecast", "velocity"],
                "competitor": ["competitor", "competitive", "threat", "win against"],
                "churn": ["churn", "loss", "at_risk", "renewal", "retention"],
            },
            skill_rules={
                "deal_analysis": ["sql_query", "rag_search", "api_call"],
                "pipeline_health": ["sql_query", "calculation"],
                "customer_insight": ["sql_query", "rag_search", "api_call"],
                "competitive_threat": ["web_search", "rag_search", "api_call"],
                "deal_closure": ["deal_predict", "sql_query", "calculation"],
            },
            validation_rules={
                "deal_amount_positive": True,
                "probability_0_to_1": True,
                "stage_valid": True,
                "win_rate_0_to_1": True,
            },
            governance_rules={
                "no_personal_customer_data": True,
                "respect_nda": True,
                "salesforce_source_of_truth": True,
                "quote_deal_amount": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify sales query to domain intent."""
        query_lower = query.lower()

        # Deal analysis
        if any(w in query_lower for w in ["deal", "opportunity", "proposal"]):
            return DomainIntent.DEAL_ANALYSIS

        # Pipeline health
        if any(w in query_lower for w in ["pipeline", "funnel", "forecast", "velocity"]):
            return DomainIntent.PIPELINE_HEALTH

        # Customer insight
        if any(w in query_lower for w in ["customer", "account", "segment", "profile"]):
            return DomainIntent.CUSTOMER_INSIGHT

        # Competitive threat
        if any(w in query_lower for w in ["competitor", "competitive", "threat", "win against"]):
            return DomainIntent.COMPETITIVE_THREAT

        # Deal closure
        if any(w in query_lower for w in ["close", "closure", "won", "lost", "predict"]):
            return DomainIntent.DEAL_CLOSURE

        # Default
        return DomainIntent.PIPELINE_HEALTH

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract sales-specific entities."""
        entities = {}

        # Sales stage
        stages = ["prospecting", "qualify", "proposal", "negotiation", "close"]
        query_lower = query.lower()
        for stage in stages:
            if stage in query_lower:
                entities["stage"] = stage
                break

        # Deal size
        if "enterprise" in query_lower:
            entities["deal_size"] = "enterprise"
        elif "mid-market" in query_lower or "mid market" in query_lower:
            entities["deal_size"] = "mid-market"
        elif "smb" in query_lower or "small" in query_lower:
            entities["deal_size"] = "smb"

        # Territory
        if "apac" in query_lower or "asia" in query_lower:
            entities["territory"] = "APAC"
        elif "emea" in query_lower or "europe" in query_lower:
            entities["territory"] = "EMEA"
        elif "amer" in query_lower or "america" in query_lower:
            entities["territory"] = "AMER"

        # Competitor
        if "salesforce" in query_lower:
            entities["competitor"] = "salesforce"
        elif "hubspot" in query_lower:
            entities["competitor"] = "hubspot"
        elif "pipedrive" in query_lower:
            entities["competitor"] = "pipedrive"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Sales needs real-time for pipeline updates."""
        return intent in [
            DomainIntent.PIPELINE_HEALTH,
            DomainIntent.DEAL_CLOSURE,
        ]

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Almost all sales queries need CRM (Salesforce)."""
        return intent in [
            DomainIntent.DEAL_ANALYSIS,
            DomainIntent.PIPELINE_HEALTH,
            DomainIntent.CUSTOMER_INSIGHT,
            DomainIntent.DEAL_CLOSURE,
        ]

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Sales might need external competitive intelligence."""
        return intent in [
            DomainIntent.COMPETITIVE_THREAT,
            DomainIntent.CUSTOMER_INSIGHT,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Sales queries with customer data are sensitive."""
        return intent in [
            DomainIntent.CUSTOMER_INSIGHT,
            DomainIntent.DEAL_ANALYSIS,
        ]

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for sales queries."""
        clarifications = []

        # Pipeline health needs stage clarity
        if intent == DomainIntent.PIPELINE_HEALTH:
            if "stage" not in entities:
                clarifications.append(
                    "Which stage: Prospecting, Qualify, Proposal, Negotiation, or Close?"
                )

        # Deal analysis needs deal/opportunity clarity
        if intent == DomainIntent.DEAL_ANALYSIS:
            clarifications.append("Deal ID or Opportunity name for reference?")

        # Competitor analysis needs specific competitor
        if intent == DomainIntent.COMPETITIVE_THREAT:
            if "competitor" not in entities:
                clarifications.append(
                    "Which competitor: Salesforce, HubSpot, Pipedrive, or other?"
                )

        # Customer insight needs segment
        if intent == DomainIntent.CUSTOMER_INSIGHT:
            clarifications.append("Customer segment: Enterprise, Mid-Market, or SMB?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in sales intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if intent == DomainIntent.DEAL_ANALYSIS:
            keywords = ["deal", "opportunity", "proposal"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.PIPELINE_HEALTH:
            keywords = ["pipeline", "funnel", "forecast", "velocity"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.CUSTOMER_INSIGHT:
            keywords = ["customer", "account", "segment"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.COMPETITIVE_THREAT:
            keywords = ["competitor", "competitive", "threat"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.DEAL_CLOSURE:
            keywords = ["close", "closure", "predict", "win"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on sales requirements."""
        adjusted = skills.copy()

        # If needs CRM, ensure API call for Salesforce
        if analysis.requires_crm and "api_call" not in adjusted:
            adjusted.insert(0, "api_call")

        # If needs external data, add web search
        if analysis.requires_external and "web_search" not in adjusted:
            adjusted.append("web_search")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for sales queries."""
        # If CRM call fails, try SQL
        if "api_call" in skills:
            return ["sql_query", "rag_search"]
        # If deal prediction fails, try calculation
        if "deal_predict" in skills:
            return ["calculation", "sql_query"]
        # Default fallback
        return ["rag_search"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = f"For {analysis.domain_intent.value} query: "

        if "api_call" in skills:
            rationale += "Query Salesforce CRM for opportunity and account data. "
        if "sql_query" in skills:
            rationale += "Query database for sales metrics. "
        if "deal_predict" in skills:
            rationale += "Apply deal closure prediction model. "
        if "web_search" in skills:
            rationale += "Search for competitive intelligence. "
        if "calculation" in skills:
            rationale += "Calculate sales metrics (win rate, velocity). "
        if "rag_search" in skills:
            rationale += "Search sales documents and playbooks. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.DEAL_ANALYSIS:
            return "Deal summary with amount, probability, stage, and key stakeholders"
        elif analysis.domain_intent == DomainIntent.PIPELINE_HEALTH:
            return "Pipeline by stage with total value, count, and velocity metrics"
        elif analysis.domain_intent == DomainIntent.CUSTOMER_INSIGHT:
            return "Customer profile with engagement level, spend, and churn risk"
        elif analysis.domain_intent == DomainIntent.COMPETITIVE_THREAT:
            return "Competitive intelligence report with threat level and win strategy"
        elif analysis.domain_intent == DomainIntent.DEAL_CLOSURE:
            return "Deal closure prediction with probability, risk factors, and actions"

        return "Sales data with analysis and next steps"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for sales results."""
        checks = [
            "deal_amount_positive",
            "probability_0_1",
            "stage_valid",
            "no_null_values",
        ]

        if analysis.domain_intent == DomainIntent.DEAL_CLOSURE:
            checks.append("prediction_confidence")

        checks.append("salesforce_verified")

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sales-specific validations."""
        issues = []

        # Check deal amount is positive
        if "amount" in result:
            if isinstance(result["amount"], (int, float)):
                if result["amount"] < 0:
                    issues.append("Deal amount cannot be negative")

        # Check probability is 0-1
        if "probability" in result:
            prob = result["probability"]
            if not (0.0 <= prob <= 1.0):
                issues.append(f"Deal probability must be 0-1, got {prob}")

        # Check stage is valid
        valid_stages = ["prospecting", "qualify", "proposal", "negotiation", "close"]
        if "stage" in result:
            stage = result["stage"]
            if stage not in valid_stages:
                issues.append(f"Invalid stage: {stage}. Must be one of {valid_stages}")

        # Check win rate is 0-1
        if "win_rate" in result:
            rate = result["win_rate"]
            if not (0.0 <= rate <= 1.0):
                issues.append(f"Win rate must be 0-1, got {rate}")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance rules (customer data, NDA)."""
        issues = []

        # Check for customer PII
        dangerous_keys = ["email", "phone", "address", "ssn", "account_number"]
        for key in result.keys():
            if any(dk in key.lower() for dk in dangerous_keys):
                # Allow if aggregated/anonymized
                if "list" not in str(result.get(key, "")).lower():
                    issues.append(
                        f"Customer PII exposed in result: {key}. Aggregate or redact."
                    )

        # Check Salesforce is source of truth
        if "source" in result:
            if "salesforce" not in result["source"].lower():
                issues.append(
                    "For Salesforce data, must cite Salesforce as source of truth"
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

        # Check for required keys
        if "data" not in result and "results" not in result:
            issues.append("Result missing 'data' or 'results' field")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on sales results."""
        issues = []

        # Deal amount sanity
        if "amount" in result and isinstance(result["amount"], (int, float)):
            if result["amount"] > 100_000_000:  # $100M+
                issues.append(
                    f"Deal amount ${result['amount']:,.0f} seems unusually large - verify"
                )

        # Pipeline velocity sanity
        if "velocity" in result:
            velocity = result["velocity"]
            if velocity < 0.5 or velocity > 2.0:  # Less than 0.5 deals/month or more than 2
                issues.append(
                    f"Sales velocity {velocity:.2f} deals/month seems unusual - verify"
                )

        # Win rate sanity
        if "win_rate" in result:
            rate = result["win_rate"]
            if rate > 0.5:  # > 50% win rate
                issues.append(
                    f"Win rate {rate:.0%} seems high - typical is 20-30%, verify"
                )

        return issues
