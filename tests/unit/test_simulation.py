"""Tests for grid simulation."""

import pytest
from datetime import datetime

from aether_grid.simulation.grid import (
    GridNode,
    GridSimulator,
    GridState,
    NodeType,
    TransmissionLine,
    WeatherModel,
    LoadModel,
)


class TestGridSimulator:
    """Tests for GridSimulator."""

    @pytest.fixture
    def simulator(self):
        return GridSimulator(time_step_seconds=60)

    def test_initialization(self, simulator):
        """Test simulator initialization."""
        assert simulator.time_step_seconds == 60
        assert not simulator._running
        assert len(simulator._nodes) > 0
        assert len(simulator._lines) > 0

    def test_get_node(self, simulator):
        """Test node retrieval."""
        node = simulator.get_node("gen-1")
        assert node is not None
        assert node.node_type == NodeType.GENERATOR

    def test_get_nonexistent_node(self, simulator):
        """Test retrieval of non-existent node."""
        node = simulator.get_node("nonexistent")
        assert node is None

    @pytest.mark.asyncio
    async def test_step(self, simulator):
        """Test simulation step."""
        initial_time = simulator.current_time
        state = await simulator.step()

        assert isinstance(state, GridState)
        assert simulator.current_time > initial_time
        assert state.total_generation_mw >= 0

    def test_set_node_power(self, simulator):
        """Test setting node power."""
        success = simulator.set_node_power("gen-1", 150.0)
        assert success

        node = simulator.get_node("gen-1")
        assert node.active_power_mw == 150.0

    def test_set_invalid_power(self, simulator):
        """Test setting invalid power level."""
        # Try to exceed capacity
        node = simulator.get_node("gen-1")
        success = simulator.set_node_power("gen-1", node.max_power_mw + 100)
        assert not success

    def test_trigger_fault(self, simulator):
        """Test fault triggering."""
        success = simulator.trigger_fault("gen-1")
        assert success

        node = simulator.get_node("gen-1")
        assert node.fault
        assert not node.is_online

    def test_clear_fault(self, simulator):
        """Test fault clearing."""
        simulator.trigger_fault("gen-1")
        success = simulator.clear_fault("gen-1")
        assert success

        node = simulator.get_node("gen-1")
        assert not node.fault
        assert node.is_online

    def test_get_status(self, simulator):
        """Test status retrieval."""
        status = simulator.get_status()
        assert "current_time" in status
        assert "node_count" in status
        assert "is_running" in status


class TestWeatherModel:
    """Tests for WeatherModel."""

    @pytest.fixture
    def weather(self):
        return WeatherModel(seed=42)

    def test_solar_factor_night(self, weather):
        """Test solar factor at night."""
        weather._hour_of_day = 2  # 2 AM
        factor = weather.get_solar_factor()
        assert factor == 0.0

    def test_solar_factor_day(self, weather):
        """Test solar factor during day."""
        weather._hour_of_day = 12  # Noon
        weather._cloud_cover = 0.0
        factor = weather.get_solar_factor()
        assert factor > 0.9

    def test_wind_factor(self, weather):
        """Test wind factor calculation."""
        weather._wind_speed = 8.0  # Good wind speed
        factor = weather.get_wind_factor()
        assert 0 < factor < 1


class TestLoadModel:
    """Tests for LoadModel."""

    @pytest.fixture
    def load_model(self):
        return LoadModel(base_load_mw=100.0, seed=42)

    def test_load_factor_night(self, load_model):
        """Test load factor at night."""
        load_model._hour_of_day = 3  # 3 AM
        factor = load_model.get_load_factor()
        assert factor < 0.7  # Should be low at night

    def test_load_factor_peak(self, load_model):
        """Test load factor at peak hours."""
        load_model._hour_of_day = 19  # 7 PM
        factor = load_model.get_load_factor()
        assert factor > 0.8  # Should be high at evening peak


class TestGridNode:
    """Tests for GridNode."""

    def test_node_creation(self):
        """Test node creation with defaults."""
        node = GridNode()
        assert node.is_online
        assert not node.fault
        assert node.node_type == NodeType.BUS

    def test_to_dict(self):
        """Test dictionary conversion."""
        node = GridNode(
            id="node-1",
            name="Test Node",
            node_type=NodeType.GENERATOR,
            active_power_mw=100.0,
        )
        data = node.to_dict()

        assert data["id"] == "node-1"
        assert data["type"] == "generator"
        assert data["active_power_mw"] == 100.0
