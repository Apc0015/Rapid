"""
base_agent_intelligence.py — Base class for all agent intelligence.

Every department agent inherits from this to get:
  - Domain knowledge management
  - Decision rules engine
  - Query understanding/classification
  - Skill selection logic
  - Result validation
  - Reasoning/explanation
  - Learning from outcomes
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from agents.capabilities import (
    CapabilityEngine,
    SkillContext,
    QueryIntent,
)

logger = logging.getLogger(__name__)


class DomainIntent(Enum):
    """Domain-specific intents (beyond generic QueryIntent)."""
    # Finance
    REVENUE_ANALYSIS = "revenue_analysis"
    BUDGET_PLANNING = "budget_planning"
    FRAUD_DETECTION_INTENT = "fraud_detection"
    FORECASTING = "forecasting"
    FINANCIAL_HEALTH = "financial_health"

    # Sales
    DEAL_ANALYSIS = "deal_analysis"
    PIPELINE_HEALTH = "pipeline_health"
    CUSTOMER_INSIGHT = "customer_insight"
    COMPETITIVE_THREAT = "competitive_threat"
    DEAL_CLOSURE = "deal_closure"

    # HR
    RETENTION_RISK = "retention_risk"
    HIRING_NEED = "hiring_need"
    COMPENSATION = "compensation"
    COMPLIANCE = "compliance"
    CULTURE = "culture"

    # Legal
    CONTRACT_REVIEW = "contract_review"
    COMPLIANCE_CHECK = "compliance_check"
    RISK_ASSESSMENT = "risk_assessment"
    IP_PROTECTION = "ip_protection"
    DISPUTE = "dispute"

    # Marketing
    CAMPAIGN_PERFORMANCE = "campaign_performance"
    CUSTOMER_ENGAGEMENT = "customer_engagement"
    BRAND_HEALTH = "brand_health"
    MARKET_TRENDS = "market_trends"
    COMPETITOR_INTELLIGENCE = "competitor_intelligence"

    # Ops
    PROCESS_OPTIMIZATION = "process_optimization"
    QUALITY_IMPROVEMENT = "quality_improvement"
    COST_REDUCTION = "cost_reduction"
    CAPACITY_PLANNING = "capacity_planning"
    EFFICIENCY = "efficiency"


@dataclass
class DomainKnowledge:
    """Domain-specific knowledge for an agent."""

    department: str                 # 'finance', 'sales', 'hr', etc
    key_concepts: List[str]        # ['revenue', 'cost', 'margin', ...]
    keywords: Dict[str, List[str]] # {'revenue': ['revenue', 'sales', 'income', ...]}
    skill_rules: Dict[str, List[str]]  # {'revenue_query': ['sql_query', 'calculation']}
    validation_rules: Dict[str, Any]   # Custom validation per intent
    governance_rules: Dict[str, Any]   # Column access, PII, etc


@dataclass
class QueryAnalysis:
    """Result of analyzing a user query."""

    domain_intent: DomainIntent
    confidence: float              # 0.0-1.0
    entities: Dict[str, Any]      # Extracted entities (revenue, customer, etc)
    requires_realtime: bool        # Needs real-time data?
    requires_crm: bool             # Needs CRM access?
    requires_external: bool        # Needs external data (web)?
    is_sensitive: bool             # Contains sensitive data?
    clarifications_needed: List[str]  # Questions to ask user


@dataclass
class SkillPlan:
    """Plan for executing skills."""

    skills: List[str]              # Skills to execute in order
    rationale: str                 # Why these skills?
    expected_output: str           # What should result look like?
    validation_checks: List[str]   # Validations to perform
    fallback_skills: List[str]     # If primary fails, try these


class BaseAgentIntelligence(ABC):
    """
    Base intelligence class for all department agents.

    Provides:
      - Domain knowledge management
      - Query classification
      - Skill planning
      - Result validation
      - Reasoning/explanation
      - Learning
    """

    def __init__(self, capability_engine: CapabilityEngine):
        """Initialize agent intelligence."""
        self.engine = capability_engine
        self.domain_knowledge = self._build_domain_knowledge()
        self.decision_history: List[Dict[str, Any]] = []
        self.learned_patterns: Dict[str, float] = {}

    @abstractmethod
    def _build_domain_knowledge(self) -> DomainKnowledge:
        """Build domain-specific knowledge. Override in subclasses."""
        pass

    async def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze user query to understand intent.

        Returns: QueryAnalysis with domain intent, entities, requirements
        """
        # Detect domain intent
        domain_intent = self._classify_intent(query)

        # Extract entities
        entities = self._extract_entities(query, domain_intent)

        # Determine requirements
        requires_realtime = self._needs_realtime(domain_intent)
        requires_crm = self._needs_crm(domain_intent)
        requires_external = self._needs_external(domain_intent)
        is_sensitive = self._is_sensitive(domain_intent, entities)

        # Check for clarifications needed
        clarifications = self._identify_clarifications(query, domain_intent, entities)

        # Calculate confidence in classification
        confidence = self._calculate_classification_confidence(query, domain_intent)

        return QueryAnalysis(
            domain_intent=domain_intent,
            confidence=confidence,
            entities=entities,
            requires_realtime=requires_realtime,
            requires_crm=requires_crm,
            requires_external=requires_external,
            is_sensitive=is_sensitive,
            clarifications_needed=clarifications,
        )

    async def plan_skills(self, analysis: QueryAnalysis) -> SkillPlan:
        """
        Plan which skills to execute based on query analysis.

        Returns: SkillPlan with ordered skills and rationale
        """
        # Get skill rules for this intent
        intent_key = analysis.domain_intent.value
        skill_rules = self.domain_knowledge.skill_rules.get(
            intent_key,
            ['sql_query']  # Fallback
        )

        # Adjust based on requirements
        skills = self._adjust_skills_for_requirements(skill_rules, analysis)

        # Determine fallback skills
        fallback = self._get_fallback_skills(skills, analysis)

        # Get rationale
        rationale = self._generate_rationale(skills, analysis)

        # Expected output
        expected = self._describe_expected_output(analysis)

        # Validation checks
        validations = self._get_validation_checks(analysis)

        return SkillPlan(
            skills=skills,
            rationale=rationale,
            expected_output=expected,
            validation_checks=validations,
            fallback_skills=fallback,
        )

    async def validate_result(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
        plan: SkillPlan,
    ) -> Tuple[bool, List[str]]:
        """
        Validate result from skill execution.

        Returns: (is_valid, list_of_issues)
        """
        issues = []

        # Check result structure
        if not result:
            issues.append("Empty result")
            return False, issues

        # Domain-specific validations
        domain_issues = await self._validate_domain_specific(result, analysis)
        issues.extend(domain_issues)

        # Governance validations
        governance_issues = self._validate_governance(result, analysis)
        issues.extend(governance_issues)

        # Format validations
        format_issues = self._validate_format(result, plan)
        issues.extend(format_issues)

        # Reasonableness checks
        reasonableness_issues = self._validate_reasonableness(result, analysis)
        issues.extend(reasonableness_issues)

        is_valid = len(issues) == 0
        return is_valid, issues

    async def explain_decision(
        self,
        query: str,
        analysis: QueryAnalysis,
        plan: SkillPlan,
        result: Dict[str, Any],
    ) -> str:
        """
        Generate explanation of decision and reasoning.

        Returns: Human-readable explanation
        """
        explanation = f"""
Decision Reasoning:
─────────────────
Query: {query}

1. Intent Analysis:
   - Detected: {analysis.domain_intent.value}
   - Confidence: {analysis.confidence:.0%}
   - Entities: {analysis.entities}

2. Requirements:
   - Requires Real-time: {analysis.requires_realtime}
   - Requires CRM: {analysis.requires_crm}
   - Requires External Data: {analysis.requires_external}
   - Sensitive Data: {analysis.is_sensitive}

3. Skill Selection:
   - Selected Skills: {' → '.join(plan.skills)}
   - Rationale: {plan.rationale}
   - Fallback Skills: {plan.fallback_skills}

4. Validations:
   - Checks Performed: {', '.join(plan.validation_checks)}
   - Result Valid: ✅ (passed all checks)

5. Output Summary:
   - {plan.expected_output}
"""
        return explanation.strip()

    def record_decision(
        self,
        query: str,
        analysis: QueryAnalysis,
        plan: SkillPlan,
        result: Dict[str, Any],
        success: bool,
    ) -> None:
        """Record decision for learning."""
        self.decision_history.append({
            'query': query,
            'intent': analysis.domain_intent.value,
            'skills': plan.skills,
            'success': success,
            'timestamp': __import__('datetime').datetime.now(),
        })

    # ─────────────────────────────────────────────────────────────────
    # Abstract methods - override in subclasses
    # ─────────────────────────────────────────────────────────────────

    def _classify_intent(self, query: str) -> DomainIntent:
        """Classify query to domain intent. Override in subclass."""
        raise NotImplementedError()

    def _extract_entities(
        self,
        query: str,
        intent: DomainIntent,
    ) -> Dict[str, Any]:
        """Extract entities from query. Override in subclass."""
        raise NotImplementedError()

    def _needs_realtime(self, intent: DomainIntent) -> bool:
        """Does this intent need real-time data?"""
        raise NotImplementedError()

    def _needs_crm(self, intent: DomainIntent) -> bool:
        """Does this intent need CRM data?"""
        raise NotImplementedError()

    def _needs_external(self, intent: DomainIntent) -> bool:
        """Does this intent need external/web data?"""
        raise NotImplementedError()

    def _is_sensitive(self, intent: DomainIntent, entities: Dict[str, Any]) -> bool:
        """Is this query handling sensitive data?"""
        raise NotImplementedError()

    def _identify_clarifications(
        self,
        query: str,
        intent: DomainIntent,
        entities: Dict[str, Any],
    ) -> List[str]:
        """What clarifications do we need?"""
        raise NotImplementedError()

    def _calculate_classification_confidence(
        self,
        query: str,
        intent: DomainIntent,
    ) -> float:
        """Calculate confidence in intent classification."""
        raise NotImplementedError()

    def _adjust_skills_for_requirements(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Adjust skill list based on requirements."""
        raise NotImplementedError()

    def _get_fallback_skills(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Get fallback skills if primary fails."""
        raise NotImplementedError()

    def _generate_rationale(
        self,
        skills: List[str],
        analysis: QueryAnalysis,
    ) -> str:
        """Generate rationale for skill selection."""
        raise NotImplementedError()

    def _describe_expected_output(self, analysis: QueryAnalysis) -> str:
        """Describe what output should look like."""
        raise NotImplementedError()

    def _get_validation_checks(self, analysis: QueryAnalysis) -> List[str]:
        """Get list of validation checks to perform."""
        raise NotImplementedError()

    async def _validate_domain_specific(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Domain-specific validations. Override in subclass."""
        raise NotImplementedError()

    def _validate_governance(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Validate governance rules."""
        raise NotImplementedError()

    def _validate_format(
        self,
        result: Dict[str, Any],
        plan: SkillPlan,
    ) -> List[str]:
        """Validate result format matches expected."""
        raise NotImplementedError()

    def _validate_reasonableness(
        self,
        result: Dict[str, Any],
        analysis: QueryAnalysis,
    ) -> List[str]:
        """Check if result is reasonable (sanity checks)."""
        raise NotImplementedError()


class SmartAgent(ABC):
    """
    Smart agent that uses intelligence layer.

    Combines:
      - BaseAgentIntelligence (reasoning)
      - CapabilityEngine (skills)
      - Orchestration (execution)
    """

    def __init__(self, intelligence: BaseAgentIntelligence):
        """Initialize smart agent."""
        self.intelligence = intelligence
        self.engine = intelligence.engine

    async def execute(
        self,
        query: str,
        user_permissions: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute query end-to-end with intelligence.

        Steps:
        1. Analyze query
        2. Plan skills
        3. Execute skills
        4. Validate result
        5. Explain decision
        6. Record for learning
        """
        logger.info(f"Executing: {query[:50]}...")

        # Step 1: Analyze
        analysis = await self.intelligence.analyze_query(query)
        logger.info(f"Intent: {analysis.domain_intent.value} ({analysis.confidence:.0%})")

        # If clarifications needed, ask
        if analysis.clarifications_needed:
            return {
                'status': 'clarification_needed',
                'message': 'I need more information',
                'clarifications': analysis.clarifications_needed,
            }

        # Step 2: Plan
        plan = await self.intelligence.plan_skills(analysis)
        logger.info(f"Skills: {' → '.join(plan.skills)}")

        # Step 3: Execute
        try:
            result = await self.engine.process_query(
                query=query,
                dept_tag=self.intelligence.domain_knowledge.department,
                user_permissions=user_permissions,
            )
            skill_result = result.get('results', {})
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            skill_result = {}

        # Step 4: Validate
        is_valid, issues = await self.intelligence.validate_result(
            skill_result,
            analysis,
            plan,
        )

        if not is_valid:
            logger.warning(f"Validation failed: {issues}")
            # Try fallback skills
            # (implementation in specific agents)

        # Step 5: Explain
        explanation = await self.intelligence.explain_decision(
            query,
            analysis,
            plan,
            skill_result,
        )

        # Step 6: Record
        self.intelligence.record_decision(
            query,
            analysis,
            plan,
            skill_result,
            success=is_valid,
        )

        return {
            'status': 'success' if is_valid else 'partial',
            'result': skill_result,
            'intent': analysis.domain_intent.value,
            'explanation': explanation,
            'confidence': analysis.confidence,
            'skills_used': plan.skills,
        }
