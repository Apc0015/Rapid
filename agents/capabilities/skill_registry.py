"""
skill_registry.py — Central registry for all agent skills.

The SkillRegistry is responsible for:
  - Registering skills
  - Enabling/disabling skills (admin control)
  - Looking up skills by name
  - Health checking skills
  - Providing metrics and dashboards

Example:
    registry = SkillRegistry()
    registry.register(SQLQuerySkill())
    registry.register(RAGSearchSkill())
    registry.register(FraudDetectionSkill())

    # Admin disables a skill
    registry.disable('fraud_detection')

    # Get all skills for Finance agent
    skills = registry.list_for_dept('finance')
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from agents.capabilities.base_skill import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Central registry for all agent skills.

    Manages skill lifecycle, enables/disables, tracks health and metrics.
    """

    def __init__(self):
        """Initialize skill registry."""
        self._skills: Dict[str, BaseSkill] = {}  # name -> skill
        self._metrics: Dict[str, Dict[str, Any]] = {}  # name -> metrics
        self._last_health_check: Dict[str, bool] = {}  # name -> is_healthy

    def register(self, skill: BaseSkill) -> None:
        """
        Register a skill.

        Args:
            skill: BaseSkill instance to register

        Raises:
            ValueError: If skill name already registered
        """
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already registered")

        self._skills[skill.name] = skill
        self._metrics[skill.name] = {
            'name': skill.name,
            'description': skill.description,
            'registered_at': datetime.now().isoformat(),
            'execution_count': 0,
            'success_count': 0,
            'failure_count': 0,
            'avg_confidence': 0.0,
            'avg_time_ms': 0.0,
        }

        logger.info(f"Registered skill: {skill.name}")

    def get(self, name: str) -> Optional[BaseSkill]:
        """
        Get a skill by name.

        Args:
            name: Skill name

        Returns:
            BaseSkill or None if not found
        """
        return self._skills.get(name)

    def list(self) -> List[BaseSkill]:
        """Get all registered skills."""
        return list(self._skills.values())

    def list_enabled(self) -> List[BaseSkill]:
        """Get only enabled skills."""
        return [s for s in self._skills.values() if s.enabled]

    def list_for_dept(self, dept_tag: str) -> List[BaseSkill]:
        """
        Get skills applicable to a specific department.

        Args:
            dept_tag: Department (e.g., 'finance', 'sales')

        Returns:
            List of applicable skills
        """
        applicable = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue

            applicable_depts = skill.applicable_to_depts()
            # Empty list = available to all depts
            if not applicable_depts or dept_tag in applicable_depts:
                applicable.append(skill)

        return applicable

    def enable(self, name: str) -> bool:
        """
        Enable a skill.

        Args:
            name: Skill name

        Returns:
            True if enabled, False if not found
        """
        skill = self._skills.get(name)
        if not skill:
            return False

        skill.enabled = True
        logger.info(f"Enabled skill: {name}")
        return True

    def disable(self, name: str) -> bool:
        """
        Disable a skill.

        Args:
            name: Skill name

        Returns:
            True if disabled, False if not found
        """
        skill = self._skills.get(name)
        if not skill:
            return False

        skill.enabled = False
        logger.info(f"Disabled skill: {name}")
        return True

    def set_priority(self, name: str, priority: int) -> bool:
        """
        Set skill priority (0-10, higher = more preferred).

        Args:
            name: Skill name
            priority: Priority (0-10)

        Returns:
            True if set, False if not found
        """
        if priority < 0 or priority > 10:
            raise ValueError(f"Priority must be 0-10, got {priority}")

        skill = self._skills.get(name)
        if not skill:
            return False

        skill.priority = priority
        logger.info(f"Set {name} priority to {priority}")
        return True

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Health check all registered skills.

        Returns:
            Dict of skill_name -> is_healthy (True/False)
        """
        results = {}

        for name, skill in self._skills.items():
            try:
                is_healthy = await skill.health_check()
                results[name] = is_healthy
                self._last_health_check[name] = is_healthy
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
                self._last_health_check[name] = False

        return results

    def record_execution(
        self,
        skill_name: str,
        success: bool,
        confidence: float = 0.0,
        time_ms: int = 0,
    ) -> None:
        """
        Record skill execution metrics.

        Called after every skill execution to update metrics.

        Args:
            skill_name: Name of skill executed
            success: Whether execution was successful
            confidence: Confidence score (0.0-1.0)
            time_ms: Execution time in milliseconds
        """
        if skill_name not in self._metrics:
            return

        metrics = self._metrics[skill_name]
        metrics['execution_count'] += 1

        if success:
            metrics['success_count'] += 1
        else:
            metrics['failure_count'] += 1

        # Update rolling average confidence
        old_avg = metrics['avg_confidence']
        count = metrics['execution_count']
        metrics['avg_confidence'] = (old_avg * (count - 1) + confidence) / count

        # Update rolling average time
        old_time = metrics['avg_time_ms']
        metrics['avg_time_ms'] = (old_time * (count - 1) + time_ms) / count

    def get_metrics(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get metrics for a skill.

        Args:
            name: Skill name

        Returns:
            Metrics dict or None if not found
        """
        metrics = self._metrics.get(name)
        if metrics:
            # Add derived fields
            metrics['success_rate'] = (
                metrics['success_count'] / metrics['execution_count']
                if metrics['execution_count'] > 0
                else 0.0
            )
            metrics['is_healthy'] = self._last_health_check.get(name, True)

        return metrics

    def list_metrics(self) -> List[Dict[str, Any]]:
        """
        Get metrics for all skills.

        Useful for dashboards and monitoring.

        Returns:
            List of metrics dicts
        """
        all_metrics = []
        for name in sorted(self._metrics.keys()):
            metrics = self.get_metrics(name)
            if metrics:
                all_metrics.append(metrics)

        return all_metrics

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for all skills.

        Returns:
            Dict with overall metrics
        """
        all_metrics = self._metrics.values()

        if not all_metrics:
            return {'total_skills': 0}

        total_executions = sum(m['execution_count'] for m in all_metrics)
        total_successes = sum(m['success_count'] for m in all_metrics)

        return {
            'total_skills': len(self._skills),
            'enabled_skills': len(self.list_enabled()),
            'total_executions': total_executions,
            'total_successes': total_successes,
            'overall_success_rate': (
                total_successes / total_executions if total_executions > 0 else 0.0
            ),
            'avg_confidence': (
                sum(m['avg_confidence'] for m in all_metrics) / len(all_metrics)
                if all_metrics else 0.0
            ),
            'avg_time_ms': (
                sum(m['avg_time_ms'] for m in all_metrics) / len(all_metrics)
                if all_metrics else 0.0
            ),
        }

    def __repr__(self) -> str:
        """String representation."""
        enabled = len(self.list_enabled())
        return f"<SkillRegistry({enabled}/{len(self._skills)} enabled)>"
