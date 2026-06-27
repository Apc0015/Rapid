"""
finance_agent.py — Finance Department Agent Intelligence

Provides domain-specific intelligence for:
  - Revenue analysis and forecasting
  - Budget planning and variance analysis
  - Fraud detection and risk assessment
  - Financial health scoring
  - Profitability analysis
"""

import logging
from typing import Any, Dict, List
from datetime import datetime

from agents.intelligence.base_agent_intelligence import (
    BaseAgentIntelligence,
    DomainIntent,
    DomainKnowledge,
    QueryAnalysis,
    SkillPlan,
)
from agents.capabilities import CapabilityEngine, QueryIntent

logger = logging.getLogger(__name__)


class FinanceAgent(BaseAgentIntelligence):
    """Finance department agent with revenue, budget, and fraud expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build finance-specific domain knowledge."""
        return DomainKnowledge(
            department="finance",
            key_concepts=[
                "revenue", "cost", "margin", "profit", "cash_flow",
                "budget", "forecast", "variance", "expense", "headcount_cost",
                "fraud_risk", "compliance", "audit", "tax", "valuation"
            ],
            keywords={
                "revenue": ["revenue", "sales", "income", "top_line", "arr", "mrr"],
                "cost": ["cost", "expense", "cogs", "opex", "capex"],
                "margin": ["margin", "gm", "ebitda", "ebit", "net_margin"],
                "budget": ["budget", "allocation", "spend", "p&l", "forecast"],
                "fraud": ["fraud", "anomaly", "unusual", "suspicious", "red_flag"],
                "cash": ["cash", "cash_flow", "liquidity", "burn_rate", "runway"],
            },
            skill_rules={
                "revenue_analysis": ["sql_query", "rag_search", "calculation"],
                "budget_planning": ["sql_query", "calculation", "forecast_rev"],
                "fraud_detection_intent": ["sql_query", "fraud_detect"],
                "forecasting": ["forecast_rev", "calculation"],
                "financial_health": ["sql_query", "calculation", "rag_search"],
            },
            validation_rules={
                "revenue_must_be_positive": True,
                "margin_0_to_100": True,
                "variance_within_budget": True,
                "fraud_score_0_to_1": True,
            },
            governance_rules={
                "no_personal_compensation": True,
                "no_employee_salaries": True,
                "audit_trail_required": True,
                "must_cite_source": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify finance query to domain intent."""
        query_lower = query.lower()

        # Revenue analysis
        if any(w in query_lower for w in ["revenue", "sales", "income", "top_line"]):
            return DomainIntent.REVENUE_ANALYSIS

        # Budget planning
        if any(w in query_lower for w in ["budget", "allocation", "spending", "forecast"]):
            return DomainIntent.BUDGET_PLANNING

        # Fraud detection
        if any(w in query_lower for w in ["fraud", "anomaly", "unusual", "suspicious"]):
            return DomainIntent.FRAUD_DETECTION_INTENT

        # Forecasting
        if any(w in query_lower for w in ["forecast", "predict", "projection", "outlook"]):
            return DomainIntent.FORECASTING

        # Financial health
        if any(w in query_lower for w in ["health", "performance", "status", "metrics"]):
            return DomainIntent.FINANCIAL_HEALTH

        # Default
        return DomainIntent.REVENUE_ANALYSIS

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract finance-specific entities."""
        entities = {}

        # Time period
        if "q1" in query.lower():
            entities["period"] = "Q1"
        elif "q2" in query.lower():
            entities["period"] = "Q2"
        elif "q3" in query.lower():
            entities["period"] = "Q3"
        elif "q4" in query.lower():
            entities["period"] = "Q4"
        elif "year" in query.lower() or "annual" in query.lower():
            entities["period"] = "YEAR"
        else:
            entities["period"] = "CURRENT"

        # Department
        if "sales" in query.lower():
            entities["department"] = "sales"
        elif "marketing" in query.lower():
            entities["department"] = "marketing"
        elif "ops" in query.lower() or "operations" in query.lower():
            entities["department"] = "operations"
        elif "engineering" in query.lower():
            entities["department"] = "engineering"

        # Metric type
        if intent == DomainIntent.REVENUE_ANALYSIS:
            entities["metric"] = "revenue"
        elif intent == DomainIntent.BUDGET_PLANNING:
            entities["metric"] = "budget"
        elif intent == DomainIntent.FRAUD_DETECTION_INTENT:
            entities["metric"] = "fraud_score"
        elif intent == DomainIntent.FORECASTING:
            entities["metric"] = "forecast"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Finance needs real-time for fraud detection and cash flow monitoring."""
        return intent in [
            DomainIntent.FRAUD_DETECTION_INTENT,
            DomainIntent.FINANCIAL_HEALTH,
        ]

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Finance queries rarely need CRM (except customer-based revenue)."""
        return intent == DomainIntent.REVENUE_ANALYSIS

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Finance queries might need external market data or compliance info."""
        return intent in [
            DomainIntent.FORECASTING,
            DomainIntent.FINANCIAL_HEALTH,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Finance always handles sensitive financial data."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for finance queries."""
        clarifications = []

        # Missing period
        if intent in [DomainIntent.REVENUE_ANALYSIS, DomainIntent.BUDGET_PLANNING]:
            if entities.get("period") == "CURRENT":
                clarifications.append("Which period: Q1, Q2, Q3, Q4, or YTD?")

        # Missing department
        if intent == DomainIntent.REVENUE_ANALYSIS:
            if "department" not in entities:
                clarifications.append(
                    "Revenue from which department: Sales, Marketing, or all?"
                )

        # Fraud detection needs threshold
        if intent == DomainIntent.FRAUD_DETECTION_INTENT:
            clarifications.append(
                "What fraud score threshold (0.0-1.0)? Default is 0.7."
            )

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in finance intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        # Check keyword match
        if intent == DomainIntent.REVENUE_ANALYSIS:
            keywords = ["revenue", "sales", "income"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.BUDGET_PLANNING:
            keywords = ["budget", "allocation", "spending"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.FRAUD_DETECTION_INTENT:
            keywords = ["fraud", "anomaly", "suspicious"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.FORECASTING:
            keywords = ["forecast", "predict", "projection"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on finance requirements."""
        adjusted = skills.copy()

        # If needs real-time monitoring, add realtime check
        if analysis.requires_realtime and "realtime_monitor" not in adjusted:
            adjusted.insert(0, "realtime_monitor")

        # If sensitive, ensure validation is included
        if analysis.is_sensitive and "validation_check" not in adjusted:
            adjusted.append("validation_check")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for finance queries."""
        # If SQL fails, try RAG
        if "sql_query" in skills:
            return ["rag_search", "calculation"]
        # If forecast fails, try calculation
        if "forecast_rev" in skills:
            return ["calculation", "rag_search"]
        # Default fallback
        return ["calculation"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = f"For {analysis.domain_intent.value} query: "

        if "sql_query" in skills:
            rationale += "Query database for structured financial data. "
        if "forecast_rev" in skills:
            rationale += "Apply revenue forecasting model. "
        if "fraud_detect" in skills:
            rationale += "Detect anomalies in financial transactions. "
        if "calculation" in skills:
            rationale += "Perform financial calculations (margins, ratios). "
        if "rag_search" in skills:
            rationale += "Search financial documents and policies. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.REVENUE_ANALYSIS:
            return "Revenue breakdown by period, department, and product line with YoY comparison"
        elif analysis.domain_intent == DomainIntent.BUDGET_PLANNING:
            return "Budget allocation plan with variance analysis and headroom"
        elif analysis.domain_intent == DomainIntent.FRAUD_DETECTION_INTENT:
            return "Transaction anomalies with fraud score and risk level"
        elif analysis.domain_intent == DomainIntent.FORECASTING:
            return "Revenue forecast with confidence intervals and key assumptions"
        elif analysis.domain_intent == DomainIntent.FINANCIAL_HEALTH:
            return "Financial health metrics: margin, cash_flow, burn_rate, runway"

        return "Financial data with analysis and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for finance results."""
        checks = [
            "revenue_positive",
            "margin_range_0_100",
            "no_null_values",
        ]

        if analysis.domain_intent == DomainIntent.FRAUD_DETECTION_INTENT:
            checks.append("fraud_score_0_1")

        if analysis.domain_intent == DomainIntent.BUDGET_PLANNING:
            checks.append("variance_within_tolerance")

        checks.append("source_cited")

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Finance-specific validations."""
        issues = []

        # Check revenue is positive
        if "revenue" in result:
            if isinstance(result["revenue"], (int, float)):
                if result["revenue"] < 0:
                    issues.append("Revenue cannot be negative")

        # Check margin is 0-100
        if "margin" in result:
            margin = result["margin"]
            if not (0 <= margin <= 100):
                issues.append(f"Margin must be 0-100, got {margin}")

        # Check fraud score is 0-1
        if "fraud_score" in result:
            score = result["fraud_score"]
            if not (0.0 <= score <= 1.0):
                issues.append(f"Fraud score must be 0-1, got {score}")

        # Check forecast confidence
        if "forecast" in result:
            if "confidence" in result["forecast"]:
                conf = result["forecast"]["confidence"]
                if not (0.0 <= conf <= 1.0):
                    issues.append("Forecast confidence must be 0-1")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance rules (PII, audit trail)."""
        issues = []

        # Check for employee salaries (PII)
        dangerous_keys = ["salary", "compensation", "personal_income", "individual_pay"]
        for key in result.keys():
            if any(dk in key.lower() for dk in dangerous_keys):
                issues.append(f"Sensitive employee data exposed: {key}")

        # Check source is cited
        if "source" not in result:
            issues.append("Source must be cited for financial data")

        # Check audit metadata
        if analysis.is_sensitive and "audit_timestamp" not in result:
            issues.append("Audit timestamp required for sensitive financial data")

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

        # Check for metadata
        if "metadata" not in result:
            issues.append("Result missing metadata (timestamp, source)")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on finance results."""
        issues = []

        # Revenue sanity check
        if "revenue" in result and isinstance(result["revenue"], (int, float)):
            # Check it's not suspiciously large/small
            if result["revenue"] > 10_000_000_000:  # $10B+
                issues.append(
                    f"Revenue {result['revenue']} seems unusually high - verify data"
                )
            if result["revenue"] < 1000 and analysis.domain_intent == DomainIntent.REVENUE_ANALYSIS:
                issues.append(
                    f"Revenue {result['revenue']} seems unusually low - verify data"
                )

        # Forecast reasonableness
        if "forecast" in result:
            forecast = result["forecast"]
            if "growth_rate" in forecast:
                rate = forecast["growth_rate"]
                if rate > 1.0:  # > 100% growth
                    issues.append(
                        f"Growth rate {rate:.0%} seems aggressive - check assumptions"
                    )

        return issues
