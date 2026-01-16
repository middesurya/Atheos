"""
Agent-to-Agent (A2A) Protocol for ÆTHER-Grid

Enables agents to discover and collaborate with each other,
including specialized quantum routines for complex optimization.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


class MessageType(Enum):
    """Types of A2A messages."""

    # Discovery
    DISCOVER = "discover"
    ANNOUNCE = "announce"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"

    # Task delegation
    TASK_REQUEST = "task_request"
    TASK_ACCEPT = "task_accept"
    TASK_REJECT = "task_reject"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"

    # Coordination
    SYNC = "sync"
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"

    # Data exchange
    DATA_SHARE = "data_share"
    DATA_REQUEST = "data_request"
    DATA_RESPONSE = "data_response"


class MessagePriority(Enum):
    """Priority levels for messages."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentCapability:
    """Describes a capability an agent can provide."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    cost_estimate: float = 0.0  # Relative cost/complexity
    execution_time_estimate_ms: int = 0
    requires_context: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "cost_estimate": self.cost_estimate,
            "execution_time_estimate_ms": self.execution_time_estimate_ms,
        }


@dataclass
class A2AMessage:
    """A message in the A2A protocol."""

    id: UUID = field(default_factory=uuid4)
    message_type: MessageType = MessageType.HEARTBEAT
    sender_id: str = ""
    recipient_id: Optional[str] = None  # None = broadcast
    priority: MessagePriority = MessagePriority.NORMAL
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[UUID] = None  # For request-response pairs
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    requires_ack: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "type": self.message_type.value,
            "sender": self.sender_id,
            "recipient": self.recipient_id,
            "priority": self.priority.value,
            "payload": self.payload,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "timestamp": self.timestamp.isoformat(),
        }

    def is_expired(self) -> bool:
        """Check if message has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


@dataclass
class AgentDescriptor:
    """Describes an agent in the A2A network."""

    agent_id: str = ""
    name: str = ""
    agent_type: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    endpoint: str = ""
    status: str = "unknown"
    last_seen: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "status": self.status,
            "last_seen": self.last_seen.isoformat(),
        }


class MessageHandler(ABC):
    """Abstract handler for A2A messages."""

    @abstractmethod
    async def handle(self, message: A2AMessage) -> Optional[A2AMessage]:
        """Handle an incoming message and optionally return a response."""
        pass


