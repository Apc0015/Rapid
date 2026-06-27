"""
marketing_agent.py — Marketing Department Agent Intelligence

Provides domain-specific intelligence for:
  - Campaign performance analysis
  - Customer engagement tracking
  - Brand health monitoring
  - Market trends and competitive intelligence
  - Marketing ROI analysis
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


class MarketingAgent(BaseAgentIntelligence):
    """Marketing department agent with campaign, engagement, and brand expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build marketing-specific domain knowledge."""
        return DomainKnowledge(
            department="marketing",
            key_concepts=[
                "campaign", "performance", "roi", "conversion", "funnel",
                "customer", "segment", "engagement", "retention", "acquisition",
                "brand", "awareness", "sentiment", "health", "positioning",
                "market", "trends", "competitor", "intelligence", "analysis",
                "content", "channel", "email", "social", "advertising"
            ],
            keywords={
                "campaign": ["campaign", "promotion", "initiative", "launch"],
                "performance": ["roi", "conversion", "ctr", "impression", "engagement"],
                "customer": ["customer", "segment", "cohort", "behavior"],
                "brand": ["brand", "awareness", "sentiment", "positioning"],
                "market": ["market", "trend", "opportunity", "competitive"],
                "content": ["content", "blog", "webinar", "whitepaper"],
            },
            skill_rules={
                "campaign_performance": ["sql_query", "calculation", "web_search"],
                "customer_engagement": ["sql_query", "rag_search", "calculation"],
                "brand_health": ["web_search", "rag_search", "calculation"],
                "market_trends": ["web_search", "rag_search"],
                "competitor_intelligence": ["web_search", "rag_search", "competitor"],
            },
            validation_rules={
                "conversion_0_to_1": True,
                "roi_reasonableness": True,
                "no_negative_ctr": True,
            },
            governance_rules={
                "no_individual_customer_data": True,
                "aggregate_segments": True,
                "respect_privacy": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify marketing query to domain intent."""
        query_lower = query.lower()

        # Campaign performance
        if any(w in query_lower for w in ["campaign", "promotion", "roi", "conversion"]):
            return DomainIntent.CAMPAIGN_PERFORMANCE

        # Customer engagement
        if any(w in query_lower for w in ["engagement", "retention", "acquisition", "segment"]):
            return DomainIntent.CUSTOMER_ENGAGEMENT

        # Brand health
        if any(w in query_lower for w in ["brand", "awareness", "sentiment", "positioning"]):
            return DomainIntent.BRAND_HEALTH

        # Market trends
        if any(w in query_lower for w in ["market", "trend", "opportunity", "growth"]):
            return DomainIntent.MARKET_TRENDS

        # Competitor intelligence
        if any(w in query_lower for w in ["competitor", "competitive", "benchmark"]):
            return DomainIntent.COMPETITOR_INTELLIGENCE

        # Default
        return DomainIntent.CAMPAIGN_PERFORMANCE

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract marketing-specific entities."""
        entities = {}

        # Channel
        channels = ["email", "social", "web", "paid", "organic", "direct"]
        query_lower = query.lower()
        for channel in channels:
            if channel in query_lower:
                entities["channel"] = channel
                break

        # Campaign type
        if "webinar" in query_lower:
            entities["campaign_type"] = "webinar"
        elif "whitepaper" in query_lower:
            entities["campaign_type"] = "whitepaper"
        elif "event" in query_lower:
            entities["campaign_type"] = "event"

        # Time period
        if "month" in query_lower:
            entities["period"] = "monthly"
        elif "quarter" in query_lower:
            entities["period"] = "quarterly"
        elif "year" in query_lower:
            entities["period"] = "annual"

        # Customer segment
        if "enterprise" in query_lower:
            entities["segment"] = "enterprise"
        elif "mid-market" in query_lower:
            entities["segment"] = "mid-market"
        elif "smb" in query_lower:
            entities["segment"] = "smb"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Marketing needs real-time for engagement and sentiment monitoring."""
        return intent in [
            DomainIntent.CUSTOMER_ENGAGEMENT,
            DomainIntent.BRAND_HEALTH,
        ]

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Marketing might need CRM for customer segments."""
        return intent == DomainIntent.CUSTOMER_ENGAGEMENT

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Marketing needs external data for market trends and competitive intelligence."""
        return intent in [
            DomainIntent.MARKET_TRENDS,
            DomainIntent.COMPETITOR_INTELLIGENCE,
            DomainIntent.BRAND_HEALTH,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Marketing queries with customer segments are sensitive."""
        return intent == DomainIntent.CUSTOMER_ENGAGEMENT

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for marketing queries."""
        clarifications = []

        # Campaign needs channel/type
        if intent == DomainIntent.CAMPAIGN_PERFORMANCE:
            if "channel" not in entities:
                clarifications.append(
                    "Campaign channel: Email, Social, Web, Paid, or Organic?"
                )

        # Engagement needs segment
        if intent == DomainIntent.CUSTOMER_ENGAGEMENT:
            if "segment" not in entities:
                clarifications.append("Customer segment: Enterprise, Mid-Market, or SMB?")

        # Brand health needs markets
        if intent == DomainIntent.BRAND_HEALTH:
            clarifications.append("Specific markets or regions to track?")

        # Market trends needs industry
        if intent == DomainIntent.MARKET_TRENDS:
            clarifications.append("Industry or market segment to analyze?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in marketing intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if intent == DomainIntent.CAMPAIGN_PERFORMANCE:
            keywords = ["campaign", "roi", "conversion"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.CUSTOMER_ENGAGEMENT:
            keywords = ["engagement", "retention", "segment"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.BRAND_HEALTH:
            keywords = ["brand", "awareness", "sentiment"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.MARKET_TRENDS:
            keywords = ["market", "trend", "growth"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.8
        elif intent == DomainIntent.COMPETITOR_INTELLIGENCE:
            keywords = ["competitor", "competitive", "benchmark"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on marketing requirements."""
        adjusted = skills.copy()

        # If needs external, prioritize web search
        if analysis.requires_external and "web_search" not in adjusted:
            adjusted.insert(0, "web_search")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for marketing queries."""
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
        rationale = f"For {analysis.domain_intent.value} query: "

        if "sql_query" in skills:
            rationale += "Query marketing database for campaign and customer data. "
        if "web_search" in skills:
            rationale += "Search for market trends and competitive intelligence. "
        if "calculation" in skills:
            rationale += "Calculate marketing metrics (ROI, conversion rate). "
        if "rag_search" in skills:
            rationale += "Search marketing documents and best practices. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.CAMPAIGN_PERFORMANCE:
            return "Campaign metrics by channel with impressions, clicks, conversions, and ROI"
        elif analysis.domain_intent == DomainIntent.CUSTOMER_ENGAGEMENT:
            return "Customer engagement by segment with retention rate and churn risk"
        elif analysis.domain_intent == DomainIntent.BRAND_HEALTH:
            return "Brand health metrics with awareness, sentiment, and perception trends"
        elif analysis.domain_intent == DomainIntent.MARKET_TRENDS:
            return "Market trends and growth opportunities with size and competitive landscape"
        elif analysis.domain_intent == DomainIntent.COMPETITOR_INTELLIGENCE:
            return "Competitive analysis with positioning, features, pricing, and strengths/weaknesses"

        return "Marketing data with analysis and recommendations"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for marketing results."""
        checks = [
            "conversion_0_1",
            "roi_positive",
            "no_negative_metrics",
            "no_null_values",
        ]

        if analysis.domain_intent == DomainIntent.CUSTOMER_ENGAGEMENT:
            checks.append("aggregated_segments")

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Marketing-specific validations."""
        issues = []

        # Check conversion rate is 0-1
        if "conversion_rate" in result:
            rate = result["conversion_rate"]
            if not (0.0 <= rate <= 1.0):
                issues.append(f"Conversion rate must be 0-1, got {rate}")

        # Check ROI is reasonable
        if "roi" in result:
            roi = result["roi"]
            if roi < -1.0:  # Loss > 100%
                issues.append(f"ROI {roi:.0%} indicates total loss - verify accuracy")

        # Check CTR is 0-1
        if "click_through_rate" in result:
            ctr = result["click_through_rate"]
            if not (0.0 <= ctr <= 1.0):
                issues.append(f"Click-through rate must be 0-1, got {ctr}")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (customer privacy)."""
        issues = []

        # Check for individual customer data
        if "customers" in result and isinstance(result["customers"], list):
            if len(result["customers"]) > 0:
                issues.append(
                    "Result contains individual customer data - must be aggregated by segment"
                )

        # Check for email addresses or personal info
        dangerous_keys = ["email", "phone", "contact", "personal"]
        for key in result.keys():
            if any(dk in key.lower() for dk in dangerous_keys):
                issues.append(f"Customer PII exposed: {key}. Aggregate or remove.")

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
        """Sanity checks on marketing results."""
        issues = []

        # Conversion rate sanity
        if "conversion_rate" in result:
            rate = result["conversion_rate"]
            if rate > 0.5:  # > 50% conversion
                issues.append(
                    f"Conversion rate {rate:.0%} seems unusually high - verify data"
                )

        # ROI sanity
        if "roi" in result:
            roi = result["roi"]
            if roi > 10.0:  # > 1000% ROI
                issues.append(f"ROI {roi:.0%} seems unusually high - verify calculations")

        # Campaign cost sanity
        if "campaign_cost" in result:
            cost = result["campaign_cost"]
            if cost > 100_000_000:  # > $100M
                issues.append(f"Campaign cost ${cost:,.0f} seems very high - verify")

        return issues
