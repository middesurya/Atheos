"""
Execution Agent for ÆTHER-Grid

Interacts with smart grid hardware and APIs via the Model Context
Protocol (MCP) to adjust loads autonomously.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

import structlog

from aether_grid.core.base import (
    Action,
    ActionType,
    BaseAgent,
    Result,
    RiskLevel,
    Task,
)


class DeviceType(Enum):
    """Types of grid devices."""

    GENERATOR = "generator"
    LOAD = "load"
    STORAGE = "storage"
    TRANSFORMER = "transformer"
    SWITCH = "switch"
    INVERTER = "inverter"
    METER = "meter"


class DeviceState(Enum):
    """Operational states for devices."""

    ONLINE = "online"
    OFFLINE = "offline"
    STANDBY = "standby"
    FAULT = "fault"
    MAINTENANCE = "maintenance"


class CommandType(Enum):
    """Types of commands for grid devices."""

    SET_POWER = "set_power"
    SET_VOLTAGE = "set_voltage"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    START = "start"
    STOP = "stop"
    CHARGE = "charge"
    DISCHARGE = "discharge"
    SET_MODE = "set_mode"


@dataclass
class GridDevice:
    """Represents a device in the grid."""

    id: str = ""
    name: str = ""
    device_type: DeviceType = DeviceType.LOAD
    state: DeviceState = DeviceState.OFFLINE
    location: str = ""
    capacity_kw: float = 0.0
    current_output_kw: float = 0.0
    voltage_level: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.device_type.value,
            "state": self.state.value,
            "location": self.location,
            "capacity_kw": self.capacity_kw,
            "current_output_kw": self.current_output_kw,
        }


@dataclass
class GridCommand:
    """A command to be executed on a grid device."""

    id: UUID = field(default_factory=uuid4)
    command_type: CommandType = CommandType.SET_POWER
    device_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    timeout_seconds: int = 30
    requires_confirmation: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None
    result: Optional[str] = None
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "type": self.command_type.value,
            "device_id": self.device_id,
            "parameters": self.parameters,
            "success": self.success,
            "result": self.result,
        }


@dataclass
class ExecutionResult:
    """Result of a grid command execution."""

    command_id: UUID = field(default_factory=uuid4)
    success: bool = False
    message: str = ""
    device_state_before: Optional[dict] = None
    device_state_after: Optional[dict] = None
    execution_time_ms: float = 0.0
    reversible: bool = True
    reversal_command: Optional[GridCommand] = None


class MCPHandler(ABC):
    """Abstract handler for Model Context Protocol communication."""

    @abstractmethod
    async def connect(self, endpoint: str) -> bool:
        """Connect to an MCP endpoint."""
        pass

    @abstractmethod
    async def send_command(self, command: GridCommand) -> ExecutionResult:
        """Send a command through MCP."""
        pass

    @abstractmethod
    async def get_device_state(self, device_id: str) -> Optional[GridDevice]:
        """Get current state of a device."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the endpoint."""
        pass