class A2ARouter:
    """Routes A2A messages between agents."""

    def __init__(self):
        self._agents: dict[str, AgentDescriptor] = {}
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._pending_responses: dict[UUID, asyncio.Future] = {}
        self._running = False
        self.logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        """Start the message routing loop."""
        self._running = True
        asyncio.create_task(self._process_messages())
        self.logger.info("a2a_router_started")

    async def stop(self) -> None:
        """Stop the router."""
        self._running = False
        self.logger.info("a2a_router_stopped")

    def register_agent(self, descriptor: AgentDescriptor) -> None:
        """Register an agent with the router."""
        self._agents[descriptor.agent_id] = descriptor
        self._handlers[descriptor.agent_id] = []
        self.logger.info("agent_registered", agent_id=descriptor.agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the router."""
        if agent_id in self._agents:
            del self._agents[agent_id]
        if agent_id in self._handlers:
            del self._handlers[agent_id]
        self.logger.info("agent_unregistered", agent_id=agent_id)

    def add_handler(self, agent_id: str, handler: MessageHandler) -> None:
        """Add a message handler for an agent."""
        if agent_id not in self._handlers:
            self._handlers[agent_id] = []
        self._handlers[agent_id].append(handler)

    async def send(self, message: A2AMessage) -> None:
        """Send a message through the router."""
        await self._message_queue.put(message)

    async def send_and_wait(
        self,
        message: A2AMessage,
        timeout: float = 30.0,
    ) -> Optional[A2AMessage]:
        """Send a message and wait for a response."""
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_responses[message.id] = future

        await self.send(message)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            self.logger.warning("message_timeout", message_id=str(message.id))
            return None
        finally:
            self._pending_responses.pop(message.id, None)

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue

            # Skip expired messages
            if message.is_expired():
                self.logger.debug("message_expired", message_id=str(message.id))
                continue

            # Route to recipient or broadcast
            if message.recipient_id:
                await self._deliver_to_agent(message, message.recipient_id)
            else:
                # Broadcast to all agents except sender
                for agent_id in self._agents:
                    if agent_id != message.sender_id:
                        await self._deliver_to_agent(message, agent_id)

    async def _deliver_to_agent(self, message: A2AMessage, agent_id: str) -> None:
        """Deliver a message to a specific agent."""
        handlers = self._handlers.get(agent_id, [])

        for handler in handlers:
            try:
                response = await handler.handle(message)
                if response:
                    # Check if this is a response to a pending request
                    if message.id in self._pending_responses:
                        future = self._pending_responses[message.id]
                        if not future.done():
                            future.set_result(response)
                    else:
                        # Send response as a new message
                        await self.send(response)
            except Exception as e:
                self.logger.error(
                    "handler_error",
                    agent_id=agent_id,
                    error=str(e),
                )

    def discover_agents(
        self,
        capability: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> list[AgentDescriptor]:
        """Discover agents matching criteria."""
        results = []

        for agent in self._agents.values():
            # Filter by type
            if agent_type and agent.agent_type != agent_type:
                continue

            # Filter by capability
            if capability:
                has_capability = any(
                    c.name == capability for c in agent.capabilities
                )
                if not has_capability:
                    continue

            results.append(agent)

        return results

    def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        """Get an agent descriptor by ID."""
        return self._agents.get(agent_id)


class A2AClient:
    """Client interface for agents to use the A2A protocol."""

    def __init__(self, agent_id: str, router: A2ARouter):
        self.agent_id = agent_id
        self.router = router
        self.logger = structlog.get_logger(__name__).bind(agent_id=agent_id)

    async def announce(self, capabilities: list[AgentCapability]) -> None:
        """Announce this agent's capabilities to the network."""
        message = A2AMessage(
            message_type=MessageType.ANNOUNCE,
            sender_id=self.agent_id,
            payload={"capabilities": [c.to_dict() for c in capabilities]},
        )
        await self.router.send(message)
        self.logger.info("announced_capabilities", count=len(capabilities))

    async def discover(
        self,
        capability: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> list[AgentDescriptor]:
        """Discover other agents in the network."""
        return self.router.discover_agents(capability, agent_type)

    async def query_capabilities(self, target_agent_id: str) -> list[AgentCapability]:
        """Query capabilities of a specific agent."""
        message = A2AMessage(
            message_type=MessageType.CAPABILITY_QUERY,
            sender_id=self.agent_id,
            recipient_id=target_agent_id,
        )

        response = await self.router.send_and_wait(message, timeout=10.0)
        if response and response.payload.get("capabilities"):
            return [
                AgentCapability(**c) for c in response.payload["capabilities"]
            ]
        return []

    async def request_task(
        self,
        target_agent_id: str,
        task_name: str,
        parameters: dict[str, Any],
        timeout: float = 60.0,
    ) -> Optional[dict[str, Any]]:
        """Request another agent to perform a task."""
        message = A2AMessage(
            message_type=MessageType.TASK_REQUEST,
            sender_id=self.agent_id,
            recipient_id=target_agent_id,
            payload={
                "task_name": task_name,
                "parameters": parameters,
            },
            requires_ack=True,
        )

        response = await self.router.send_and_wait(message, timeout=timeout)
        if response:
            return response.payload
        return None

    async def share_data(
        self,
        data: dict[str, Any],
        target_agent_id: Optional[str] = None,
    ) -> None:
        """Share data with other agents."""
        message = A2AMessage(
            message_type=MessageType.DATA_SHARE,
            sender_id=self.agent_id,
            recipient_id=target_agent_id,
            payload={"data": data},
        )
        await self.router.send(message)

    async def send_heartbeat(self, status: str = "healthy") -> None:
        """Send a heartbeat to the network."""
        message = A2AMessage(
            message_type=MessageType.HEARTBEAT,
            sender_id=self.agent_id,
            payload={"status": status, "timestamp": datetime.utcnow().isoformat()},
            expires_at=datetime.utcnow() + timedelta(seconds=30),
        )
        await self.router.send(message)


class QuantumAgentBridge:
    """
    Bridge for connecting classical agents to quantum optimization routines.

    This enables A2A discovery and collaboration between classical AI agents
    and quantum computing modules.
    """

    def __init__(self, router: A2ARouter):
        self.router = router
        self.quantum_agent_id = "quantum-optimizer"
        self.logger = structlog.get_logger(__name__)

        # Register quantum capabilities
        self._register_quantum_capabilities()

    def _register_quantum_capabilities(self) -> None:
        """Register quantum optimization capabilities."""
        capabilities = [
            AgentCapability(
                name="qaoa_optimization",
                description="Quantum Approximate Optimization Algorithm for combinatorial problems",
                input_schema={
                    "type": "object",
                    "properties": {
                        "cost_function": {"type": "string"},
                        "num_qubits": {"type": "integer"},
                        "layers": {"type": "integer"},
                    },
                },
                cost_estimate=10.0,
                execution_time_estimate_ms=5000,
            ),
            AgentCapability(
                name="vqe_optimization",
                description="Variational Quantum Eigensolver for energy optimization",
                input_schema={
                    "type": "object",
                    "properties": {
                        "hamiltonian": {"type": "object"},
                        "ansatz": {"type": "string"},
                    },
                },
                cost_estimate=15.0,
                execution_time_estimate_ms=10000,
            ),
            AgentCapability(
                name="quantum_sampling",
                description="Quantum sampling for probabilistic models",
                input_schema={
                    "type": "object",
                    "properties": {
                        "distribution": {"type": "object"},
                        "num_samples": {"type": "integer"},
                    },
                },
                cost_estimate=5.0,
                execution_time_estimate_ms=2000,
            ),
        ]

        descriptor = AgentDescriptor(
            agent_id=self.quantum_agent_id,
            name="Quantum Optimizer",
            agent_type="quantum",
            capabilities=capabilities,
            status="available",
        )
        self.router.register_agent(descriptor)

    async def request_optimization(
        self,
        optimization_type: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Request a quantum optimization from the bridge."""
        client = A2AClient("bridge-client", self.router)

        result = await client.request_task(
            target_agent_id=self.quantum_agent_id,
            task_name=optimization_type,
            parameters=parameters,
            timeout=120.0,
        )

        return result or {"error": "No response from quantum optimizer"}
