"""
legal_agent.py — Legal Department Agent Intelligence

Provides domain-specific intelligence for:
  - Contract review and analysis
  - Compliance checking
  - Risk assessment
  - IP protection
  - Dispute resolution
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


class LegalAgent(BaseAgentIntelligence):
    """Legal department agent with contract, compliance, and IP expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build legal-specific domain knowledge."""
        return DomainKnowledge(
            department="legal",
            key_concepts=[
                "contract", "agreement", "terms", "conditions", "liability",
                "compliance", "regulation", "policy", "audit", "risk",
                "intellectual_property", "patent", "trademark", "copyright",
                "dispute", "litigation", "settlement", "arbitration",
                "confidentiality", "nda", "employment", "privacy"
            ],
            keywords={
                "contract": ["contract", "agreement", "terms", "conditions"],
                "compliance": ["compliance", "regulation", "audit", "policy"],
                "risk": ["risk", "liability", "exposure", "penalty"],
                "ip": ["ip", "patent", "trademark", "copyright", "intellectual"],
                "dispute": ["dispute", "litigation", "lawsuit", "settlement"],
                "confidentiality": ["confidential", "nda", "secret", "proprietary"],
            },
            skill_rules={
                "contract_review": ["rag_search", "sql_query"],
                "compliance_check": ["rag_search", "sql_query"],
                "risk_assessment": ["rag_search", "sql_query"],
                "ip_protection": ["rag_search", "web_search"],
                "dispute": ["rag_search", "sql_query"],
            },
            validation_rules={
                "legal_review_required": True,
                "risk_score_0_1": True,
                "no_legal_advice": True,
            },
            governance_rules={
                "attorney_client_privilege": True,
                "work_product_protection": True,
                "confidentiality_required": True,
                "legal_review_sign_off": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify legal query to domain intent."""
        query_lower = query.lower()

        # Contract review
        if any(w in query_lower for w in ["contract", "agreement", "terms", "clause"]):
            return DomainIntent.CONTRACT_REVIEW

        # Compliance check
        if any(w in query_lower for w in ["compliance", "audit", "regulation", "policy"]):
            return DomainIntent.COMPLIANCE_CHECK

        # Risk assessment
        if any(w in query_lower for w in ["risk", "liability", "exposure", "penalty"]):
            return DomainIntent.RISK_ASSESSMENT

        # IP protection
        if any(w in query_lower for w in ["patent", "trademark", "copyright", "ip", "intellectual"]):
            return DomainIntent.IP_PROTECTION

        # Dispute
        if any(w in query_lower for w in ["dispute", "litigation", "lawsuit", "settlement"]):
            return DomainIntent.DISPUTE

        # Default
        return DomainIntent.CONTRACT_REVIEW

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract legal-specific entities."""
        entities = {}

        # Contract type
        if "nda" in query.lower():
            entities["contract_type"] = "nda"
        elif "msa" in query.lower():
            entities["contract_type"] = "msa"
        elif "sla" in query.lower():
            entities["contract_type"] = "sla"
        elif "employment" in query.lower():
            entities["contract_type"] = "employment"

        # Jurisdiction
        if "california" in query.lower() or "ca" in query.lower():
            entities["jurisdiction"] = "CA"
        elif "new york" in query.lower() or "ny" in query.lower():
            entities["jurisdiction"] = "NY"
        elif "delaware" in query.lower():
            entities["jurisdiction"] = "DE"

        # Risk level
        if "high" in query.lower():
            entities["risk_level"] = "high"
        elif "medium" in query.lower():
            entities["risk_level"] = "medium"
        elif "low" in query.lower():
            entities["risk_level"] = "low"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Legal rarely needs real-time data."""
        return False

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Legal rarely needs CRM."""
        return False

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Legal might need external compliance/IP/case law info."""
        return intent in [
            DomainIntent.COMPLIANCE_CHECK,
            DomainIntent.IP_PROTECTION,
            DomainIntent.DISPUTE,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """All legal queries are highly sensitive (attorney-client privilege)."""
        return True

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for legal queries."""
        clarifications = []

        # Contract review needs contract identifier
        if intent == DomainIntent.CONTRACT_REVIEW:
            clarifications.append("Contract ID or name for reference?")
            if "contract_type" not in entities:
                clarifications.append(
                    "Contract type: NDA, MSA, SLA, Employment, or other?"
                )

        # Compliance needs specific area
        if intent == DomainIntent.COMPLIANCE_CHECK:
            clarifications.append(
                "Compliance area: GDPR, CCPA, SOC2, Labor Law, or other?"
            )

        # Risk assessment needs scope
        if intent == DomainIntent.RISK_ASSESSMENT:
            clarifications.append("Scope: Contract risk, Legal risk, or Operational risk?")

        # Dispute needs party info
        if intent == DomainIntent.DISPUTE:
            clarifications.append("Parties involved and dispute status?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in legal intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if intent == DomainIntent.CONTRACT_REVIEW:
            keywords = ["contract", "agreement", "terms"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.COMPLIANCE_CHECK:
            keywords = ["compliance", "audit", "regulation"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.RISK_ASSESSMENT:
            keywords = ["risk", "liability", "exposure"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.8
        elif intent == DomainIntent.IP_PROTECTION:
            keywords = ["patent", "trademark", "copyright"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.DISPUTE:
            keywords = ["dispute", "litigation", "lawsuit"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on legal requirements."""
        adjusted = skills.copy()

        # All legal should have validation at end
        if "legal_review" not in adjusted:
            adjusted.append("legal_review")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for legal queries."""
        # If RAG fails, try SQL
        if "rag_search" in skills:
            return ["sql_query"]
        # If web search fails, try RAG
        if "web_search" in skills:
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

        if "rag_search" in skills:
            rationale += "Search legal documents, contracts, and policies. "
        if "sql_query" in skills:
            rationale += "Query legal matter database. "
        if "web_search" in skills:
            rationale += "Search external legal and compliance resources. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.CONTRACT_REVIEW:
            return "Contract summary with key terms, risks, and recommendations for review"
        elif analysis.domain_intent == DomainIntent.COMPLIANCE_CHECK:
            return "Compliance status with gaps, remediation actions, and timeline"
        elif analysis.domain_intent == DomainIntent.RISK_ASSESSMENT:
            return "Risk assessment with risk score, key exposures, and mitigation strategies"
        elif analysis.domain_intent == DomainIntent.IP_PROTECTION:
            return "IP status with patents, trademarks, copyrights, and protection gaps"
        elif analysis.domain_intent == DomainIntent.DISPUTE:
            return "Dispute analysis with parties, claims, legal positions, and strategy"

        return "Legal analysis with risks and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for legal results."""
        checks = [
            "no_null_values",
            "attorney_client_privileged",
            "work_product_protected",
            "legal_reviewed",
            "confidential_marked",
        ]

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Legal-specific validations."""
        issues = []

        # Check risk score is 0-1
        if "risk_score" in result:
            score = result["risk_score"]
            if not (0.0 <= score <= 1.0):
                issues.append(f"Risk score must be 0-1, got {score}")

        # Check legal review is documented
        if "legal_review" not in result:
            issues.append("Legal review documentation missing")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (attorney-client privilege, work product)."""
        issues = []

        # Check for confidential marking
        if "confidential" not in str(result).lower():
            issues.append("Result must be marked CONFIDENTIAL - ATTORNEY-CLIENT PRIVILEGED")

        # Check work product protection
        if "work_product" not in str(result).lower():
            issues.append("Result should reference work product protection")

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

        # Legal results must have summary
        if "summary" not in result and "analysis" not in result:
            issues.append("Result missing 'summary' or 'analysis' field")

        return issues

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Sanity checks on legal results."""
        issues = []

        # Risk score sanity
        if "risk_score" in result:
            score = result["risk_score"]
            if score > 0.9:  # > 90% risk
                issues.append(
                    f"High risk score {score:.0%} - verify this is correct severity"
                )

        return issues