class SimulatedMCPHandler(MCPHandler):
    """Simulated MCP handler for testing."""

    def __init__(self):
        self.connected = False
        self.endpoint = ""
        self._devices: dict[str, GridDevice] = {}
        self._initialize_simulated_devices()
        self.logger = structlog.get_logger(__name__)

    def _initialize_simulated_devices(self) -> None:
        """Initialize simulated grid devices."""
        # Generators
        self._devices["gen-001"] = GridDevice(
            id="gen-001",
            name="Solar Farm Alpha",
            device_type=DeviceType.GENERATOR,
            state=DeviceState.ONLINE,
            location="Zone A",
            capacity_kw=5000,
            current_output_kw=3200,
        )
        self._devices["gen-002"] = GridDevice(
            id="gen-002",
            name="Wind Farm Beta",
            device_type=DeviceType.GENERATOR,
            state=DeviceState.ONLINE,
            location="Zone B",
            capacity_kw=8000,
            current_output_kw=5500,
        )

        # Storage
        self._devices["stor-001"] = GridDevice(
            id="stor-001",
            name="Battery Bank 1",
            device_type=DeviceType.STORAGE,
            state=DeviceState.ONLINE,
            location="Zone A",
            capacity_kw=2000,
            current_output_kw=0,
            metadata={"charge_level": 0.75},
        )

        # Loads
        self._devices["load-001"] = GridDevice(
            id="load-001",
            name="Industrial Complex",
            device_type=DeviceType.LOAD,
            state=DeviceState.ONLINE,
            location="Zone C",
            capacity_kw=3000,
            current_output_kw=2100,
        )

    async def connect(self, endpoint: str) -> bool:
        """Simulate connection to MCP endpoint."""
        await asyncio.sleep(0.1)  # Simulate network latency
        self.endpoint = endpoint
        self.connected = True
        self.logger.info("mcp_connected", endpoint=endpoint)
        return True

    async def send_command(self, command: GridCommand) -> ExecutionResult:
        """Simulate sending a command."""
        start_time = datetime.utcnow()

        # Get device
        device = self._devices.get(command.device_id)
        if not device:
            return ExecutionResult(
                command_id=command.id,
                success=False,
                message=f"Device not found: {command.device_id}",
            )

        state_before = device.to_dict()

        # Simulate command execution
        await asyncio.sleep(0.05)  # Simulate execution time

        try:
            result = await self._execute_command(device, command)
            state_after = device.to_dict()
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ExecutionResult(
                command_id=command.id,
                success=True,
                message=result,
                device_state_before=state_before,
                device_state_after=state_after,
                execution_time_ms=execution_time,
                reversible=True,
            )
        except Exception as e:
            return ExecutionResult(
                command_id=command.id,
                success=False,
                message=str(e),
                device_state_before=state_before,
            )

    async def _execute_command(self, device: GridDevice, command: GridCommand) -> str:
        """Execute a specific command on a device."""
        if command.command_type == CommandType.SET_POWER:
            new_power = command.parameters.get("power_kw", device.current_output_kw)
            if new_power > device.capacity_kw:
                raise ValueError(f"Requested power {new_power} exceeds capacity {device.capacity_kw}")
            device.current_output_kw = new_power
            return f"Power set to {new_power} kW"

        elif command.command_type == CommandType.CONNECT:
            device.state = DeviceState.ONLINE
            return "Device connected"

        elif command.command_type == CommandType.DISCONNECT:
            device.state = DeviceState.OFFLINE
            device.current_output_kw = 0
            return "Device disconnected"

        elif command.command_type == CommandType.START:
            device.state = DeviceState.ONLINE
            return "Device started"

        elif command.command_type == CommandType.STOP:
            device.state = DeviceState.STANDBY
            device.current_output_kw = 0
            return "Device stopped"

        elif command.command_type == CommandType.CHARGE:
            if device.device_type != DeviceType.STORAGE:
                raise ValueError("Charge command only valid for storage devices")
            rate = command.parameters.get("rate_kw", 500)
            device.current_output_kw = -rate  # Negative for charging
            return f"Charging at {rate} kW"

        elif command.command_type == CommandType.DISCHARGE:
            if device.device_type != DeviceType.STORAGE:
                raise ValueError("Discharge command only valid for storage devices")
            rate = command.parameters.get("rate_kw", 500)
            device.current_output_kw = rate
            return f"Discharging at {rate} kW"

        else:
            return f"Command {command.command_type.value} executed"

    async def get_device_state(self, device_id: str) -> Optional[GridDevice]:
        """Get current state of a simulated device."""
        return self._devices.get(device_id)

    async def disconnect(self) -> None:
        """Disconnect from simulated endpoint."""
        self.connected = False
        self.endpoint = ""
        self.logger.info("mcp_disconnected")

    def list_devices(self) -> list[GridDevice]:
        """List all available devices."""
        return list(self._devices.values())


