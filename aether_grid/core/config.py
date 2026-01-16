"""
Configuration management for ÆTHER-Grid.

Centralized configuration using Pydantic for validation
and environment variable support.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class QuantumBackend(str, Enum):
    """Available quantum computing backends."""

    SIMULATOR = "aer_simulator"
    IBMQ = "ibmq"
    IONQ = "ionq"


class VectorDBType(str, Enum):
    """Supported vector database types."""

    CHROMADB = "chromadb"
    PINECONE = "pinecone"
    FAISS = "faiss"


class OrchestratorConfig(BaseModel):
    """Configuration for the Orchestrator."""

    max_concurrent_tasks: int = Field(default=10, ge=1, le=100)
    task_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    retry_delay_seconds: int = Field(default=5, ge=1, le=60)
    enable_load_balancing: bool = True
    health_check_interval_seconds: int = Field(default=30, ge=10, le=300)


class AgentConfig(BaseModel):
    """Configuration for individual agents."""

    analyst: dict[str, Any] = Field(default_factory=lambda: {
        "telemetry_buffer_size": 10000,
        "semantic_enrichment_enabled": True,
        "anomaly_threshold": 0.95,
    })
    risk: dict[str, Any] = Field(default_factory=lambda: {
        "prompt_injection_detection": True,
        "tool_abuse_monitoring": True,
        "max_risk_score": 0.8,
    })
    execution: dict[str, Any] = Field(default_factory=lambda: {
        "dry_run_mode": False,
        "max_load_adjustment_percent": 20,
        "confirmation_required_threshold": "HIGH",
    })


class QuantumConfig(BaseModel):
    """Configuration for quantum computing integration."""

    backend: QuantumBackend = QuantumBackend.SIMULATOR
    shots: int = Field(default=1024, ge=1, le=100000)
    optimization_level: int = Field(default=3, ge=0, le=3)
    enable_error_mitigation: bool = True
    max_qubits: int = Field(default=20, ge=1, le=127)


class VectorDBConfig(BaseModel):
    """Configuration for vector database."""

    type: VectorDBType = VectorDBType.CHROMADB
    host: str = "localhost"
    port: int = 8000
    collection_name: str = "aether_memory"
    embedding_dimension: int = 768
    distance_metric: str = "cosine"


class AuditConfig(BaseModel):
    """Configuration for audit trail system."""

    enabled: bool = True
    storage_path: Path = Path("./audit_logs")
    retention_days: int = Field(default=365, ge=30)
    high_risk_actions_only: bool = False
    include_reasoning_traces: bool = True
    encryption_enabled: bool = True


class GridSimulationConfig(BaseModel):
    """Configuration for grid simulation environment."""

    enabled: bool = True
    time_step_seconds: int = Field(default=60, ge=1, le=3600)
    max_nodes: int = Field(default=1000, ge=10, le=100000)
    renewable_ratio: float = Field(default=0.4, ge=0.0, le=1.0)
    demand_volatility: float = Field(default=0.2, ge=0.0, le=1.0)


class AetherConfig(BaseSettings):
    """
    Main configuration for ÆTHER-Grid.

    Configuration can be loaded from environment variables
    with the AETHER_ prefix (e.g., AETHER_LOG_LEVEL=DEBUG).
    """

    model_config = {"env_prefix": "AETHER_", "env_nested_delimiter": "__"}

    # General settings
    environment: str = Field(default="development")
    log_level: LogLevel = LogLevel.INFO
    debug: bool = False

    # API Keys (loaded from environment)
    openai_api_key: Optional[str] = Field(default=None, repr=False)
    anthropic_api_key: Optional[str] = Field(default=None, repr=False)
    ibmq_api_key: Optional[str] = Field(default=None, repr=False)

    # Component configurations
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    quantum: QuantumConfig = Field(default_factory=QuantumConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    simulation: GridSimulationConfig = Field(default_factory=GridSimulationConfig)

    # Feature flags
    enable_quantum_optimization: bool = False
    enable_hitl_safety_gates: bool = True
    enable_a2a_protocol: bool = True

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @classmethod
    def from_yaml(cls, path: Path) -> "AetherConfig":
        """Load configuration from a YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to a YAML file."""
        import yaml

        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)


def get_config() -> AetherConfig:
    """Get the global configuration instance."""
    return AetherConfig()
