"""
MLOps Pipeline for ÆTHER-Grid

Implements CI/CD pipelines for ML models including drift monitoring,
automated retraining, and model versioning.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


class ModelStatus(Enum):
    """Status of a model version."""

    TRAINING = "training"
    VALIDATING = "validating"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    FAILED = "failed"


class DriftType(Enum):
    """Types of model drift."""

    DATA_DRIFT = "data_drift"  # Input distribution change
    CONCEPT_DRIFT = "concept_drift"  # Relationship change
    PREDICTION_DRIFT = "prediction_drift"  # Output distribution change


class PipelineStage(Enum):
    """Stages in the ML pipeline."""

    DATA_INGESTION = "data_ingestion"
    DATA_VALIDATION = "data_validation"
    FEATURE_ENGINEERING = "feature_engineering"
    MODEL_TRAINING = "model_training"
    MODEL_EVALUATION = "model_evaluation"
    MODEL_VALIDATION = "model_validation"
    MODEL_DEPLOYMENT = "model_deployment"
    MONITORING = "monitoring"


@dataclass
class ModelVersion:
    """A version of a trained model."""

    id: UUID = field(default_factory=uuid4)
    model_name: str = ""
    version: str = "1.0.0"
    status: ModelStatus = ModelStatus.TRAINING
    created_at: datetime = field(default_factory=datetime.utcnow)
    trained_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None

    # Training info
    training_data_hash: str = ""
    training_config: dict[str, Any] = field(default_factory=dict)
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    # Performance metrics
    metrics: dict[str, float] = field(default_factory=dict)
    validation_metrics: dict[str, float] = field(default_factory=dict)

    # Artifacts
    model_path: Optional[Path] = None
    checkpoint_paths: list[Path] = field(default_factory=list)

    # Lineage
    parent_version_id: Optional[UUID] = None
    training_job_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "model_name": self.model_name,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "hyperparameters": self.hyperparameters,
        }


@dataclass
class DriftReport:
    """Report on detected model drift."""

    id: UUID = field(default_factory=uuid4)
    model_version_id: UUID = field(default_factory=uuid4)
    drift_type: DriftType = DriftType.DATA_DRIFT
    detected_at: datetime = field(default_factory=datetime.utcnow)
    severity: float = 0.0  # 0-1 scale
    affected_features: list[str] = field(default_factory=list)
    baseline_stats: dict[str, float] = field(default_factory=dict)
    current_stats: dict[str, float] = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "model_version_id": str(self.model_version_id),
            "drift_type": self.drift_type.value,
            "detected_at": self.detected_at.isoformat(),
            "severity": self.severity,
            "affected_features": self.affected_features,
            "recommendation": self.recommendation,
        }


@dataclass
class PipelineRun:
    """A run of the ML pipeline."""

    id: UUID = field(default_factory=uuid4)
    pipeline_name: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    current_stage: PipelineStage = PipelineStage.DATA_INGESTION
    status: str = "running"
    stages_completed: list[str] = field(default_factory=list)
    stage_metrics: dict[str, dict] = field(default_factory=dict)
    model_version_id: Optional[UUID] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "pipeline_name": self.pipeline_name,
            "started_at": self.started_at.isoformat(),
            "current_stage": self.current_stage.value,
            "status": self.status,
            "stages_completed": self.stages_completed,
        }


class ModelRegistry:
    """Registry for tracking model versions."""

    def __init__(self):
        self._models: dict[str, list[ModelVersion]] = {}
        self._production_models: dict[str, UUID] = {}
        self.logger = structlog.get_logger(__name__)

    def register(self, version: ModelVersion) -> None:
        """Register a new model version."""
        if version.model_name not in self._models:
            self._models[version.model_name] = []

        self._models[version.model_name].append(version)
        self.logger.info(
            "model_registered",
            model_name=version.model_name,
            version=version.version,
        )

    def promote_to_production(self, model_name: str, version_id: UUID) -> bool:
        """Promote a model version to production."""
        versions = self._models.get(model_name, [])
        version = next((v for v in versions if v.id == version_id), None)

        if not version:
            return False

        # Demote current production model
        if model_name in self._production_models:
            current_prod_id = self._production_models[model_name]
            current_prod = next(
                (v for v in versions if v.id == current_prod_id), None
            )
            if current_prod:
                current_prod.status = ModelStatus.ARCHIVED

        # Promote new version
        version.status = ModelStatus.PRODUCTION
        version.deployed_at = datetime.utcnow()
        self._production_models[model_name] = version_id

        self.logger.info(
            "model_promoted",
            model_name=model_name,
            version=version.version,
        )
        return True

    def get_production_version(self, model_name: str) -> Optional[ModelVersion]:
        """Get the current production version of a model."""
        if model_name not in self._production_models:
            return None

        version_id = self._production_models[model_name]
        versions = self._models.get(model_name, [])
        return next((v for v in versions if v.id == version_id), None)

    def get_versions(self, model_name: str) -> list[ModelVersion]:
        """Get all versions of a model."""
        return self._models.get(model_name, [])

    def list_models(self) -> list[str]:
        """List all registered model names."""
        return list(self._models.keys())


class DriftMonitor:
    """Monitors models for drift."""

    def __init__(
        self,
        threshold: float = 0.1,
        window_size: int = 1000,
    ):
        self.threshold = threshold
        self.window_size = window_size
        self._baselines: dict[UUID, dict[str, float]] = {}
        self._current_stats: dict[UUID, dict[str, list[float]]] = {}
        self.logger = structlog.get_logger(__name__)

    def set_baseline(
        self,
        model_version_id: UUID,
        feature_stats: dict[str, float],
    ) -> None:
        """Set baseline statistics for a model."""
        self._baselines[model_version_id] = feature_stats
        self._current_stats[model_version_id] = {
            feature: [] for feature in feature_stats
        }
        self.logger.info("baseline_set", model_version_id=str(model_version_id))

    def record_observation(
        self,
        model_version_id: UUID,
        features: dict[str, float],
    ) -> None:
        """Record an observation for drift detection."""
        if model_version_id not in self._current_stats:
            return

        for feature, value in features.items():
            if feature in self._current_stats[model_version_id]:
                stats = self._current_stats[model_version_id][feature]
                stats.append(value)
                # Keep only last window_size observations
                if len(stats) > self.window_size:
                    stats.pop(0)

    def check_drift(self, model_version_id: UUID) -> Optional[DriftReport]:
        """Check for drift in a model."""
        if model_version_id not in self._baselines:
            return None

        baseline = self._baselines[model_version_id]
        current = self._current_stats.get(model_version_id, {})

        affected_features = []
        current_means = {}

        for feature, baseline_mean in baseline.items():
            if feature not in current or len(current[feature]) < 100:
                continue

            current_mean = sum(current[feature]) / len(current[feature])
            current_means[feature] = current_mean

            # Simple drift detection using relative difference
            if baseline_mean != 0:
                drift = abs(current_mean - baseline_mean) / abs(baseline_mean)
                if drift > self.threshold:
                    affected_features.append(feature)

        if not affected_features:
            return None

        severity = len(affected_features) / len(baseline)

        report = DriftReport(
            model_version_id=model_version_id,
            drift_type=DriftType.DATA_DRIFT,
            severity=severity,
            affected_features=affected_features,
            baseline_stats=baseline,
            current_stats=current_means,
            recommendation=(
                "Model retraining recommended"
                if severity > 0.3
                else "Continue monitoring"
            ),
        )

        self.logger.warning(
            "drift_detected",
            model_version_id=str(model_version_id),
            severity=severity,
            affected_features=affected_features,
        )

        return report


class MLPipeline:
    """
    Main ML pipeline for model training and deployment.

    Implements a full MLOps workflow including:
    - Data validation
    - Feature engineering
    - Model training
    - Evaluation and validation
    - Automated deployment
    - Drift monitoring
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        drift_monitor: Optional[DriftMonitor] = None,
    ):
        self.registry = registry or ModelRegistry()
        self.drift_monitor = drift_monitor or DriftMonitor()
        self._stage_handlers: dict[PipelineStage, Callable] = {}
        self._runs: dict[UUID, PipelineRun] = {}
        self.logger = structlog.get_logger(__name__)

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default stage handlers."""
        self._stage_handlers = {
            PipelineStage.DATA_INGESTION: self._handle_data_ingestion,
            PipelineStage.DATA_VALIDATION: self._handle_data_validation,
            PipelineStage.FEATURE_ENGINEERING: self._handle_feature_engineering,
            PipelineStage.MODEL_TRAINING: self._handle_model_training,
            PipelineStage.MODEL_EVALUATION: self._handle_model_evaluation,
            PipelineStage.MODEL_VALIDATION: self._handle_model_validation,
            PipelineStage.MODEL_DEPLOYMENT: self._handle_model_deployment,
        }

    async def run_pipeline(
        self,
        model_name: str,
        training_config: dict[str, Any],
        auto_deploy: bool = False,
    ) -> PipelineRun:
        """Run the full ML pipeline."""
        run = PipelineRun(
            pipeline_name=f"{model_name}_training",
        )
        self._runs[run.id] = run

        # Create new model version
        version = ModelVersion(
            model_name=model_name,
            training_config=training_config,
            hyperparameters=training_config.get("hyperparameters", {}),
        )

        run.model_version_id = version.id

        try:
            for stage in PipelineStage:
                if stage == PipelineStage.MONITORING:
                    continue  # Monitoring is continuous, not a pipeline stage

                run.current_stage = stage
                self.logger.info(
                    "pipeline_stage_started",
                    run_id=str(run.id),
                    stage=stage.value,
                )

                handler = self._stage_handlers.get(stage)
                if handler:
                    metrics = await handler(version, training_config)
                    run.stage_metrics[stage.value] = metrics

                run.stages_completed.append(stage.value)

            # Register successful model
            self.registry.register(version)

            # Auto-deploy if requested and validation passed
            if auto_deploy and version.validation_metrics.get("passed", False):
                self.registry.promote_to_production(model_name, version.id)

            run.status = "completed"
            run.completed_at = datetime.utcnow()

        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            version.status = ModelStatus.FAILED
            self.logger.error("pipeline_failed", error=str(e), run_id=str(run.id))

        return run

    async def _handle_data_ingestion(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle data ingestion stage."""
        # Simulate data ingestion
        data_source = config.get("data_source", "default")
        record_count = config.get("sample_size", 10000)

        # Compute data hash for lineage
        data_hash = hashlib.sha256(
            f"{data_source}_{record_count}".encode()
        ).hexdigest()[:16]
        version.training_data_hash = data_hash

        return {
            "records_loaded": record_count,
            "data_hash": data_hash,
        }

    async def _handle_data_validation(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle data validation stage."""
        # Simulate data validation
        return {
            "schema_valid": True,
            "null_check_passed": True,
            "outlier_percentage": 0.02,
        }

    async def _handle_feature_engineering(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle feature engineering stage."""
        features = config.get("features", ["feature_1", "feature_2"])
        return {
            "features_created": len(features),
            "feature_names": features,
        }

    async def _handle_model_training(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle model training stage."""
        version.status = ModelStatus.TRAINING
        version.trained_at = datetime.utcnow()

        # Simulate training metrics
        epochs = config.get("epochs", 10)
        version.metrics = {
            "train_loss": 0.15,
            "train_accuracy": 0.92,
            "epochs_completed": epochs,
        }

        return version.metrics

    async def _handle_model_evaluation(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle model evaluation stage."""
        # Simulate evaluation
        version.metrics.update({
            "test_loss": 0.18,
            "test_accuracy": 0.89,
            "test_f1": 0.87,
        })

        return {
            "test_loss": version.metrics["test_loss"],
            "test_accuracy": version.metrics["test_accuracy"],
        }

    async def _handle_model_validation(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle model validation stage."""
        version.status = ModelStatus.VALIDATING

        # Simulate validation checks
        min_accuracy = config.get("min_accuracy", 0.8)
        passed = version.metrics.get("test_accuracy", 0) >= min_accuracy

        version.validation_metrics = {
            "passed": passed,
            "min_accuracy_met": passed,
            "latency_check": True,
            "memory_check": True,
        }

        if passed:
            version.status = ModelStatus.STAGING

        return version.validation_metrics

    async def _handle_model_deployment(
        self,
        version: ModelVersion,
        config: dict,
    ) -> dict[str, Any]:
        """Handle model deployment stage."""
        # Simulate deployment
        return {
            "deployed": True,
            "endpoint": f"/models/{version.model_name}/v{version.version}",
        }

    def get_run(self, run_id: UUID) -> Optional[PipelineRun]:
        """Get a pipeline run by ID."""
        return self._runs.get(run_id)

    def list_runs(self) -> list[PipelineRun]:
        """List all pipeline runs."""
        return list(self._runs.values())

    async def trigger_retraining(
        self,
        model_name: str,
        reason: str = "scheduled",
    ) -> Optional[PipelineRun]:
        """Trigger model retraining."""
        # Get current production model config
        prod_version = self.registry.get_production_version(model_name)
        if not prod_version:
            self.logger.warning("no_production_model", model_name=model_name)
            return None

        # Create new training config based on previous
        config = {
            **prod_version.training_config,
            "retrain_reason": reason,
            "parent_version": str(prod_version.id),
        }

        self.logger.info(
            "retraining_triggered",
            model_name=model_name,
            reason=reason,
        )

        return await self.run_pipeline(model_name, config, auto_deploy=True)
