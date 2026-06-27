"""
skill_intelligence.py — Machine learning-based skill intelligence.

Phase 4: Intelligent skill selection and auto-tuning.

Features:
  1. ML-based skill ranking (learns from execution history)
  2. Auto-tuning of skill priorities
  3. Context-aware skill chaining
  4. Anomaly detection (skills underperforming)
  5. Skill recommendation engine
"""

import asyncio
import logging
import json
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from agents.capabilities.base_skill import BaseSkill, SkillContext, SkillResult
from agents.capabilities.skill_selector import QueryIntent

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a single skill execution."""

    skill_name: str
    query: str
    intent: QueryIntent
    success: bool
    confidence: float
    time_ms: int
    timestamp: datetime = field(default_factory=datetime.now)
    user_dept: str = ""
    user_role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            'skill_name': self.skill_name,
            'query': self.query,
            'intent': self.intent.value,
            'success': self.success,
            'confidence': self.confidence,
            'time_ms': self.time_ms,
            'timestamp': self.timestamp.isoformat(),
            'user_dept': self.user_dept,
            'user_role': self.user_role,
        }


@dataclass
class SkillMetrics:
    """Performance metrics for a skill."""

    skill_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    avg_confidence: float = 0.0
    avg_time_ms: float = 0.0
    success_rate: float = 0.0
    confidence_by_intent: Dict[str, float] = field(default_factory=dict)
    time_by_intent: Dict[str, float] = field(default_factory=dict)
    dept_performance: Dict[str, float] = field(default_factory=dict)
    trend: float = 0.0  # +1.0 (improving) to -1.0 (degrading)

    def update_success_rate(self) -> None:
        """Recalculate success rate."""
        if self.total_executions > 0:
            self.success_rate = self.successful_executions / self.total_executions


class SkillIntelligence:
    """
    Machine learning-based skill intelligence.

    Learns from execution history to improve skill selection and ranking.
    Implements:
      - ML-based skill scoring
      - Auto-tuning of priorities
      - Context-aware recommendations
      - Anomaly detection
      - Performance trending
    """

    def __init__(self, skill_registry, look_back_days: int = 30):
        """
        Initialize skill intelligence.

        Args:
            skill_registry: SkillRegistry instance
            look_back_days: Days of history to consider for learning
        """
        self._skill_registry = skill_registry
        self._look_back_days = look_back_days
        self._execution_history: List[ExecutionRecord] = []
        self._metrics_cache: Dict[str, SkillMetrics] = {}

    def record_execution(
        self,
        skill_name: str,
        query: str,
        intent: QueryIntent,
        result: SkillResult,
        user_dept: str = "",
        user_role: str = "",
    ) -> None:
        """
        Record skill execution for learning.

        Args:
            skill_name: Name of skill executed
            query: User query
            intent: Detected query intent
            result: Execution result
            user_dept: User's department
            user_role: User's role
        """
        record = ExecutionRecord(
            skill_name=skill_name,
            query=query,
            intent=intent,
            success=result.is_success(),
            confidence=result.confidence,
            time_ms=result.time_ms,
            user_dept=user_dept,
            user_role=user_role,
        )

        self._execution_history.append(record)

        # Invalidate cache (will be recalculated on next request)
        self._metrics_cache.clear()

    async def learn(self) -> Dict[str, Any]:
        """
        Run learning pipeline.

        Analyzes execution history and updates skill priorities.

        Returns:
            Dict with learning results and recommended priority changes
        """
        # Calculate metrics
        metrics = self._calculate_metrics()

        # Detect anomalies (underperforming skills)
        anomalies = self._detect_anomalies(metrics)

        # Calculate priority adjustments
        adjustments = self._calculate_priority_adjustments(metrics)

        # Apply auto-tuning
        applied = await self._apply_auto_tuning(adjustments)

        logger.info(f"Learning complete: {len(adjustments)} adjustments, {len(anomalies)} anomalies")

        return {
            'metrics': {name: vars(m) for name, m in metrics.items()},
            'anomalies': anomalies,
            'adjustments': adjustments,
            'applied': applied,
        }

    def _calculate_metrics(self) -> Dict[str, SkillMetrics]:
        """Calculate performance metrics for all skills."""
        if self._metrics_cache:
            return self._metrics_cache

        # Filter to recent history
        cutoff_date = datetime.now() - timedelta(days=self._look_back_days)
        recent = [r for r in self._execution_history if r.timestamp >= cutoff_date]

        # Group by skill
        by_skill = defaultdict(list)
        for record in recent:
            by_skill[record.skill_name].append(record)

        # Calculate metrics per skill
        metrics = {}
        for skill_name, records in by_skill.items():
            m = SkillMetrics(skill_name=skill_name)

            # Basic stats
            m.total_executions = len(records)
            m.successful_executions = sum(1 for r in records if r.success)
            m.failed_executions = m.total_executions - m.successful_executions
            m.update_success_rate()

            # Confidence
            if records:
                confidences = [r.confidence for r in records]
                m.avg_confidence = statistics.mean(confidences)

            # Time
            if records:
                times = [r.time_ms for r in records]
                m.avg_time_ms = statistics.mean(times)

            # Confidence by intent
            by_intent = defaultdict(list)
            for record in records:
                by_intent[record.intent.value].append(record.confidence)

            for intent, confs in by_intent.items():
                m.confidence_by_intent[intent] = statistics.mean(confs) if confs else 0.0

            # Department performance
            by_dept = defaultdict(list)
            for record in records:
                if record.user_dept:
                    by_dept[record.user_dept].append(1 if record.success else 0)

            for dept, successes in by_dept.items():
                m.dept_performance[dept] = sum(successes) / len(successes) if successes else 0.0

            # Trend (improving or degrading)
            m.trend = self._calculate_trend(records)

            metrics[skill_name] = m

        self._metrics_cache = metrics
        return metrics

    def _calculate_trend(self, records: List[ExecutionRecord]) -> float:
        """
        Calculate trend for a skill (improving or degrading).

        Returns:
            +1.0 (improving) to -1.0 (degrading)
        """
        if len(records) < 3:
            return 0.0

        # Split into thirds
        third = len(records) // 3
        early = records[:third]
        recent = records[-third:]

        early_success_rate = sum(1 for r in early if r.success) / len(early) if early else 0.0
        recent_success_rate = sum(1 for r in recent if r.success) / len(recent) if recent else 0.0

        trend = recent_success_rate - early_success_rate
        return max(-1.0, min(trend, 1.0))

    def _detect_anomalies(self, metrics: Dict[str, SkillMetrics]) -> List[Dict[str, Any]]:
        """
        Detect underperforming skills.

        Returns:
            List of anomalies (skills below threshold)
        """
        anomalies = []

        for skill_name, m in metrics.items():
            issues = []

            # Low success rate
            if m.success_rate < 0.70 and m.total_executions > 10:
                issues.append(f"Low success rate: {m.success_rate:.0%}")

            # High latency
            if m.avg_time_ms > 5000:
                issues.append(f"High latency: {m.avg_time_ms:.0f}ms")

            # Degrading trend
            if m.trend < -0.2:
                issues.append(f"Degrading: {m.trend:.2f} trend")

            if issues:
                anomalies.append({
                    'skill': skill_name,
                    'issues': issues,
                    'success_rate': m.success_rate,
                    'avg_time_ms': m.avg_time_ms,
                    'trend': m.trend,
                })

        return anomalies

    def _calculate_priority_adjustments(self, metrics: Dict[str, SkillMetrics]) -> Dict[str, int]:
        """
        Calculate priority adjustments based on performance.

        Returns:
            Dict of skill_name -> new_priority (0-10)
        """
        adjustments = {}

        for skill_name, m in metrics.items():
            # Start with current priority
            skill = self._skill_registry.get(skill_name)
            if not skill:
                continue

            current_priority = skill.priority

            # Adjust based on success rate
            # 95%+ success: +1
            # 80-95% success: 0
            # <80% success: -1
            if m.success_rate >= 0.95:
                new_priority = min(current_priority + 1, 10)
            elif m.success_rate < 0.80 and m.total_executions > 10:
                new_priority = max(current_priority - 1, 0)
            else:
                new_priority = current_priority

            # Adjust based on latency
            # If slower than average, lower priority slightly
            avg_times = [m.avg_time_ms for m in metrics.values() if m.avg_time_ms > 0]
            if avg_times:
                avg_time = statistics.mean(avg_times)
                if m.avg_time_ms > avg_time * 1.5:
                    new_priority = max(new_priority - 1, 0)

            adjustments[skill_name] = new_priority

        return adjustments

    async def _apply_auto_tuning(self, adjustments: Dict[str, int]) -> Dict[str, bool]:
        """
        Apply priority adjustments.

        Args:
            adjustments: Dict of skill_name -> new_priority

        Returns:
            Dict of skill_name -> was_changed (True/False)
        """
        applied = {}

        for skill_name, new_priority in adjustments.items():
            skill = self._skill_registry.get(skill_name)
            if not skill:
                continue

            old_priority = skill.priority

            if new_priority != old_priority:
                self._skill_registry.set_priority(skill_name, new_priority)
                applied[skill_name] = True
                logger.info(f"Auto-tuned {skill_name}: {old_priority} → {new_priority}")
            else:
                applied[skill_name] = False

        return applied

    async def get_recommendation(
        self,
        query: str,
        intent: QueryIntent,
        dept_tag: str,
    ) -> List[str]:
        """
        Get AI-recommended skill sequence for a query.

        Uses learning from execution history to recommend the best
        sequence of skills to execute.

        Args:
            query: User query
            intent: Detected intent
            dept_tag: User department

        Returns:
            Ordered list of skill names to execute
        """
        metrics = self._calculate_metrics()

        # Filter to skills applicable to this dept
        applicable_skills = self._skill_registry.list_for_dept(dept_tag)

        # Score each skill based on:
        # 1. Historical success for this intent
        # 2. Confidence for this intent
        # 3. Department-specific performance
        # 4. Current priority
        scores = {}

        for skill in applicable_skills:
            m = metrics.get(skill.name)
            if not m:
                # No history, use base priority
                scores[skill.name] = skill.priority / 10.0
                continue

            intent_value = intent.value
            intent_confidence = m.confidence_by_intent.get(intent_value, 0.0)
            dept_success = m.dept_performance.get(dept_tag, m.success_rate)

            # Weighted score
            score = (
                intent_confidence * 0.4 +  # 40% intent-specific confidence
                dept_success * 0.3 +        # 30% department-specific success
                (skill.priority / 10.0) * 0.2 +  # 20% current priority
                m.success_rate * 0.1        # 10% overall success
            )

            scores[skill.name] = score

        # Sort and return top 3
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [name for name, score in ranked[:3]]

    def get_stats(self) -> Dict[str, Any]:
        """Get overall intelligence statistics."""
        metrics = self._calculate_metrics()

        return {
            'total_records': len(self._execution_history),
            'skills_tracked': len(metrics),
            'avg_success_rate': statistics.mean([m.success_rate for m in metrics.values()]) if metrics else 0.0,
            'avg_confidence': statistics.mean([m.avg_confidence for m in metrics.values()]) if metrics else 0.0,
            'metrics_by_skill': {name: vars(m) for name, m in metrics.items()},
        }


class SkillChain:
    """
    Skill orchestration and chaining.

    Executes a sequence of skills with context passing between them.

    Example:
        chain = SkillChain(skill_registry)
        result = await chain.execute(
            skills=['competitor_analysis', 'calculation'],
            context=context
        )
    """

    def __init__(self, skill_registry):
        """Initialize skill chain executor."""
        self._skill_registry = skill_registry

    async def execute(
        self,
        skills: List[str],
        context: SkillContext,
    ) -> Dict[str, Any]:
        """
        Execute a chain of skills in sequence.

        Args:
            skills: List of skill names in order
            context: Skill context (passed to all skills)

        Returns:
            Dict with results from all skills
        """
        results = {}
        combined_data = {}

        for skill_name in skills:
            skill = self._skill_registry.get(skill_name)
            if not skill:
                logger.error(f"Skill {skill_name} not found")
                continue

            # Add previous results to context
            context.set('previous_results', combined_data)

            # Execute skill
            result = await skill.execute(context)
            results[skill_name] = result.to_dict() if hasattr(result, 'to_dict') else vars(result)

            # Accumulate data
            if isinstance(result.data, dict):
                combined_data.update(result.data)

        return {
            'individual_results': results,
            'combined_data': combined_data,
        }

    async def optimize_chain(
        self,
        skills: List[str],
        intelligence: SkillIntelligence,
    ) -> List[str]:
        """
        Optimize skill chain order based on learning.

        Reorders skills for optimal performance:
          - Put fastest skills first
          - Put most reliable skills first
          - Consider dependencies

        Args:
            skills: Original skill sequence
            intelligence: SkillIntelligence instance

        Returns:
            Optimized skill sequence
        """
        metrics = intelligence._calculate_metrics()

        # Score each skill in the chain
        scores = {}
        for skill_name in skills:
            m = metrics.get(skill_name)
            if not m:
                scores[skill_name] = 0.5
                continue

            # Fast + reliable = high score
            speed_score = max(0, 1.0 - (m.avg_time_ms / 5000))  # Normalize to 0-1
            reliability_score = m.success_rate

            score = (speed_score * 0.4) + (reliability_score * 0.6)
            scores[skill_name] = score

        # Sort by score (highest first)
        optimized = sorted(skills, key=lambda s: scores[s], reverse=True)

        return optimized