class ExecutionAgent(BaseAgent):
    """
    Execution Agent for smart grid interaction.

    Capabilities:
    - Grid device control via MCP protocol
    - Load adjustment and balancing
    - Storage charge/discharge management
    - Emergency response execution
    - Command validation and safety checks
    """

    def __init__(
        self,
        agent_id: str = "execution-001",
        dry_run_mode: bool = False,
        max_load_adjustment_percent: float = 20.0,
    ):
        super().__init__(
            agent_id=agent_id,
            name="Execution Agent",
            description="Smart grid interaction and control",
        )
        self.dry_run_mode = dry_run_mode
        self.max_load_adjustment_percent = max_load_adjustment_percent

        # Use simulated handler by default
        self._mcp_handler: MCPHandler = SimulatedMCPHandler()
        self._command_history: list[GridCommand] = []
        self._pending_confirmations: dict[UUID, GridCommand] = {}

    def get_capabilities(self) -> list[str]:
        """Return agent capabilities."""
        return [
            "device_control",
            "load_adjustment",
            "storage_management",
            "emergency_response",
            "mcp_communication",
        ]

    async def initialize(self) -> None:
        """Initialize the agent and connect to MCP."""
        await super().initialize()
        await self._mcp_handler.connect("simulated://grid")

    async def shutdown(self) -> None:
        """Shutdown the agent and disconnect from MCP."""
        await self._mcp_handler.disconnect()
        await super().shutdown()

    async def process(self, task: Task) -> Result:
        """Process an execution task."""
        start_time = datetime.utcnow()
        self._record_task(task.id)

        try:
            task_type = task.context.get("task_type", "execute")

            if task_type == "execute":
                result_data = await self._execute_command_task(task)
            elif task_type == "adjust_load":
                result_data = await self._adjust_load(task)
            elif task_type == "manage_storage":
                result_data = await self._manage_storage(task)
            elif task_type == "get_status":
                result_data = await self._get_grid_status(task)
            elif task_type == "emergency":
                result_data = await self._handle_emergency(task)
            else:
                result_data = await self._execute_command_task(task)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return Result(
                task_id=task.id,
                success=True,
                data=result_data,
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
                reasoning_trace=[
                    f"Task type: {task_type}",
                    f"Dry run mode: {self.dry_run_mode}",
                    f"Commands executed: {len(self._command_history)}",
                ],
            )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error("execution_failed", error=str(e), task_id=str(task.id))
            return Result(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
            )

    async def validate(self, action: Action) -> bool:
        """Validate an action before execution."""
        # Check action type
        if action.action_type != ActionType.EXECUTE:
            return True  # Non-execute actions are always valid

        # Check risk level
        if action.risk_level == RiskLevel.CRITICAL:
            if not action.requires_approval:
                self.logger.warning(
                    "critical_action_needs_approval",
                    action_id=str(action.id),
                )
                return False

        # Check load adjustment limits
        if "power_change_percent" in action.parameters:
            change = abs(action.parameters["power_change_percent"])
            if change > self.max_load_adjustment_percent:
                self.logger.warning(
                    "load_adjustment_exceeds_limit",
                    requested=change,
                    limit=self.max_load_adjustment_percent,
                )
                return False

        return True

    async def _execute_command_task(self, task: Task) -> dict[str, Any]:
        """Execute a grid command."""
        command_data = task.context.get("command", {})

        command = GridCommand(
            command_type=CommandType(command_data.get("type", "set_power")),
            device_id=command_data.get("device_id", ""),
            parameters=command_data.get("parameters", {}),
            requires_confirmation=command_data.get("requires_confirmation", False),
        )

        # Check if confirmation is required
        if command.requires_confirmation:
            self._pending_confirmations[command.id] = command
            return {
                "status": "pending_confirmation",
                "command_id": str(command.id),
                "message": "Command requires confirmation before execution",
            }

        # Execute command
        if self.dry_run_mode:
            return {
                "status": "dry_run",
                "command": command.to_dict(),
                "message": "Command validated but not executed (dry run mode)",
            }

        result = await self._mcp_handler.send_command(command)
        command.success = result.success
        command.result = result.message
        command.executed_at = datetime.utcnow()
        self._command_history.append(command)

        return {
            "status": "executed",
            "success": result.success,
            "message": result.message,
            "command": command.to_dict(),
            "state_before": result.device_state_before,
            "state_after": result.device_state_after,
            "execution_time_ms": result.execution_time_ms,
        }

    async def _adjust_load(self, task: Task) -> dict[str, Any]:
        """Adjust grid load across multiple devices."""
        target_reduction_kw = task.context.get("reduction_kw", 0)
        zone = task.context.get("zone", None)

        if not isinstance(self._mcp_handler, SimulatedMCPHandler):
            return {"error": "Load adjustment requires simulated handler"}

        devices = self._mcp_handler.list_devices()
        load_devices = [
            d for d in devices
            if d.device_type == DeviceType.LOAD
            and d.state == DeviceState.ONLINE
            and (zone is None or d.location == zone)
        ]

        if not load_devices:
            return {"error": "No available load devices found"}

        adjustments = []
        remaining_reduction = target_reduction_kw

        for device in load_devices:
            if remaining_reduction <= 0:
                break

            # Calculate safe reduction for this device
            max_reduction = device.current_output_kw * (self.max_load_adjustment_percent / 100)
            actual_reduction = min(remaining_reduction, max_reduction)

            new_power = device.current_output_kw - actual_reduction

            command = GridCommand(
                command_type=CommandType.SET_POWER,
                device_id=device.id,
                parameters={"power_kw": new_power},
            )

            if not self.dry_run_mode:
                result = await self._mcp_handler.send_command(command)
                adjustments.append({
                    "device_id": device.id,
                    "reduction_kw": actual_reduction,
                    "success": result.success,
                })
            else:
                adjustments.append({
                    "device_id": device.id,
                    "reduction_kw": actual_reduction,
                    "success": True,
                    "dry_run": True,
                })

            remaining_reduction -= actual_reduction

        return {
            "target_reduction_kw": target_reduction_kw,
            "achieved_reduction_kw": target_reduction_kw - remaining_reduction,
            "adjustments": adjustments,
            "remaining_kw": remaining_reduction,
        }

    async def _manage_storage(self, task: Task) -> dict[str, Any]:
        """Manage storage devices (charge/discharge)."""
        action = task.context.get("action", "status")
        device_id = task.context.get("device_id", "stor-001")
        rate_kw = task.context.get("rate_kw", 500)

        device = await self._mcp_handler.get_device_state(device_id)
        if not device:
            return {"error": f"Device not found: {device_id}"}

        if device.device_type != DeviceType.STORAGE:
            return {"error": "Device is not a storage device"}

        if action == "status":
            return {
                "device": device.to_dict(),
                "charge_level": device.metadata.get("charge_level", 0),
            }

        command_type = CommandType.CHARGE if action == "charge" else CommandType.DISCHARGE
        command = GridCommand(
            command_type=command_type,
            device_id=device_id,
            parameters={"rate_kw": rate_kw},
        )

        if self.dry_run_mode:
            return {
                "status": "dry_run",
                "action": action,
                "device_id": device_id,
                "rate_kw": rate_kw,
            }

        result = await self._mcp_handler.send_command(command)
        return {
            "success": result.success,
            "action": action,
            "device_id": device_id,
            "rate_kw": rate_kw,
            "message": result.message,
        }

    async def _get_grid_status(self, task: Task) -> dict[str, Any]:
        """Get current grid status."""
        if not isinstance(self._mcp_handler, SimulatedMCPHandler):
            return {"error": "Status requires simulated handler"}

        devices = self._mcp_handler.list_devices()

        total_generation = sum(
            d.current_output_kw for d in devices
            if d.device_type == DeviceType.GENERATOR and d.state == DeviceState.ONLINE
        )

        total_load = sum(
            d.current_output_kw for d in devices
            if d.device_type == DeviceType.LOAD and d.state == DeviceState.ONLINE
        )

        storage_devices = [d for d in devices if d.device_type == DeviceType.STORAGE]
        storage_status = [
            {
                "id": d.id,
                "charge_level": d.metadata.get("charge_level", 0),
                "output_kw": d.current_output_kw,
            }
            for d in storage_devices
        ]

        return {
            "total_generation_kw": total_generation,
            "total_load_kw": total_load,
            "net_balance_kw": total_generation - total_load,
            "storage": storage_status,
            "device_count": len(devices),
            "devices": [d.to_dict() for d in devices],
        }

    async def _handle_emergency(self, task: Task) -> dict[str, Any]:
        """Handle emergency grid situations."""
        emergency_type = task.context.get("emergency_type", "load_shed")

        if emergency_type == "load_shed":
            # Emergency load shedding
            reduction_percent = task.context.get("reduction_percent", 30)
            # Override normal limits for emergency
            original_limit = self.max_load_adjustment_percent
            self.max_load_adjustment_percent = reduction_percent

            result = await self._adjust_load(
                Task(context={
                    "reduction_kw": float("inf"),  # Reduce as much as possible
                })
            )

            self.max_load_adjustment_percent = original_limit
            return {
                "emergency_type": emergency_type,
                "result": result,
            }

        elif emergency_type == "storage_discharge":
            # Emergency storage discharge
            if not isinstance(self._mcp_handler, SimulatedMCPHandler):
                return {"error": "Requires simulated handler"}

            devices = self._mcp_handler.list_devices()
            storage = [d for d in devices if d.device_type == DeviceType.STORAGE]

            results = []
            for device in storage:
                command = GridCommand(
                    command_type=CommandType.DISCHARGE,
                    device_id=device.id,
                    parameters={"rate_kw": device.capacity_kw},  # Max discharge
                )
                if not self.dry_run_mode:
                    result = await self._mcp_handler.send_command(command)
                    results.append({
                        "device_id": device.id,
                        "success": result.success,
                    })

            return {
                "emergency_type": emergency_type,
                "storage_activated": results,
            }

        return {"error": f"Unknown emergency type: {emergency_type}"}

    async def confirm_command(self, command_id: UUID) -> dict[str, Any]:
        """Confirm and execute a pending command."""
        command = self._pending_confirmations.pop(command_id, None)
        if not command:
            return {"error": "Command not found or already executed"}

        result = await self._mcp_handler.send_command(command)
        command.success = result.success
        command.result = result.message
        command.executed_at = datetime.utcnow()
        self._command_history.append(command)

        return {
            "status": "executed",
            "success": result.success,
            "message": result.message,
        }

    def get_command_history(self, limit: int = 100) -> list[dict]:
        """Get recent command history."""
        return [c.to_dict() for c in self._command_history[-limit:]]
