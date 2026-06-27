"""
capability_engine.py — Unified interface for the entire capability system.

This is the main entry point for agents to use skills.

Example:
    engine = CapabilityEngine()
    engine.setup()

    # Query and get result
    result = await engine.process_query(
        query="What is Q3 revenue?",
        dept_tag="finance",
        user_permissions={}
    )

    # Learn and auto-tune
    await engine.learn()
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from agents.capabilities.base_skill import SkillContext
from agents.capabilities.base_connector import ConnectorRegistry
from agents.capabilities.skill_registry import SkillRegistry
from agents.capabilities.skill_selector import SkillSelector, QueryIntent
from agents.capabilities.skill_intelligence import SkillIntelligence, SkillChain
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
from agents.capabilities.connectors import (
    SalesforceConnector,
    HubSpotConnector,
    SlackConnector,
    RealtimeConnector,
)

logger = logging.getLogger(__name__)


class CapabilityEngine:
    """
    Unified capability engine for agent skill management.

    Combines:
      - Skill registry (what skills exist)
      - Connector registry (what data sources exist)
      - Skill selector (which skill to pick)
      - Skill intelligence (learning from history)
      - Skill chaining (execute sequences)
    """

    def __init__(self):
        """Initialize capability engine."""
        self.skill_registry = SkillRegistry()
        self.connector_registry = ConnectorRegistry()
        self.skill_selector = None
        self.skill_intelligence = None
        self.skill_chain = None
        self._initialized = False

    def setup(self) -> None:
        """
        Setup the capability engine.

        Registers all skills and connectors, initializes components.
        """
        if self._initialized:
            logger.warning("Engine already initialized")
            return

        logger.info("=== Setting up Capability Engine ===")

        # Register all core skills
        logger.info("Registering core skills...")
        self.skill_registry.register(SQLQuerySkill())
        self.skill_registry.register(RAGSearchSkill())
        self.skill_registry.register(WebSearchSkill())
        self.skill_registry.register(APICallSkill())
        self.skill_registry.register(CalculationSkill())

        # Register domain skills
        logger.info("Registering domain skills...")
        self.skill_registry.register(RevenueForecasting())
        self.skill_registry.register(FraudDetection())
        self.skill_registry.register(DealPrediction())
        self.skill_registry.register(ChurnRiskScoring())
        self.skill_registry.register(CompetitorAnalysis())

        logger.info(f"Total skills registered: {len(self.skill_registry.list())}")

        # Initialize components
        logger.info("Initializing components...")
        self.skill_selector = SkillSelector(self.skill_registry, self.connector_registry)
        self.skill_intelligence = SkillIntelligence(self.skill_registry)
        self.skill_chain = SkillChain(self.skill_registry)

        self._initialized = True
        logger.info("✅ Capability engine ready")

    async def setup_connectors(self, connector_configs: Dict[str, Any] = None) -> Dict[str, bool]:
        """
        Setup and connect all data sources.

        Args:
            connector_configs: Dict of connector_name -> config

        Returns:
            Dict of connector_name -> connected (True/False)
        """
        logger.info("=== Connecting Data Sources ===")

        # Default configs (override with provided ones)
        defaults = {
            'salesforce': {
                'name': 'salesforce',
                'type': 'crm',
                'enabled': True,
                'settings': {'salesforce_url': 'https://yourinstance.salesforce.com'},
                'credentials': {'client_id': '', 'client_secret': ''},
            },
            'hubspot': {
                'name': 'hubspot',
                'type': 'crm',
                'enabled': True,
                'credentials': {'api_key': ''},
            },
            'slack': {
                'name': 'slack',
                'type': 'messaging',
                'enabled': True,
                'credentials': {'bot_token': ''},
            },
            'realtime': {
                'name': 'realtime',
                'type': 'data_stream',
                'enabled': True,
                'settings': {},
            },
        }

        configs = {**defaults, **(connector_configs or {})}

        # Register connectors
        from agents.capabilities.base_connector import ConnectorConfig

        for name, config_dict in configs.items():
            try:
                config = ConnectorConfig(**config_dict)

                if name == 'salesforce':
                    connector = SalesforceConnector(config)
                elif name == 'hubspot':
                    connector = HubSpotConnector(config)
                elif name == 'slack':
                    connector = SlackConnector(config)
                elif name == 'realtime':
                    connector = RealtimeConnector(config)
                else:
                    logger.warning(f"Unknown connector: {name}")
                    continue

                self.connector_registry.register(connector)
                logger.info(f"Registered connector: {name}")

            except Exception as e:
                logger.error(f"Failed to register {name}: {e}")

        # Connect all
        logger.info("Connecting all connectors...")
        results = await self.connector_registry.connect_all()

        for name, success in results.items():
            status = "✅" if success else "❌"
            logger.info(f"{status} {name}: {'connected' if success else 'failed'}")

        return results

    async def process_query(
        self,
        query: str,
        dept_tag: str,
        user_permissions: Dict[str, Any],
        use_intelligence: bool = True,
    ) -> Dict[str, Any]:
        """
        Process a user query end-to-end.

        1. Select best skills
        2. Execute skills
        3. Record metrics
        4. Return results

        Args:
            query: User query
            dept_tag: Department
            user_permissions: Access control
            use_intelligence: Use ML-based selection (vs. rule-based)

        Returns:
            Dict with results, confidence, sources, etc.
        """
        if not self._initialized:
            raise RuntimeError("Engine not initialized. Call setup() first.")

        logger.info(f"Processing query: {query[:50]}...")

        # Select skills
        if use_intelligence and self.skill_intelligence:
            intent = self.skill_selector._detect_intent(query)
            recommended = await self.skill_intelligence.get_recommendation(
                query, intent, dept_tag
            )
            logger.info(f"ML-recommended skills: {recommended}")

            # Use recommended skills if available
            selected_skills = [
                self.skill_registry.get(name) for name in recommended
                if self.skill_registry.get(name)
            ]

            if not selected_skills:
                # Fallback to regular selection
                selected_skills, intent = await self.skill_selector.select(
                    query, dept_tag, user_permissions
                )
        else:
            selected_skills, intent = await self.skill_selector.select(
                query, dept_tag, user_permissions
            )

        logger.info(f"Selected {len(selected_skills)} skills: {[s.name for s in selected_skills]}")

        if not selected_skills:
            return {
                'status': 'error',
                'message': 'No suitable skills found for this query',
                'confidence': 0.0,
            }

        # Create context
        context = SkillContext(
            query=query,
            dept_tag=dept_tag,
            user_permissions=user_permissions,
        )

        # Execute skills in sequence (chain)
        skill_names = [s.name for s in selected_skills]
        chain_result = await self.skill_chain.execute(skill_names, context)

        # Record execution in intelligence system
        if self.skill_intelligence:
            for skill_name in skill_names:
                skill = self.skill_registry.get(skill_name)
                if skill:
                    # Get result for this skill
                    individual_result = chain_result['individual_results'].get(skill_name, {})
                    success = individual_result.get('status') == 'SUCCESS'
                    confidence = individual_result.get('confidence', 0.0)

                    self.skill_intelligence.record_execution(
                        skill_name,
                        query,
                        intent,
                        type('Result', (), {
                            'is_success': lambda: success,
                            'confidence': confidence,
                            'time_ms': individual_result.get('time_ms', 0),
                        })(),
                        user_dept=dept_tag,
                        user_role=user_permissions.get('role', ''),
                    )

        return {
            'status': 'success',
            'intent': intent.value,
            'skills_used': skill_names,
            'results': chain_result['combined_data'],
            'confidence': self._calculate_overall_confidence(chain_result),
            'sources': self._extract_sources(chain_result),
            'execution_time_ms': self._calculate_total_time(chain_result),
        }

    async def learn(self) -> Dict[str, Any]:
        """
        Run learning pipeline.

        Analyzes execution history and optimizes skill priorities.

        Returns:
            Learning results (metrics, anomalies, adjustments)
        """
        if not self.skill_intelligence:
            return {'status': 'error', 'message': 'Intelligence not initialized'}

        logger.info("=== Running Learning Pipeline ===")

        results = await self.skill_intelligence.learn()

        logger.info(f"Learning complete:")
        logger.info(f"  - Anomalies detected: {len(results['anomalies'])}")
        logger.info(f"  - Priority adjustments: {len(results['adjustments'])}")
        logger.info(f"  - Applied changes: {sum(1 for v in results['applied'].values() if v)}")

        return results

    async def health_check(self) -> Dict[str, Any]:
        """
        Health check all systems.

        Returns:
            Health status for skills and connectors
        """
        logger.info("=== Health Check ===")

        # Check skills
        skill_health = {}
        for skill in self.skill_registry.list():
            try:
                is_healthy = await skill.health_check()
                skill_health[skill.name] = is_healthy
            except Exception as e:
                logger.error(f"Health check failed for {skill.name}: {e}")
                skill_health[skill.name] = False

        # Check connectors
        connector_health = await self.connector_registry.health_check_all()

        return {
            'timestamp': datetime.now().isoformat(),
            'skills': skill_health,
            'connectors': connector_health,
            'overall_healthy': all(skill_health.values()) and all(connector_health.values()),
        }

    def get_status(self) -> Dict[str, Any]:
        """Get engine status and statistics."""
        summary = self.skill_registry.get_summary()
        intelligence_stats = (
            self.skill_intelligence.get_stats()
            if self.skill_intelligence
            else {}
        )

        return {
            'initialized': self._initialized,
            'skills': summary,
            'intelligence': intelligence_stats,
            'skills_by_dept': {
                'finance': [s.name for s in self.skill_registry.list_for_dept('finance')],
                'sales': [s.name for s in self.skill_registry.list_for_dept('sales')],
                'hr': [s.name for s in self.skill_registry.list_for_dept('hr')],
                'operations': [s.name for s in self.skill_registry.list_for_dept('operations')],
            },
        }

    def _calculate_overall_confidence(self, chain_result: Dict[str, Any]) -> float:
        """Calculate overall confidence from chain results."""
        confidences = [
            r.get('confidence', 0.0)
            for r in chain_result['individual_results'].values()
        ]
        return sum(confidences) / len(confidences) if confidences else 0.0

    def _extract_sources(self, chain_result: Dict[str, Any]) -> List[str]:
        """Extract all sources from chain results."""
        sources = []
        for result in chain_result['individual_results'].values():
            sources.extend(result.get('sources', []))
        return list(set(sources))

    def _calculate_total_time(self, chain_result: Dict[str, Any]) -> int:
        """Calculate total execution time."""
        return sum(r.get('time_ms', 0) for r in chain_result['individual_results'].values())
