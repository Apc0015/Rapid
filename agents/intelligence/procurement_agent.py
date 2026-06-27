"""
procurement_agent.py — Procurement Department Agent Intelligence

Provides domain-specific intelligence for:
  - Vendor management and evaluation
  - Cost control and negotiation
  - Contract terms and compliance
  - Spend analysis
  - Supply chain optimization
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


class ProcurementAgent(BaseAgentIntelligence):
    """Procurement department agent with vendor, cost, and supply chain expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build procurement-specific domain knowledge."""
        return DomainKnowledge(
            department="procurement",
            key_concepts=[
                "vendor", "supplier", "contract", "purchase_order", "invoice",
                "cost", "price", "discount", "negotiation", "terms",
                "spend", "category", "compliance", "audit", "quality",
                "delivery", "lead_time", "inventory", "supply_chain"
            ],
            keywords={
                "vendor": ["vendor", "supplier", "partner", "provider"],
                "cost": ["cost", "price", "discount", "negotiation"],
                "contract": ["contract", "terms", "agreement", "sla"],
                "spend": ["spend", "expense", "purchase", "invoice"],
                "supply": ["supply", "delivery", "lead_time", "inventory"],
                "compliance": ["compliance", "audit", "quality", "certification"],
            },
            skill_rules={
                "vendor_management": ["sql_query", "rag_search", "api_call"],
                "cost_control": ["sql_query", "calculation"],
                "contract_terms": ["rag_search", "sql_query"],
                "spend_analysis": ["sql_query", "calculation"],
                "supply_chain": ["sql_query", "rag_search"],
            },
            validation_rules={
                "cost_positive": True,
                "discount_0_to_100": True,
                "contract_signed": True,
            },
            governance_rules={
                "contract_required": True,
                "vendor_verification": True,
                "spend_audit_trail": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify procurement query to domain intent."""
        query_lower = query.lower()

        # Vendor management (reuse CUSTOMER_INSIGHT for vendor evaluation)
        if any(w in query_lower for w in ["vendor", "supplier", "partner", "evaluate"]):
            return DomainIntent.CUSTOMER_INSIGHT

        # Cost control (reuse COST_REDUCTION)
        if any(w in query_lower for w in ["cost", "price", "negotiation", "discount"]):
            return DomainIntent.COST_REDUCTION

        # Contract terms (reuse CONTRACT_REVIEW)
        if any(w in query_lower for w in ["contract", "terms", "agreement", "sla"]):
            return DomainIntent.CONTRACT_REVIEW

        # Spend analysis (reuse REVENUE_ANALYSIS pattern)
        if any(w in query_lower for w in ["spend", "expense", "category", "analysis"]):
            return DomainIntent.REVENUE_ANALYSIS

        # Supply chain optimization (reuse PROCESS_OPTIMIZATION)
        if any(w in query_lower for w in ["supply", "delivery", "lead_time", "inventory"]):
            return DomainIntent.PROCESS_OPTIMIZATION

        # Default
        return DomainIntent.CUSTOMER_INSIGHT

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract procurement-specific entities."""
        entities = {}

        # Spend category
        categories = ["software", "hardware", "services", "materials", "consulting"]
        query_lower = query.lower()
        for cat in categories:
            if cat in query_lower:
                entities["category"] = cat
                break

        # Vendor name (common vendors)
        vendors = ["aws", "microsoft", "google", "salesforce", "oracle"]
        for vendor in vendors:
            if vendor in query_lower:
                entities["vendor"] = vendor
                break

        # Contract status
        if "active" in query_lower:
            entities["contract_status"] = "active"
        elif "expired" in query_lower:
            entities["contract_status"] = "expired"
        elif "renew" in query_lower:
            entities["contract_status"] = "renewal"

        # Time period
        if "quarter" in query_lower:
            entities["period"] = "quarterly"
        elif "year" in query_lower:
            entities["period"] = "annual"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Procurement needs real-time for spend tracking."""
        return True

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Procurement rarely needs CRM."""
        return False

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Procurement might need external vendor databases."""
        return intent == DomainIntent.CUSTOMER_INSIGHT

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Procurement queries can expose vendor contracts and pricing."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for procurement queries."""
        clarifications = []

        if intent == DomainIntent.CUSTOMER_INSIGHT:  # Vendor management
            if "vendor" not in entities:
                clarifications.append("Specific vendor to evaluate?")

        if intent == DomainIntent.COST_REDUCTION:
            if "category" not in entities:
                clarifications.append(
                    "Spend category: Software, Hardware, Services, or Materials?"
                )

        if intent == DomainIntent.PROCESS_OPTIMIZATION:  # Supply chain
            clarifications.append("Optimize delivery, inventory, or both?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in procurement intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if any(w in query_lower for w in ["vendor", "supplier", "partner"]):
            confidence = 0.9
        elif any(w in query_lower for w in ["cost", "price", "negotiation"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["contract", "terms", "sla"]):
            confidence = 0.85
        elif any(w in query_lower for w in ["spend", "expense", "category"]):
            confidence = 0.8
        elif any(w in query_lower for w in ["supply", "delivery", "inventory"]):
            confidence = 0.8

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on procurement requirements."""
        adjusted = skills.copy()

        # For all procurement, validation is critical
        if "validation_check" not in adjusted:
            adjusted.append("validation_check")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for procurement queries."""
        # If SQL fails, try RAG
        if "sql_query" in skills:
            return ["rag_search"]
        # If API fails, try SQL
        if "api_call" in skills:
            return ["sql_query"]
        # Default fallback
        return ["rag_search"]

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        rationale = "For procurement query: "

        if "sql_query" in skills:
            rationale += "Query procurement database for vendor and spend data. "
        if "calculation" in skills:
            rationale += "Calculate spend metrics and cost analysis. "
        if "rag_search" in skills:
            rationale += "Search contracts and procurement policies. "
        if "api_call" in skills:
            rationale += "Query vendor systems and databases. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        return "Procurement data with vendor status, contract terms, spend metrics, and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for procurement results."""
        checks = [
            "cost_positive",
            "discount_0_100",
            "contract_verified",
            "no_null_values",
            "vendor_verified",
        ]

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Procurement-specific validations."""
        issues = []

        # Check cost is positive
        if "cost" in result:
            if isinstance(result["cost"], (int, float)):
                if result["cost"] < 0:
                    issues.append("Vendor cost cannot be negative")

        # Check discount is 0-100
        if "discount_percent" in result:
            discount = result["discount_percent"]
            if not (0 <= discount <= 100):
                issues.append(f"Discount must be 0-100%, got {discount}")

        # Check contract exists
        if "has_contract" in result:
            if result["has_contract"] == False:
                issues.append("Vendor contract is required before engagement")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (vendor verification, contract status)."""
        issues = []

        # Check vendor is verified
        if "vendor_verified" not in result:
            issues.append("Vendor must be verified before engagement")

        # Check contract is signed
        if "contract_signed" not in result:
            issues.append("Contract signature and effective date required")

        # Check spend has audit trail
        if "spend" in result:
            if "audit_trail" not in result:
                issues.append("Spend must have audit trail")

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

        # Procurement results must have vendor info
        if "vendor" not in result and "vendors" not in result:
            issues.append("Result missing vendor information")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on procurement results."""
        issues = []

        # Cost sanity
        if "cost" in result and isinstance(result["cost"], (int, float)):
            if result["cost"] > 1_000_000_000:  # > $1B
                issues.append(
                    f"Vendor cost ${result['cost']:,.0f} seems very large - verify"
                )

        # Discount sanity
        if "discount_percent" in result:
            discount = result["discount_percent"]
            if discount > 80:  # > 80% discount
                issues.append(
                    f"Discount {discount:.0f}% seems unusually high - verify legitimacy"
                )

        # Lead time sanity
        if "lead_time_days" in result:
            lead = result["lead_time_days"]
            if lead > 365:  # > 1 year
                issues.append(
                    f"Lead time {lead} days is very long - consider alternative vendors"
                )

        return issues
