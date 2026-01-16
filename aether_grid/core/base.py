"""
Base classes for the ÆTHER-Grid multi-agent system.

This module defines the foundational abstractions that all agents
and components build upon.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


class TaskPriority(Enum):
    """Priority levels for task scheduling."""

    CRITICAL = 0  # Immediate attention required
    HIGH = 1  # Important, process soon
    MEDIUM = 2  # Normal priority
    LOW = 3  # Can be deferred
    BACKGROUND = 4  # Process when idle


class TaskStatus(Enum):
    """Status of a task in the system."""

    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ActionType(Enum):
    """Types of actions agents can perform."""

    QUERY = "query"  # Read-only data retrieval
    ANALYZE = "analyze"  # Data analysis and processing
    PREDICT = "predict"  # ML-based prediction
    OPTIMIZE = "optimize"  # Optimization routine
    EXECUTE = "execute"  # Grid control action
    ALERT = "alert"  # Notification/alert
    AUDIT = "audit"  # Compliance logging


class RiskLevel(Enum):
    """Risk classification for actions."""

    NONE = 0  # No risk, informational
    LOW = 1  # Minor impact if failed
    MEDIUM = 2  # Moderate impact, reversible
    HIGH = 3  # Significant impact, requires approval
    CRITICAL = 4  # Major impact, human oversight required


@dataclass
class Action:
    """
    Represents an action to be performed by an agent.

    Actions are the atomic units of work in ÆTHER-Grid. Each action
    has a type, associated data, and risk classification for audit purposes.
    """

    id: UUID = field(default_factory=uuid4)
    action_type: ActionType = ActionType.QUERY
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    reversible: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_audit_record(self) -> dict[str, Any]:
        """Generate an audit-compliant record of this action."""
        return {
            "action_id": str(self.id),
            "type": self.action_type.value,
            "target": self.target,
            "parameters": self.parameters,
            "risk_level": self.risk_level.name,
            "requires_approval": self.requires_approval,
            "reversible": self.reversible,
            "timestamp": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """
    Represents a task to be processed by the agent system.

    Tasks are higher-level work units that may decompose into
    multiple actions across different agents.
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    source_agent: Optional[str] = None
    target_agent: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    parent_task_id: Optional[UUID] = None
    subtask_ids: list[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()

    def complete(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def fail(self, reason: str = "") -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.metadata["failure_reason"] = reason

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries


@dataclass
class Result:
    """
    Represents the result of a task or action execution.

    Results carry both the output data and metadata about the
    execution for audit and analysis purposes.
    """

    id: UUID = field(default_factory=uuid4)
    task_id: Optional[UUID] = None
    action_id: Optional[UUID] = None
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    agent_id: str = ""
    execution_time_ms: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    reasoning_trace: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_audit_record(self) -> dict[str, Any]:
        """Generate an audit-compliant record of this result."""
        return {
            "result_id": str(self.id),
            "task_id": str(self.task_id) if self.task_id else None,
            "action_id": str(self.action_id) if self.action_id else None,
            "success": self.success,
            "error": self.error,
            "error_code": self.error_code,
            "agent_id": self.agent_id,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.created_at.isoformat(),
            "reasoning_trace": self.reasoning_trace,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all ÆTHER-Grid agents.

    All specialized agents (Analyst, Risk, Execution) inherit from this
    base class and implement the required abstract methods.
    """

    def __init__(self, agent_id: str, name: str, description: str = ""):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.is_active = False
        self.created_at = datetime.utcnow()
        self.logger = structlog.get_logger(__name__).bind(agent_id=agent_id, agent_name=name)
        self._task_history: list[UUID] = []

    @abstractmethod
    async def process(self, task: Task) -> Result:
        """
        Process a task and return the result.

        This is the main entry point for task handling. Implementations
        should handle the full lifecycle of task processing.

        Args:
            task: The task to process

        Returns:
            Result object containing execution outcome
        """
        pass

    @abstractmethod
    async def validate(self, action: Action) -> bool:
        """
        Validate an action before execution.

        Check if the action is safe and permitted according to
        agent policies and system constraints.

        Args:
            action: The action to validate

        Returns:
            True if action is valid and can proceed
        """
        pass

    async def initialize(self) -> None:
        """Initialize the agent and its resources."""
        self.is_active = True
        self.logger.info("agent_initialized")

    async def shutdown(self) -> None:
        """Gracefully shutdown the agent."""
        self.is_active = False
        self.logger.info("agent_shutdown")

    async def health_check(self) -> dict[str, Any]:
        """Return agent health status."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "is_active": self.is_active,
            "tasks_processed": len(self._task_history),
            "uptime_seconds": (datetime.utcnow() - self.created_at).total_seconds(),
        }

    def get_capabilities(self) -> list[str]:
        """Return list of agent capabilities."""
        return []

    def _record_task(self, task_id: UUID) -> None:
        """Record a task in history for tracking."""
        self._task_history.append(task_id)
        # Keep only last 1000 tasks
        if len(self._task_history) > 1000:
            self._task_history = self._task_history[-1000:]
