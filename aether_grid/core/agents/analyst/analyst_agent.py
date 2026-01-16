"""
Analyst Agent for ÆTHER-Grid

Performs real-time telemetry processing using semantic telemetry
(logs enriched with natural language context for self-diagnosis).
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import numpy as np
import structlog

from aether_grid.core.base import (
    Action,
    ActionType,
    BaseAgent,
    Result,
    RiskLevel,
    Task,
)


class TelemetryType(Enum):
    """Types of telemetry data."""

    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER = "power"
    FREQUENCY = "frequency"
    TEMPERATURE = "temperature"
    LOAD = "load"
    RENEWABLE_OUTPUT = "renewable_output"
    DEMAND = "demand"
    STORAGE_LEVEL = "storage_level"


class AnomalyType(Enum):
    """Types of detected anomalies."""

    THRESHOLD_BREACH = "threshold_breach"
    SUDDEN_CHANGE = "sudden_change"
    PATTERN_DEVIATION = "pattern_deviation"
    CORRELATION_BREAK = "correlation_break"
    PREDICTION_ERROR = "prediction_error"


@dataclass
class TelemetryPoint:
    """Single telemetry data point with semantic enrichment."""

    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    telemetry_type: TelemetryType = TelemetryType.POWER
    value: float = 0.0
    unit: str = ""
    source_node: str = ""
    quality_score: float = 1.0  # Data quality indicator

    # Semantic enrichment
    semantic_context: str = ""  # Natural language description
    tags: list[str] = field(default_factory=list)
    related_events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "type": self.telemetry_type.value,
            "value": self.value,
            "unit": self.unit,
            "source": self.source_node,
            "quality": self.quality_score,
            "context": self.semantic_context,
            "tags": self.tags,
        }


@dataclass
class Anomaly:
    """Detected anomaly with context."""

    id: UUID = field(default_factory=uuid4)
    anomaly_type: AnomalyType = AnomalyType.THRESHOLD_BREACH
    severity: float = 0.0  # 0.0 to 1.0
    detected_at: datetime = field(default_factory=datetime.utcnow)
    telemetry_points: list[TelemetryPoint] = field(default_factory=list)
    description: str = ""
    suggested_action: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "type": self.anomaly_type.value,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "description": self.description,
            "suggested_action": self.suggested_action,
            "confidence": self.confidence,
        }


@dataclass
class AnalysisResult:
    """Result of telemetry analysis."""

    summary: str = ""
    anomalies: list[Anomaly] = field(default_factory=list)
    patterns_detected: list[str] = field(default_factory=list)
    predictions: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    confidence_score: float = 0.0


class TelemetryBuffer:
    """Rolling buffer for telemetry data with efficient access patterns."""

    def __init__(self, max_size: int = 10000, retention_minutes: int = 60):
        self.max_size = max_size
        self.retention_minutes = retention_minutes
        self._data: dict[TelemetryType, deque] = {
            t: deque(maxlen=max_size) for t in TelemetryType
        }
        self._node_data: dict[str, deque] = {}

    def add(self, point: TelemetryPoint) -> None:
        """Add a telemetry point to the buffer."""
        self._data[point.telemetry_type].append(point)

        if point.source_node not in self._node_data:
            self._node_data[point.source_node] = deque(maxlen=self.max_size)
        self._node_data[point.source_node].append(point)

    def get_recent(
        self,
        telemetry_type: TelemetryType,
        minutes: int = 5,
    ) -> list[TelemetryPoint]:
        """Get recent telemetry of a specific type."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [
            p for p in self._data[telemetry_type]
            if p.timestamp > cutoff
        ]

    def get_by_node(self, node_id: str, minutes: int = 5) -> list[TelemetryPoint]:
        """Get recent telemetry from a specific node."""
        if node_id not in self._node_data:
            return []
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [p for p in self._node_data[node_id] if p.timestamp > cutoff]

    def get_statistics(self, telemetry_type: TelemetryType) -> dict[str, float]:
        """Calculate statistics for a telemetry type."""
        points = self.get_recent(telemetry_type, minutes=60)
        if not points:
            return {}

        values = [p.value for p in points]
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "count": len(values),
        }

    def cleanup_old_data(self) -> int:
        """Remove data older than retention period."""
        cutoff = datetime.utcnow() - timedelta(minutes=self.retention_minutes)
        removed = 0

        for telemetry_type in TelemetryType:
            original_len = len(self._data[telemetry_type])
            self._data[telemetry_type] = deque(
                (p for p in self._data[telemetry_type] if p.timestamp > cutoff),
                maxlen=self.max_size,
            )
            removed += original_len - len(self._data[telemetry_type])

        return removed


