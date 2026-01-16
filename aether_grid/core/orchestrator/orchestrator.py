"""
ÆTHER-Grid Orchestrator

The central coordination layer that manages task decomposition,
agent handoffs, and goal management for the multi-agent system.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import structlog

from aether_grid.core.base import (
    Action,
    BaseAgent,
    Result,
    RiskLevel,
    Task,
    TaskPriority,
    TaskStatus,
)

logger = structlog.get_logger(__name__)


class AgentType(Enum):
    """Types of agents in the system."""

    ANALYST = "analyst"
    RISK = "risk"
    EXECUTION = "execution"
    QUANTUM = "quantum"


@dataclass
class AgentRegistration:
    """Registration information for an agent."""

    agent: BaseAgent
    agent_type: AgentType
    capabilities: list[str] = field(default_factory=list)
    priority: int = 0
    max_concurrent_tasks: int = 5
    current_tasks: int = 0
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_health_check: Optional[datetime] = None
    is_healthy: bool = True


@dataclass
class TaskPlan:
    """Represents a decomposed task plan."""

    id: UUID = field(default_factory=uuid4)
    original_task: Task = field(default_factory=Task)
    subtasks: list[Task] = field(default_factory=list)
    execution_order: list[list[UUID]] = field(default_factory=list)  # Stages of parallel tasks
    dependencies: dict[UUID, list[UUID]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class TaskQueue:
    """Priority queue for task scheduling."""

    def __init__(self):
        self._queues: dict[TaskPriority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in TaskPriority
        }
        self._task_count = 0

    async def put(self, task: Task) -> None:
        """Add a task to the appropriate priority queue."""
        await self._queues[task.priority].put(task)
        self._task_count += 1

    async def get(self) -> Task:
        """Get the highest priority task available."""
        while True:
            for priority in TaskPriority:
                queue = self._queues[priority]
                if not queue.empty():
                    task = await queue.get()
                    self._task_count -= 1
                    return task
            # If all queues are empty, wait a bit
            await asyncio.sleep(0.01)

    def empty(self) -> bool:
        """Check if all queues are empty."""
        return all(q.empty() for q in self._queues.values())

    @property
    def size(self) -> int:
        """Total number of tasks in all queues."""
        return self._task_count


class Orchestrator:
    """
    Central coordination layer for ÆTHER-Grid multi-agent system.

    The Orchestrator manages:
    - Agent registration and discovery
    - Task decomposition and planning
    - Task assignment and load balancing
    - Agent handoffs and coordination
    - Result aggregation
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        task_timeout_seconds: int = 300,
        enable_load_balancing: bool = True,
    ):
        self.id = uuid4()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_timeout_seconds = task_timeout_seconds
        self.enable_load_balancing = enable_load_balancing

        self._agents: dict[str, AgentRegistration] = {}
        self._task_queue = TaskQueue()
        self._active_tasks: dict[UUID, Task] = {}
        self._completed_tasks: dict[UUID, Result] = {}
        self._task_assignments: dict[UUID, str] = {}  # task_id -> agent_id

        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None

        self.logger = structlog.get_logger(__name__).bind(orchestrator_id=str(self.id))

        # Callbacks for extensibility
        self._on_task_complete: list[Callable[[Task, Result], None]] = []
        self._on_task_failed: list[Callable[[Task, str], None]] = []

    # Agent Management
    async def register_agent(
        self,
        agent: BaseAgent,
        agent_type: AgentType,
        capabilities: Optional[list[str]] = None,
        priority: int = 0,
    ) -> str:
        """Register an agent with the orchestrator."""
        registration = AgentRegistration(
            agent=agent,
            agent_type=agent_type,
            capabilities=capabilities or agent.get_capabilities(),
            priority=priority,
        )
        self._agents[agent.agent_id] = registration
        await agent.initialize()
        self.logger.info(
            "agent_registered",
            agent_id=agent.agent_id,
            agent_type=agent_type.value,
            capabilities=registration.capabilities,
        )
        return agent.agent_id

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the orchestrator."""
        if agent_id not in self._agents:
            return False

        registration = self._agents[agent_id]
        await registration.agent.shutdown()
        del self._agents[agent_id]
        self.logger.info("agent_unregistered", agent_id=agent_id)
        return True

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by ID."""
        registration = self._agents.get(agent_id)
        return registration.agent if registration else None

    def get_agents_by_type(self, agent_type: AgentType) -> list[BaseAgent]:
        """Get all agents of a specific type."""
        return [
            reg.agent
            for reg in self._agents.values()
            if reg.agent_type == agent_type
        ]

    def find_capable_agent(self, required_capability: str) -> Optional[BaseAgent]:
        """Find an agent with a specific capability."""
        for registration in self._agents.values():
            if required_capability in registration.capabilities:
                return registration.agent
        return None

    # Task Management
    async def submit_task(self, task: Task) -> UUID:
        """Submit a task for processing."""
        task.status = TaskStatus.QUEUED
        await self._task_queue.put(task)
        self.logger.info(
            "task_submitted",
            task_id=str(task.id),
            task_name=task.name,
            priority=task.priority.name,
        )
        return task.id

    async def submit_goal(
        self,
        goal: str,
        context: Optional[dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> TaskPlan:
        """
        Submit a high-level goal for decomposition and execution.

        The orchestrator will decompose the goal into subtasks
        and coordinate their execution across agents.
        """
        # Create the root task from the goal
        root_task = Task(
            name=goal,
            description=f"Goal: {goal}",
            priority=priority,
            context=context or {},
        )

        # Decompose into subtasks
        plan = await self._decompose_goal(root_task)

        # Submit all subtasks
        for subtask in plan.subtasks:
            subtask.parent_task_id = root_task.id
            root_task.subtask_ids.append(subtask.id)
            await self.submit_task(subtask)

        self.logger.info(
            "goal_submitted",
            goal=goal,
            plan_id=str(plan.id),
            subtask_count=len(plan.subtasks),
        )
        return plan

    async def _decompose_goal(self, task: Task) -> TaskPlan:
        """
        Decompose a high-level goal into executable subtasks.

        This implements the Planner-Worker pattern where complex
        goals are broken down into discrete, manageable tasks.
        """
        plan = TaskPlan(original_task=task)

        # Default decomposition strategy
        # In practice, this would use LLM-based planning
        subtasks = []

        # Stage 1: Analysis
        analysis_task = Task(
            name=f"Analyze: {task.name}",
            description=f"Perform initial analysis for: {task.description}",
            priority=task.priority,
            target_agent="analyst",
            context={"parent_goal": task.name, **task.context},
        )
        subtasks.append(analysis_task)

        # Stage 2: Risk Assessment
        risk_task = Task(
            name=f"Risk Assessment: {task.name}",
            description=f"Assess risks for: {task.description}",
            priority=task.priority,
            target_agent="risk",
            context={"parent_goal": task.name, **task.context},
        )
        subtasks.append(risk_task)
        plan.dependencies[risk_task.id] = [analysis_task.id]

        # Stage 3: Execution (if applicable)
        if task.context.get("requires_execution", True):
            exec_task = Task(
                name=f"Execute: {task.name}",
                description=f"Execute actions for: {task.description}",
                priority=task.priority,
                target_agent="execution",
                context={"parent_goal": task.name, **task.context},
            )
            subtasks.append(exec_task)
            plan.dependencies[exec_task.id] = [analysis_task.id, risk_task.id]

        plan.subtasks = subtasks
        plan.execution_order = self._compute_execution_order(plan)

        return plan

    def _compute_execution_order(self, plan: TaskPlan) -> list[list[UUID]]:
        """Compute parallel execution stages from dependencies."""
        # Simple topological sort to determine execution stages
        remaining = {t.id for t in plan.subtasks}
        completed: set[UUID] = set()
        stages: list[list[UUID]] = []

        while remaining:
            # Find tasks with all dependencies satisfied
            ready = []
            for task_id in remaining:
                deps = plan.dependencies.get(task_id, [])
                if all(d in completed for d in deps):
                    ready.append(task_id)

            if not ready:
                # Circular dependency or error
                self.logger.error("circular_dependency_detected", remaining=list(remaining))
                break

            stages.append(ready)
            completed.update(ready)
            remaining -= set(ready)

        return stages

    # Task Execution
    async def start(self) -> None:
        """Start the orchestrator's main processing loop."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._process_tasks())
        self._health_check_task = asyncio.create_task(self._run_health_checks())
        self.logger.info("orchestrator_started")

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Shutdown all agents
        for registration in self._agents.values():
            await registration.agent.shutdown()

        self.logger.info("orchestrator_stopped")

    async def _process_tasks(self) -> None:
        """Main task processing loop."""
        while self._running:
            if len(self._active_tasks) >= self.max_concurrent_tasks:
                await asyncio.sleep(0.1)
                continue

            if self._task_queue.empty():
                await asyncio.sleep(0.01)
                continue

            task = await self._task_queue.get()
            asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task."""
        task.start()
        self._active_tasks[task.id] = task

        try:
            # Find appropriate agent
            agent = await self._select_agent(task)
            if not agent:
                raise ValueError(f"No suitable agent found for task: {task.name}")

            self._task_assignments[task.id] = agent.agent_id

            # Execute with timeout
            result = await asyncio.wait_for(
                agent.process(task),
                timeout=self.task_timeout_seconds,
            )

            task.complete()
            self._completed_tasks[task.id] = result

            self.logger.info(
                "task_completed",
                task_id=str(task.id),
                agent_id=agent.agent_id,
                success=result.success,
            )

            for callback in self._on_task_complete:
                callback(task, result)

        except asyncio.TimeoutError:
            error_msg = f"Task timed out after {self.task_timeout_seconds}s"
            task.fail(error_msg)
            self.logger.error("task_timeout", task_id=str(task.id))

            for callback in self._on_task_failed:
                callback(task, error_msg)

        except Exception as e:
            error_msg = str(e)
            task.fail(error_msg)
            self.logger.error("task_failed", task_id=str(task.id), error=error_msg)

            # Retry if possible
            if task.can_retry():
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                await self.submit_task(task)
                self.logger.info("task_retry", task_id=str(task.id), retry=task.retry_count)
            else:
                for callback in self._on_task_failed:
                    callback(task, error_msg)

        finally:
            del self._active_tasks[task.id]
            if task.id in self._task_assignments:
                del self._task_assignments[task.id]

    async def _select_agent(self, task: Task) -> Optional[BaseAgent]:
        """Select the best agent for a task."""
        # If task specifies target agent type, filter by that
        if task.target_agent:
            candidates = [
                reg for reg in self._agents.values()
                if reg.agent_type.value == task.target_agent
            ]
        else:
            candidates = list(self._agents.values())

        if not candidates:
            return None

        # Filter by health
        candidates = [c for c in candidates if c.is_healthy]

        if not candidates:
            return None

        if self.enable_load_balancing:
            # Select agent with lowest current task count
            candidates.sort(key=lambda c: (c.current_tasks, -c.priority))

        # Return the best candidate
        selected = candidates[0]
        selected.current_tasks += 1
        return selected.agent

    # Health Monitoring
    async def _run_health_checks(self) -> None:
        """Periodically check agent health."""
        while self._running:
            for agent_id, registration in self._agents.items():
                try:
                    health = await registration.agent.health_check()
                    registration.is_healthy = health.get("is_active", False)
                    registration.last_health_check = datetime.utcnow()
                except Exception as e:
                    registration.is_healthy = False
                    self.logger.warning(
                        "health_check_failed",
                        agent_id=agent_id,
                        error=str(e),
                    )

            await asyncio.sleep(30)

    # Result Retrieval
    async def get_result(self, task_id: UUID, timeout: float = 60.0) -> Optional[Result]:
        """Wait for and retrieve a task result."""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            if task_id in self._completed_tasks:
                return self._completed_tasks[task_id]
            await asyncio.sleep(0.1)

        return None

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "orchestrator_id": str(self.id),
            "running": self._running,
            "registered_agents": len(self._agents),
            "queued_tasks": self._task_queue.size,
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._completed_tasks),
            "agents": {
                agent_id: {
                    "type": reg.agent_type.value,
                    "healthy": reg.is_healthy,
                    "current_tasks": reg.current_tasks,
                }
                for agent_id, reg in self._agents.items()
            },
        }

    # Callback Registration
    def on_task_complete(self, callback: Callable[[Task, Result], None]) -> None:
        """Register a callback for task completion."""
        self._on_task_complete.append(callback)

    def on_task_failed(self, callback: Callable[[Task, str], None]) -> None:
        """Register a callback for task failure."""
        self._on_task_failed.append(callback)
