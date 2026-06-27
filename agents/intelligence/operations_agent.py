"""
operations_agent.py — Operations Department Agent Intelligence

Provides domain-specific intelligence for:
  - Process optimization
  - Quality improvement
  - Cost reduction
  - Capacity planning
  - Efficiency metrics
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


class OperationsAgent(BaseAgentIntelligence):
    """Operations department agent with process, quality, and efficiency expertise."""

    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build operations-specific domain knowledge."""
        return DomainKnowledge(
            department="operations",
            key_concepts=[
                "process", "workflow", "efficiency", "quality", "metric",
                "cost", "waste", "cycle_time", "throughput", "capacity",
                "sla", "uptime", "availability", "reliability", "performance",
                "inventory", "supply_chain", "vendor", "outsourcing"
            ],
            keywords={
                "process": ["process", "workflow", "procedure", "automation"],
                "quality": ["quality", "defect", "error", "issue", "rework"],
                "cost": ["cost", "expense", "spend", "savings", "reduction"],
                "capacity": ["capacity", "utilization", "resources", "bottleneck"],
                "performance": ["performance", "metric", "efficiency", "throughput"],
                "supply": ["supply", "inventory", "vendor", "procurement"],
            },
            skill_rules={
                "process_optimization": ["sql_query", "calculation", "rag_search"],
                "quality_improvement": ["sql_query", "calculation"],
                "cost_reduction": ["sql_query", "calculation"],
                "capacity_planning": ["sql_query", "calculation", "forecast_rev"],
                "efficiency": ["sql_query", "calculation"],
            },
            validation_rules={
                "efficiency_0_to_100": True,
                "cost_positive": True,
                "cycle_time_positive": True,
            },
            governance_rules={
                "cost_must_be_cited": True,
                "benchmarks_required": True,
            },
        )

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify operations query to domain intent."""
        query_lower = query.lower()

        # Process optimization
        if any(w in query_lower for w in ["process", "workflow", "automation", "optimize"]):
            return DomainIntent.PROCESS_OPTIMIZATION

        # Quality improvement
        if any(w in query_lower for w in ["quality", "defect", "error", "issue", "improve"]):
            return DomainIntent.QUALITY_IMPROVEMENT

        # Cost reduction
        if any(w in query_lower for w in ["cost", "savings", "reduction", "expense"]):
            return DomainIntent.COST_REDUCTION

        # Capacity planning
        if any(w in query_lower for w in ["capacity", "utilization", "bottleneck", "resource"]):
            return DomainIntent.CAPACITY_PLANNING

        # Efficiency
        if any(w in query_lower for w in ["efficiency", "throughput", "performance", "metrics"]):
            return DomainIntent.EFFICIENCY

        # Default
        return DomainIntent.PROCESS_OPTIMIZATION

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract operations-specific entities."""
        entities = {}

        # Department/area
        if "fulfillment" in query.lower():
            entities["area"] = "fulfillment"
        elif "customer_service" in query.lower() or "support" in query.lower():
            entities["area"] = "support"
        elif "manufacturing" in query.lower():
            entities["area"] = "manufacturing"
        elif "warehouse" in query.lower():
            entities["area"] = "warehouse"

        # Metric type
        if "sla" in query.lower():
            entities["metric"] = "sla"
        elif "uptime" in query.lower():
            entities["metric"] = "uptime"
        elif "latency" in query.lower():
            entities["metric"] = "latency"
        elif "throughput" in query.lower():
            entities["metric"] = "throughput"

        # Time frame
        if "daily" in query.lower():
            entities["period"] = "daily"
        elif "weekly" in query.lower():
            entities["period"] = "weekly"
        elif "monthly" in query.lower():
            entities["period"] = "monthly"

        return entities

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Operations needs real-time for performance monitoring."""
        return intent in [
            DomainIntent.EFFICIENCY,
            DomainIntent.QUALITY_IMPROVEMENT,
        ]

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Operations might need customer data for SLA analysis."""
        return intent == DomainIntent.EFFICIENCY

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Operations might need external benchmarks."""
        return intent in [
            DomainIntent.PROCESS_OPTIMIZATION,
            DomainIntent.COST_REDUCTION,
        ]

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Operations queries can expose customer or internal data."""
        return intent == DomainIntent.EFFICIENCY

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """Ask clarifying questions for operations queries."""
        clarifications = []

        # Process optimization needs area
        if intent == DomainIntent.PROCESS_OPTIMIZATION:
            if "area" not in entities:
                clarifications.append(
                    "Which area: Fulfillment, Support, Manufacturing, or Warehouse?"
                )

        # Quality improvement needs specific metric
        if intent == DomainIntent.QUALITY_IMPROVEMENT:
            clarifications.append("Quality metric: Defect rate, Error rate, or SLA compliance?")

        # Cost reduction needs category
        if intent == DomainIntent.COST_REDUCTION:
            clarifications.append("Cost category: Labor, Materials, or Infrastructure?")

        # Capacity planning needs resource type
        if intent == DomainIntent.CAPACITY_PLANNING:
            clarifications.append("Resource type: Headcount, Equipment, or Infrastructure?")

        return clarifications

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in operations intent classification."""
        query_lower = query.lower()
        confidence = 0.5

        if intent == DomainIntent.PROCESS_OPTIMIZATION:
            keywords = ["process", "workflow", "automation", "optimize"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.QUALITY_IMPROVEMENT:
            keywords = ["quality", "defect", "error"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.COST_REDUCTION:
            keywords = ["cost", "savings", "reduction"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.9
        elif intent == DomainIntent.CAPACITY_PLANNING:
            keywords = ["capacity", "utilization", "bottleneck"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.85
        elif intent == DomainIntent.EFFICIENCY:
            keywords = ["efficiency", "throughput", "performance"]
            if any(kw in query_lower for kw in keywords):
                confidence = 0.8

        return confidence

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skills based on operations requirements."""
        adjusted = skills.copy()

        # For cost analysis, ensure calculation is included
        if analysis.domain_intent == DomainIntent.COST_REDUCTION:
            if "calculation" not in adjusted:
                adjusted.append("calculation")

        return adjusted

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills for operations queries."""
        # If SQL fails, try calculation or RAG
        if "sql_query" in skills:
            return ["calculation", "rag_search"]
        # If forecast fails, try calculation
        if "forecast_rev" in skills:
            return ["calculation"]
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
            rationale += "Query operations database for process and performance data. "
        if "calculation" in skills:
            rationale += "Calculate operations metrics (efficiency, cost per unit). "
        if "forecast_rev" in skills:
            rationale += "Forecast capacity needs and resource planning. "
        if "rag_search" in skills:
            rationale += "Search operations procedures and best practices. "

        return rationale.strip()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe expected output format."""
        if analysis.domain_intent == DomainIntent.PROCESS_OPTIMIZATION:
            return "Process analysis with bottlenecks, inefficiencies, and optimization opportunities"
        elif analysis.domain_intent == DomainIntent.QUALITY_IMPROVEMENT:
            return "Quality metrics with defect/error rates, trends, and improvement actions"
        elif analysis.domain_intent == DomainIntent.COST_REDUCTION:
            return "Cost analysis with spend by category and savings opportunities"
        elif analysis.domain_intent == DomainIntent.CAPACITY_PLANNING:
            return "Capacity forecast with utilization projections and resource needs"
        elif analysis.domain_intent == DomainIntent.EFFICIENCY:
            return "Efficiency metrics with throughput, cycle time, and utilization rates"

        return "Operations data with analysis and improvements"

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get validation checks for operations results."""
        checks = [
            "cost_positive",
            "efficiency_0_100",
            "cycle_time_positive",
            "no_null_values",
        ]

        if analysis.domain_intent == DomainIntent.COST_REDUCTION:
            checks.append("cost_cited")

        return checks

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Operations-specific validations."""
        issues = []

        # Check efficiency is 0-100
        if "efficiency" in result:
            eff = result["efficiency"]
            if not (0 <= eff <= 100):
                issues.append(f"Efficiency must be 0-100, got {eff}")

        # Check costs are positive
        if "cost" in result:
            if isinstance(result["cost"], (int, float)):
                if result["cost"] < 0:
                    issues.append("Cost cannot be negative")

        # Check cycle time is positive
        if "cycle_time" in result:
            if isinstance(result["cycle_time"], (int, float)):
                if result["cycle_time"] <= 0:
                    issues.append("Cycle time must be positive")

        # Check SLA compliance is 0-1
        if "sla_compliance" in result:
            sla = result["sla_compliance"]
            if not (0.0 <= sla <= 1.0):
                issues.append(f"SLA compliance must be 0-1, got {sla}")

        return issues

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance (cost sourcing, benchmarks)."""
        issues = []

        # Check cost is cited
        if "source" not in result:
            issues.append("Cost data must have source cited")

        # Check benchmarks are provided
        if analysis.domain_intent == DomainIntent.COST_REDUCTION:
            if "benchmark" not in result:
                issues.append("Benchmark comparison required for cost reduction analysis")

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
        """Sanity checks on operations results."""
        issues = []

        # Efficiency sanity
        if "efficiency" in result:
            eff = result["efficiency"]
            if eff > 95:  # > 95% efficiency
                issues.append(
                    f"Efficiency {eff:.0f}% seems unrealistically high - verify measurement"
                )

        # Cost savings sanity
        if "savings" in result:
            savings = result["savings"]
            if isinstance(savings, (int, float)):
                if savings > 100_000_000:  # > $100M savings
                    issues.append(
                        f"Cost savings ${savings:,.0f} seems very large - verify calculations"
                    )

        # Cycle time sanity
        if "cycle_time" in result:
            cycle = result["cycle_time"]
            if cycle < 1:  # < 1 minute/hour (depending on unit)
                issues.append(f"Cycle time {cycle} seems too short - verify unit")

        return issues