class AnalystAgent(BaseAgent):
    """
    Analyst Agent for real-time telemetry processing.

    Capabilities:
    - Real-time telemetry ingestion and buffering
    - Semantic enrichment of raw data
    - Anomaly detection using statistical methods
    - Pattern recognition and trend analysis
    - Predictive analytics for load forecasting
    """

    def __init__(
        self,
        agent_id: str = "analyst-001",
        buffer_size: int = 10000,
        anomaly_threshold: float = 0.95,
    ):
        super().__init__(
            agent_id=agent_id,
            name="Analyst Agent",
            description="Real-time telemetry processing with semantic enrichment",
        )
        self.buffer = TelemetryBuffer(max_size=buffer_size)
        self.anomaly_threshold = anomaly_threshold

        # Thresholds for different telemetry types
        self._thresholds: dict[TelemetryType, dict[str, float]] = {
            TelemetryType.VOLTAGE: {"min": 0.95, "max": 1.05},  # Per-unit
            TelemetryType.FREQUENCY: {"min": 59.5, "max": 60.5},  # Hz
            TelemetryType.LOAD: {"min": 0.0, "max": 1.0},  # Fraction
            TelemetryType.TEMPERATURE: {"min": -20, "max": 80},  # Celsius
        }

        # Historical baselines for pattern detection
        self._baselines: dict[str, dict[str, float]] = {}

    def get_capabilities(self) -> list[str]:
        """Return agent capabilities."""
        return [
            "telemetry_processing",
            "semantic_enrichment",
            "anomaly_detection",
            "pattern_recognition",
            "load_forecasting",
            "trend_analysis",
        ]

    async def process(self, task: Task) -> Result:
        """Process an analysis task."""
        start_time = datetime.utcnow()
        self._record_task(task.id)

        try:
            task_type = task.context.get("task_type", "analyze")

            if task_type == "ingest":
                result_data = await self._process_ingestion(task)
            elif task_type == "analyze":
                result_data = await self._process_analysis(task)
            elif task_type == "detect_anomalies":
                result_data = await self._detect_anomalies(task)
            elif task_type == "forecast":
                result_data = await self._forecast_load(task)
            else:
                result_data = await self._process_analysis(task)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return Result(
                task_id=task.id,
                success=True,
                data=result_data,
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
                reasoning_trace=[
                    f"Task type: {task_type}",
                    f"Processed at: {start_time.isoformat()}",
                    f"Buffer size: {sum(len(d) for d in self.buffer._data.values())}",
                ],
            )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error("analysis_failed", error=str(e), task_id=str(task.id))
            return Result(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
            )

    async def validate(self, action: Action) -> bool:
        """Validate an action before execution."""
        # Analyst agent only performs read operations
        if action.action_type not in [ActionType.QUERY, ActionType.ANALYZE, ActionType.PREDICT]:
            self.logger.warning(
                "invalid_action_type",
                action_type=action.action_type.value,
            )
            return False
        return True

    async def ingest_telemetry(self, points: list[TelemetryPoint]) -> int:
        """Ingest multiple telemetry points."""
        for point in points:
            # Add semantic enrichment
            point.semantic_context = self._generate_semantic_context(point)
            self.buffer.add(point)

        self.logger.debug("telemetry_ingested", count=len(points))
        return len(points)

    def _generate_semantic_context(self, point: TelemetryPoint) -> str:
        """Generate natural language context for a telemetry point."""
        stats = self.buffer.get_statistics(point.telemetry_type)

        if not stats:
            return f"{point.telemetry_type.value} reading of {point.value:.2f} {point.unit}"

        mean = stats.get("mean", point.value)
        std = stats.get("std", 0)

        if std > 0:
            z_score = (point.value - mean) / std
            if abs(z_score) > 2:
                deviation = "significantly above" if z_score > 0 else "significantly below"
                return (
                    f"{point.telemetry_type.value} reading of {point.value:.2f} {point.unit} "
                    f"is {deviation} normal (z-score: {z_score:.2f})"
                )

        return (
            f"{point.telemetry_type.value} reading of {point.value:.2f} {point.unit} "
            f"within normal range (mean: {mean:.2f})"
        )

    async def _process_ingestion(self, task: Task) -> dict[str, Any]:
        """Process telemetry ingestion task."""
        raw_data = task.context.get("telemetry_data", [])
        points = []

        for item in raw_data:
            point = TelemetryPoint(
                telemetry_type=TelemetryType(item.get("type", "power")),
                value=item.get("value", 0.0),
                unit=item.get("unit", ""),
                source_node=item.get("source", "unknown"),
            )
            points.append(point)

        ingested = await self.ingest_telemetry(points)
        return {"ingested_count": ingested}

    async def _process_analysis(self, task: Task) -> dict[str, Any]:
        """Process general analysis task."""
        analysis = AnalysisResult()

        # Gather statistics for all telemetry types
        type_stats = {}
        for t_type in TelemetryType:
            stats = self.buffer.get_statistics(t_type)
            if stats:
                type_stats[t_type.value] = stats

        # Detect any anomalies
        anomalies = await self._run_anomaly_detection()
        analysis.anomalies = anomalies

        # Generate patterns
        patterns = self._detect_patterns()
        analysis.patterns_detected = patterns

        # Generate recommendations
        analysis.recommendations = self._generate_recommendations(anomalies, patterns)

        # Overall summary
        anomaly_count = len(anomalies)
        if anomaly_count == 0:
            analysis.summary = "Grid operating within normal parameters"
        elif anomaly_count < 3:
            analysis.summary = f"Minor deviations detected: {anomaly_count} anomalies"
        else:
            analysis.summary = f"Attention required: {anomaly_count} anomalies detected"

        analysis.confidence_score = 0.85  # Would be calculated from model confidence

        return {
            "summary": analysis.summary,
            "statistics": type_stats,
            "anomalies": [a.to_dict() for a in analysis.anomalies],
            "patterns": analysis.patterns_detected,
            "recommendations": analysis.recommendations,
            "confidence": analysis.confidence_score,
        }

    async def _detect_anomalies(self, task: Task) -> dict[str, Any]:
        """Dedicated anomaly detection task."""
        anomalies = await self._run_anomaly_detection()
        return {
            "anomaly_count": len(anomalies),
            "anomalies": [a.to_dict() for a in anomalies],
            "detection_time": datetime.utcnow().isoformat(),
        }

    async def _run_anomaly_detection(self) -> list[Anomaly]:
        """Run comprehensive anomaly detection."""
        anomalies = []

        for t_type, thresholds in self._thresholds.items():
            recent = self.buffer.get_recent(t_type, minutes=5)

            for point in recent:
                # Threshold check
                if point.value < thresholds.get("min", float("-inf")):
                    anomaly = Anomaly(
                        anomaly_type=AnomalyType.THRESHOLD_BREACH,
                        severity=0.8,
                        telemetry_points=[point],
                        description=f"{t_type.value} below minimum threshold",
                        suggested_action=f"Investigate low {t_type.value} at {point.source_node}",
                        confidence=0.95,
                    )
                    anomalies.append(anomaly)

                elif point.value > thresholds.get("max", float("inf")):
                    anomaly = Anomaly(
                        anomaly_type=AnomalyType.THRESHOLD_BREACH,
                        severity=0.8,
                        telemetry_points=[point],
                        description=f"{t_type.value} above maximum threshold",
                        suggested_action=f"Investigate high {t_type.value} at {point.source_node}",
                        confidence=0.95,
                    )
                    anomalies.append(anomaly)

        # Statistical anomaly detection
        for t_type in TelemetryType:
            stats = self.buffer.get_statistics(t_type)
            if not stats or stats.get("std", 0) == 0:
                continue

            recent = self.buffer.get_recent(t_type, minutes=5)
            mean, std = stats["mean"], stats["std"]

            for point in recent:
                z_score = abs((point.value - mean) / std)
                if z_score > 3:
                    anomaly = Anomaly(
                        anomaly_type=AnomalyType.PATTERN_DEVIATION,
                        severity=min(z_score / 5, 1.0),
                        telemetry_points=[point],
                        description=f"Statistical outlier in {t_type.value} (z={z_score:.2f})",
                        suggested_action="Review recent operational changes",
                        confidence=0.9,
                    )
                    anomalies.append(anomaly)

        return anomalies

    def _detect_patterns(self) -> list[str]:
        """Detect patterns in telemetry data."""
        patterns = []

        # Check for trending
        for t_type in [TelemetryType.LOAD, TelemetryType.DEMAND]:
            recent = self.buffer.get_recent(t_type, minutes=30)
            if len(recent) >= 10:
                values = [p.value for p in sorted(recent, key=lambda x: x.timestamp)]

                # Simple trend detection
                first_half = np.mean(values[: len(values) // 2])
                second_half = np.mean(values[len(values) // 2:])

                if second_half > first_half * 1.1:
                    patterns.append(f"Rising trend in {t_type.value}")
                elif second_half < first_half * 0.9:
                    patterns.append(f"Declining trend in {t_type.value}")

        return patterns

    def _generate_recommendations(
        self,
        anomalies: list[Anomaly],
        patterns: list[str],
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Based on anomalies
        severe_anomalies = [a for a in anomalies if a.severity > 0.7]
        if severe_anomalies:
            recommendations.append("Immediate attention required for severe anomalies")

        # Based on patterns
        for pattern in patterns:
            if "Rising" in pattern and "load" in pattern.lower():
                recommendations.append("Consider activating additional generation capacity")
            elif "Declining" in pattern and "demand" in pattern.lower():
                recommendations.append("Opportunity to increase storage charging")

        if not recommendations:
            recommendations.append("Continue normal operations")

        return recommendations

    async def _forecast_load(self, task: Task) -> dict[str, Any]:
        """Forecast future load based on historical patterns."""
        horizon_minutes = task.context.get("horizon_minutes", 60)

        # Get historical load data
        historical = self.buffer.get_recent(TelemetryType.LOAD, minutes=120)

        if len(historical) < 10:
            return {
                "error": "Insufficient historical data for forecasting",
                "minimum_required": 10,
                "available": len(historical),
            }

        values = [p.value for p in sorted(historical, key=lambda x: x.timestamp)]

        # Simple moving average forecast
        window = min(len(values), 10)
        forecast = float(np.mean(values[-window:]))

        # Trend adjustment
        if len(values) >= 20:
            recent_trend = np.mean(values[-10:]) - np.mean(values[-20:-10])
            steps = horizon_minutes / 5  # Assuming 5-min intervals
            forecast += recent_trend * steps

        return {
            "forecast_value": forecast,
            "horizon_minutes": horizon_minutes,
            "confidence": 0.7,
            "method": "moving_average_with_trend",
            "data_points_used": len(values),
        }
