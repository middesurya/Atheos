"""
ÆTHER-Grid: Autonomous Energy Transition & Hybrid Evolutionary Response

A multi-agent system for intelligent energy grid management using
quantum-enhanced optimization and verifiable AI.
"""

__version__ = "0.1.0"
__author__ = "ÆTHER-Grid Team"

from aether_grid.core.base import BaseAgent, Task, Result, Action
from aether_grid.core.orchestrator import Orchestrator

__all__ = [
    "BaseAgent",
    "Task",
    "Result",
    "Action",
    "Orchestrator",
    "__version__",
]
