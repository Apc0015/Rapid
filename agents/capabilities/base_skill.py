"""
base_skill.py — Base class for all agent skills.

A Skill is a reusable capability that an agent can execute to solve a specific problem.
Skills can be composed together to handle complex queries.

Example:
    class RevenueForecasting(BaseSkill):
        name = "forecast_revenue"
        description = "Forecast Q4 revenue based on historical data"

        async def execute(self, context: SkillContext) -> SkillResult:
            # Run forecast logic
            return SkillResult(data=forecast, confidence=0.92)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class SkillStatus(Enum):
    """Skill execution status."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class SkillContext:
    """Context passed to a skill during execution."""

    query: str                          # Original user query
    dept_tag: str                       # Department (finance, sales, etc.)
    user_permissions: Dict[str, Any]   # User's access control
    metadata: Dict[str, Any] = field(default_factory=dict)  # Arbitrary context

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from metadata."""
        return self.metadata.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in metadata."""
        self.metadata[key] = value


@dataclass
class SkillResult:
    """Result returned from a skill execution."""

    data: Any                           # The result (could be dict, list, string, etc.)
    status: SkillStatus = SkillStatus.SUCCESS
    confidence: float = 0.0             # 0.0-1.0, how confident in this result
    time_ms: int = 0                    # Execution time in milliseconds
    sources: List[str] = field(default_factory=list)  # Data sources used
    error: Optional[str] = None         # Error message if failed
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info

    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == SkillStatus.SUCCESS


class BaseSkill(ABC):
    """
    Abstract base class for all agent skills.

    A skill is a discrete capability that an agent can use to solve part of a query.
    Skills are composable—multiple skills can work together to answer complex questions.

    Attributes:
        name: Unique identifier (e.g., 'sql_query', 'fraud_detection')
        description: Human-readable description of what this skill does
        enabled: Whether this skill is available (can be toggled by admin)
        priority: Execution priority (0-10, higher = more preferred)
    """

    # Override these in subclasses
    name: str = ""
    description: str = ""
    enabled: bool = True
    priority: int = 5  # Default priority (0-10 scale)

    def __init__(self):
        """Initialize the skill."""
        if not self.name:
            raise ValueError(f"Skill {self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(f"Skill {self.__class__.__name__} must define 'description'")

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        Execute the skill.

        Args:
            context: SkillContext with query, dept, permissions, etc.

        Returns:
            SkillResult with data, status, confidence, sources

        Raises:
            Exception: Any error during execution (caught by caller)
        """
        pass

    def required_connectors(self) -> List[str]:
        """
        Return list of connector names required by this skill.

        Examples:
            ['database', 'web']  # Needs database and web connectors
            ['faiss']            # Needs FAISS vector store

        Override if your skill needs specific connectors.
        """
        return []

    def applicable_to_depts(self) -> List[str]:
        """
        Return list of departments where this skill is applicable.

        Examples:
            ['finance']           # Only finance agents
            ['sales', 'marketing'] # Multiple departments
            []                     # All departments (default)

        Override if skill is department-specific.
        """
        return []  # Empty = available to all departments

    def get_config(self) -> Dict[str, Any]:
        """
        Return skill configuration (displayed in admin panel).

        Override to expose tunable parameters.

        Example:
            {
                'timeout_seconds': 30,
                'max_retries': 3,
                'cache_enabled': True
            }
        """
        return {
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'priority': self.priority,
        }

    async def health_check(self) -> bool:
        """
        Check if this skill is healthy (can connect to required services).

        Override if your skill needs health checking.

        Returns:
            True if healthy, False otherwise
        """
        return True

    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__}(name='{self.name}', priority={self.priority}, enabled={self.enabled})>"


class ComposableSkill(BaseSkill):
    """
    Base class for skills that can call other skills.

    Useful for complex skills that orchestrate multiple sub-skills.

    Example:
        class ChurnPredictionSkill(ComposableSkill):
            async def execute(self, context):
                # Call other skills
                activity = await self.call_skill('user_activity_summary', context)
                engagement = await self.call_skill('engagement_score', context)
                # Combine results
                ...
    """

    def __init__(self, skill_registry=None):
        """
        Initialize composable skill.

        Args:
            skill_registry: SkillRegistry instance for calling other skills
        """
        super().__init__()
        self._skill_registry = skill_registry

    async def call_skill(self, skill_name: str, context: SkillContext) -> SkillResult:
        """
        Call another skill from this skill.

        Args:
            skill_name: Name of the skill to call
            context: Context to pass to the skill

        Returns:
            SkillResult from the called skill

        Raises:
            ValueError: If skill not found
        """
        if not self._skill_registry:
            raise RuntimeError("ComposableSkill needs skill_registry initialized")

        skill = self._skill_registry.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found in registry")

        return await skill.execute(context)
