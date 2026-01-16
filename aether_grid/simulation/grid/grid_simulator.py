"""
Grid Simulator for ÆTHER-Grid

A simulated power grid environment for testing multi-agent
coordination and optimization algorithms.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class NodeType(Enum):
    """Types of nodes in the grid."""

    BUS = "bus"  # Electrical bus
    GENERATOR = "generator"  # Power generator
    LOAD = "load"  # Power consumer
    STORAGE = "storage"  # Energy storage
    RENEWABLE = "renewable"  # Renewable source (solar, wind)
    SUBSTATION = "substation"  # Transformer substation


class LineType(Enum):
    """Types of transmission lines."""

    TRANSMISSION = "transmission"  # High voltage
    DISTRIBUTION = "distribution"  # Medium voltage
    FEEDER = "feeder"  # Low voltage


@dataclass
class GridNode:
    """A node in the simulated grid."""

    id: str = ""
    name: str = ""
    node_type: NodeType = NodeType.BUS
    voltage_kv: float = 0.0
    location: tuple[float, float] = (0.0, 0.0)  # x, y coordinates

    # Power characteristics
    active_power_mw: float = 0.0  # P - positive = generation, negative = load
    reactive_power_mvar: float = 0.0  # Q
    max_power_mw: float = 0.0
    min_power_mw: float = 0.0

    # For renewables
    capacity_factor: float = 1.0

    # For storage
    energy_capacity_mwh: float = 0.0
    current_energy_mwh: float = 0.0
    charge_efficiency: float = 0.9
    discharge_efficiency: float = 0.9

    # State
    is_online: bool = True
    fault: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type.value,
            "voltage_kv": self.voltage_kv,
            "active_power_mw": self.active_power_mw,
            "reactive_power_mvar": self.reactive_power_mvar,
            "is_online": self.is_online,
            "fault": self.fault,
        }


@dataclass
class TransmissionLine:
    """A transmission line connecting two nodes."""

    id: str = ""
    from_node: str = ""
    to_node: str = ""
    line_type: LineType = LineType.DISTRIBUTION
    length_km: float = 0.0
    resistance_ohm: float = 0.0
    reactance_ohm: float = 0.0
    max_power_mw: float = 100.0
    current_power_mw: float = 0.0
    is_closed: bool = True  # Breaker status

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "from": self.from_node,
            "to": self.to_node,
            "type": self.line_type.value,
            "power_mw": self.current_power_mw,
            "max_mw": self.max_power_mw,
            "closed": self.is_closed,
        }


@dataclass
class GridState:
    """Complete state of the grid at a point in time."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    total_generation_mw: float = 0.0
    total_load_mw: float = 0.0
    total_renewable_mw: float = 0.0
    total_storage_mw: float = 0.0
    frequency_hz: float = 60.0
    is_stable: bool = True
    nodes: dict[str, dict] = field(default_factory=dict)
    lines: dict[str, dict] = field(default_factory=dict)
    alarms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_generation_mw": self.total_generation_mw,
            "total_load_mw": self.total_load_mw,
            "total_renewable_mw": self.total_renewable_mw,
            "frequency_hz": self.frequency_hz,
            "is_stable": self.is_stable,
            "alarm_count": len(self.alarms),
        }


