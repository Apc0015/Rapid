"""
agents/capabilities — Agent skills and connectors system.

Complete Phase 1-4 implementation of the Agent Capability System.

Phases:
  1. Foundation: Base classes, registries, selector
  2. Core Skills: 11 ready-to-use skills
  3. Integrations: Salesforce, HubSpot, Slack, Real-time connectors
  4. Intelligence: ML-based selection, auto-tuning, skill chaining

Main Entry Point:
    engine = CapabilityEngine()
    engine.setup()
    await engine.setup_connectors()

    result = await engine.process_query(
        query="What is Q3 revenue?",
        dept_tag="finance",
        user_permissions={}
    )

    await engine.learn()  # Auto-optimize
"""

# Phase 1: Foundation
from agents.capabilities.base_skill import (
    BaseSkill,
    ComposableSkill,
    SkillContext,
    SkillResult,
    SkillStatus,
)

from agents.capabilities.base_connector import (
    BaseConnector,
    ConnectorConfig,
    ConnectorRegistry,
    DatabaseConnector,
    DocumentConnector,
    APIConnector,
    MessagingConnector,
)

from agents.capabilities.skill_registry import SkillRegistry

from agents.capabilities.skill_selector import (
    SkillSelector,
    QueryIntent,
    SkillRanking,
)

# Phase 2: Core Skills
from agents.capabilities.core_skills import (
    SQLQuerySkill,
    RAGSearchSkill,
    WebSearchSkill,
    APICallSkill,
    CalculationSkill,
    RevenueForecasting,
    FraudDetection,
    DealPrediction,
    ChurnRiskScoring,
    CompetitorAnalysis,
)

# Phase 3: Connectors
from agents.capabilities.connectors import (
    SalesforceConnector,
    HubSpotConnector,
    SlackConnector,
    RealtimeConnector,
)

# Phase 4: Intelligence
from agents.capabilities.skill_intelligence import (
    SkillIntelligence,
    SkillChain,
    SkillMetrics,
    ExecutionRecord,
)

# Unified API
from agents.capabilities.capability_engine import CapabilityEngine

__all__ = [
    # Phase 1: Foundation
    'BaseSkill',
    'ComposableSkill',
    'SkillContext',
    'SkillResult',
    'SkillStatus',
    'BaseConnector',
    'ConnectorConfig',
    'ConnectorRegistry',
    'DatabaseConnector',
    'DocumentConnector',
    'APIConnector',
    'MessagingConnector',
    'SkillRegistry',
    'SkillSelector',
    'QueryIntent',
    'SkillRanking',
    # Phase 2: Skills
    'SQLQuerySkill',
    'RAGSearchSkill',
    'WebSearchSkill',
    'APICallSkill',
    'CalculationSkill',
    'RevenueForecasting',
    'FraudDetection',
    'DealPrediction',
    'ChurnRiskScoring',
    'CompetitorAnalysis',
    # Phase 3: Connectors
    'SalesforceConnector',
    'HubSpotConnector',
    'SlackConnector',
    'RealtimeConnector',
    # Phase 4: Intelligence
    'SkillIntelligence',
    'SkillChain',
    'SkillMetrics',
    'ExecutionRecord',
    # Unified API
    'CapabilityEngine',
]
