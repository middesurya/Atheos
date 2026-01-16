"""Tests for the Orchestrator."""

import pytest
from uuid import uuid4

from aether_grid.core.base import Task, TaskPriority, TaskStatus
from aether_grid.core.orchestrator import (
    AgentType,
    Orchestrator,
    TaskQueue,
)


class TestTaskQueue:
    """Tests for TaskQueue."""

    @pytest.fixture
    def queue(self):
        return TaskQueue()

    @pytest.mark.asyncio
    async def test_put_and_get(self, queue):
        """Test basic put and get operations."""
        task = Task(name="test", priority=TaskPriority.MEDIUM)
        await queue.put(task)

        assert not queue.empty()
        assert queue.size == 1

        retrieved = await queue.get()
        assert retrieved.id == task.id
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        """Test that higher priority tasks are retrieved first."""
        low = Task(name="low", priority=TaskPriority.LOW)
        high = Task(name="high", priority=TaskPriority.HIGH)
        medium = Task(name="medium", priority=TaskPriority.MEDIUM)

        await queue.put(low)
        await queue.put(medium)
        await queue.put(high)

        # Should get high priority first
        first = await queue.get()
        assert first.name == "high"

        second = await queue.get()
        assert second.name == "medium"

        third = await queue.get()
        assert third.name == "low"


class TestOrchestrator:
    """Tests for Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return Orchestrator(max_concurrent_tasks=5)

    def test_initialization(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator.max_concurrent_tasks == 5
        assert not orchestrator._running

    @pytest.mark.asyncio
    async def test_submit_task(self, orchestrator):
        """Test task submission."""
        task = Task(name="test task", priority=TaskPriority.HIGH)
        task_id = await orchestrator.submit_task(task)

        assert task_id == task.id
        assert task.status == TaskStatus.QUEUED

    def test_get_status(self, orchestrator):
        """Test status retrieval."""
        status = orchestrator.get_status()

        assert "orchestrator_id" in status
        assert status["running"] is False
        assert status["registered_agents"] == 0
        assert status["queued_tasks"] == 0


class TestTask:
    """Tests for Task class."""

    def test_task_creation(self):
        """Test task creation with defaults."""
        task = Task()
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.MEDIUM
        assert task.retry_count == 0

    def test_task_start(self):
        """Test task start."""
        task = Task()
        task.start()

        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None

    def test_task_complete(self):
        """Test task completion."""
        task = Task()
        task.start()
        task.complete()

        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None

    def test_task_fail(self):
        """Test task failure."""
        task = Task()
        task.fail("test error")

        assert task.status == TaskStatus.FAILED
        assert task.metadata["failure_reason"] == "test error"

    def test_can_retry(self):
        """Test retry logic."""
        task = Task(max_retries=3)
        assert task.can_retry()

        task.retry_count = 3
        assert not task.can_retry()