class WeatherModel:
    """Simulates weather conditions affecting renewables."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self._hour_of_day = 12
        self._cloud_cover = 0.2
        self._wind_speed = 5.0  # m/s

    def step(self, hours: float = 1.0) -> None:
        """Advance weather simulation."""
        self._hour_of_day = (self._hour_of_day + hours) % 24

        # Cloud cover varies slowly
        self._cloud_cover = max(0, min(1, self._cloud_cover + self.rng.normal(0, 0.05)))

        # Wind speed varies
        self._wind_speed = max(0, self._wind_speed + self.rng.normal(0, 0.5))

    def get_solar_factor(self) -> float:
        """Get solar output factor (0-1)."""
        # Simple solar curve based on hour of day
        if self._hour_of_day < 6 or self._hour_of_day > 18:
            base = 0.0
        else:
            # Peak at noon
            base = np.sin((self._hour_of_day - 6) / 12 * np.pi)

        # Reduce by cloud cover
        return base * (1 - self._cloud_cover * 0.8)

    def get_wind_factor(self) -> float:
        """Get wind output factor (0-1)."""
        # Typical wind turbine curve
        cut_in = 3.0  # m/s
        rated = 12.0  # m/s
        cut_out = 25.0  # m/s

        if self._wind_speed < cut_in or self._wind_speed > cut_out:
            return 0.0
        elif self._wind_speed < rated:
            return (self._wind_speed - cut_in) / (rated - cut_in)
        else:
            return 1.0


class LoadModel:
    """Simulates load patterns."""

    def __init__(self, base_load_mw: float = 100.0, seed: int = 42):
        self.base_load = base_load_mw
        self.rng = np.random.default_rng(seed)
        self._hour_of_day = 12

    def step(self, hours: float = 1.0) -> None:
        """Advance load simulation."""
        self._hour_of_day = (self._hour_of_day + hours) % 24

    def get_load_factor(self) -> float:
        """Get load factor (0-1) based on time of day."""
        # Typical daily load curve
        hour = self._hour_of_day

        if 0 <= hour < 6:
            # Night - low load
            base = 0.5
        elif 6 <= hour < 9:
            # Morning ramp
            base = 0.5 + (hour - 6) / 3 * 0.4
        elif 9 <= hour < 17:
            # Daytime - high load
            base = 0.9
        elif 17 <= hour < 21:
            # Evening peak
            base = 1.0
        else:
            # Evening decline
            base = 1.0 - (hour - 21) / 3 * 0.5

        # Add some randomness
        noise = self.rng.normal(0, 0.05)
        return max(0.3, min(1.2, base + noise))


class GridSimulator:
    """
    Main grid simulation environment.

    Provides a realistic testbed for multi-agent grid management.
    """

    def __init__(
        self,
        time_step_seconds: int = 60,
        seed: int = 42,
    ):
        self.time_step_seconds = time_step_seconds
        self.current_time = datetime.utcnow()

        self._nodes: dict[str, GridNode] = {}
        self._lines: dict[str, TransmissionLine] = {}
        self._weather = WeatherModel(seed)
        self._load_model = LoadModel(seed=seed)

        self._running = False
        self._step_callbacks: list[Callable[[GridState], None]] = []

        self.logger = structlog.get_logger(__name__)

        # Initialize default grid
        self._initialize_default_grid()

    def _initialize_default_grid(self) -> None:
        """Create a default test grid."""
        # Main substation
        self._nodes["sub-1"] = GridNode(
            id="sub-1",
            name="Main Substation",
            node_type=NodeType.SUBSTATION,
            voltage_kv=230,
            location=(0, 0),
            max_power_mw=500,
        )

        # Conventional generator
        self._nodes["gen-1"] = GridNode(
            id="gen-1",
            name="Gas Turbine 1",
            node_type=NodeType.GENERATOR,
            voltage_kv=20,
            location=(10, 0),
            active_power_mw=100,
            max_power_mw=200,
            min_power_mw=50,
        )

        # Solar farm
        self._nodes["solar-1"] = GridNode(
            id="solar-1",
            name="Solar Farm A",
            node_type=NodeType.RENEWABLE,
            voltage_kv=33,
            location=(-10, 10),
            active_power_mw=50,
            max_power_mw=80,
            capacity_factor=0.25,
        )

        # Wind farm
        self._nodes["wind-1"] = GridNode(
            id="wind-1",
            name="Wind Farm B",
            node_type=NodeType.RENEWABLE,
            voltage_kv=33,
            location=(10, 10),
            active_power_mw=40,
            max_power_mw=100,
            capacity_factor=0.35,
        )

        # Battery storage
        self._nodes["battery-1"] = GridNode(
            id="battery-1",
            name="Grid Battery 1",
            node_type=NodeType.STORAGE,
            voltage_kv=20,
            location=(0, 5),
            max_power_mw=50,
            min_power_mw=-50,
            energy_capacity_mwh=200,
            current_energy_mwh=100,
        )

        # Loads
        for i in range(3):
            self._nodes[f"load-{i+1}"] = GridNode(
                id=f"load-{i+1}",
                name=f"Load Zone {i+1}",
                node_type=NodeType.LOAD,
                voltage_kv=11,
                location=(-5 + i*5, -10),
                active_power_mw=-50 - i*20,  # Negative for load
                max_power_mw=100,
            )

        # Transmission lines
        self._lines["line-1"] = TransmissionLine(
            id="line-1",
            from_node="sub-1",
            to_node="gen-1",
            line_type=LineType.TRANSMISSION,
            length_km=10,
            max_power_mw=250,
        )

        self._lines["line-2"] = TransmissionLine(
            id="line-2",
            from_node="sub-1",
            to_node="solar-1",
            line_type=LineType.DISTRIBUTION,
            length_km=15,
            max_power_mw=100,
        )

        self._lines["line-3"] = TransmissionLine(
            id="line-3",
            from_node="sub-1",
            to_node="wind-1",
            line_type=LineType.DISTRIBUTION,
            length_km=12,
            max_power_mw=120,
        )

    def add_node(self, node: GridNode) -> None:
        """Add a node to the grid."""
        self._nodes[node.id] = node
        self.logger.debug("node_added", node_id=node.id)

    def add_line(self, line: TransmissionLine) -> None:
        """Add a transmission line to the grid."""
        self._lines[line.id] = line
        self.logger.debug("line_added", line_id=line.id)

    def get_node(self, node_id: str) -> Optional[GridNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_line(self, line_id: str) -> Optional[TransmissionLine]:
        """Get a line by ID."""
        return self._lines.get(line_id)

    async def step(self) -> GridState:
        """Advance simulation by one time step."""
        # Advance time
        self.current_time += timedelta(seconds=self.time_step_seconds)
        hours = self.time_step_seconds / 3600

        # Update weather
        self._weather.step(hours)

        # Update load model
        self._load_model.step(hours)

        # Update renewable output
        solar_factor = self._weather.get_solar_factor()
        wind_factor = self._weather.get_wind_factor()

        for node in self._nodes.values():
            if node.node_type == NodeType.RENEWABLE:
                if "solar" in node.id.lower():
                    node.active_power_mw = node.max_power_mw * solar_factor
                elif "wind" in node.id.lower():
                    node.active_power_mw = node.max_power_mw * wind_factor

        # Update loads
        load_factor = self._load_model.get_load_factor()
        for node in self._nodes.values():
            if node.node_type == NodeType.LOAD:
                base_load = abs(node.max_power_mw) * 0.6
                node.active_power_mw = -base_load * load_factor

        # Calculate state
        state = self._calculate_state()

        # Notify callbacks
        for callback in self._step_callbacks:
            try:
                callback(state)
            except Exception as e:
                self.logger.error("callback_error", error=str(e))

        return state

    def _calculate_state(self) -> GridState:
        """Calculate current grid state."""
        state = GridState(timestamp=self.current_time)

        alarms = []

        # Sum up generation and load
        for node in self._nodes.values():
            if not node.is_online:
                continue

            state.nodes[node.id] = node.to_dict()

            if node.node_type == NodeType.GENERATOR:
                state.total_generation_mw += node.active_power_mw
            elif node.node_type == NodeType.RENEWABLE:
                state.total_renewable_mw += node.active_power_mw
                state.total_generation_mw += node.active_power_mw
            elif node.node_type == NodeType.LOAD:
                state.total_load_mw += abs(node.active_power_mw)
            elif node.node_type == NodeType.STORAGE:
                state.total_storage_mw += node.active_power_mw

            if node.fault:
                alarms.append(f"Fault at {node.name}")

        # Calculate frequency deviation
        power_imbalance = (
            state.total_generation_mw + state.total_storage_mw - state.total_load_mw
        )
        # Simplified frequency model: 0.1 Hz per 10 MW imbalance
        state.frequency_hz = 60.0 + power_imbalance * 0.01

        # Check stability
        if abs(state.frequency_hz - 60.0) > 0.5:
            state.is_stable = False
            alarms.append(f"Frequency deviation: {state.frequency_hz:.2f} Hz")

        # Check lines
        for line in self._lines.values():
            state.lines[line.id] = line.to_dict()
            if abs(line.current_power_mw) > line.max_power_mw * 0.9:
                alarms.append(f"Line {line.id} overloaded")

        state.alarms = alarms
        return state

    async def run(self, duration_seconds: int = 3600) -> list[GridState]:
        """Run simulation for specified duration."""
        states = []
        steps = duration_seconds // self.time_step_seconds

        self._running = True
        for _ in range(steps):
            if not self._running:
                break
            state = await self.step()
            states.append(state)
            await asyncio.sleep(0.001)  # Yield to other tasks

        return states

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False

    def register_callback(self, callback: Callable[[GridState], None]) -> None:
        """Register a callback for state updates."""
        self._step_callbacks.append(callback)

    def set_node_power(self, node_id: str, power_mw: float) -> bool:
        """Set the power output/consumption of a node."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        # Validate bounds
        if node.max_power_mw and power_mw > node.max_power_mw:
            return False
        if node.min_power_mw and power_mw < node.min_power_mw:
            return False

        node.active_power_mw = power_mw
        return True

    def set_storage_mode(
        self,
        node_id: str,
        power_mw: float,
    ) -> bool:
        """Set storage charge/discharge rate."""
        node = self._nodes.get(node_id)
        if not node or node.node_type != NodeType.STORAGE:
            return False

        # Validate bounds
        if abs(power_mw) > node.max_power_mw:
            return False

        node.active_power_mw = power_mw
        return True

    def trigger_fault(self, node_id: str) -> bool:
        """Trigger a fault at a node."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        node.fault = True
        node.is_online = False
        self.logger.warning("fault_triggered", node_id=node_id)
        return True

    def clear_fault(self, node_id: str) -> bool:
        """Clear a fault at a node."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        node.fault = False
        node.is_online = True
        self.logger.info("fault_cleared", node_id=node_id)
        return True

    def get_status(self) -> dict[str, Any]:
        """Get current simulation status."""
        state = self._calculate_state()
        return {
            "current_time": self.current_time.isoformat(),
            "node_count": len(self._nodes),
            "line_count": len(self._lines),
            "is_running": self._running,
            "state_summary": state.to_dict(),
        }
