"""
Risk Agent for ÆTHER-Grid

Monitors for anomalies and agentic security threats such as
prompt injection, tool abuse, and unauthorized access attempts.
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
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


class ThreatType(Enum):
    """Types of security threats."""

    PROMPT_INJECTION = "prompt_injection"
    TOOL_ABUSE = "tool_abuse"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    REPLAY_ATTACK = "replay_attack"


class ThreatSeverity(Enum):
    """Severity levels for threats."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class SecurityEvent:
    """A security-relevant event."""

    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: str = ""
    source_agent: str = ""
    source_ip: Optional[str] = None
    action_attempted: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "action_attempted": self.action_attempted,
            "risk_score": self.risk_score,
        }


@dataclass
class Threat:
    """A detected security threat."""

    id: UUID = field(default_factory=uuid4)
    threat_type: ThreatType = ThreatType.ANOMALOUS_BEHAVIOR
    severity: ThreatSeverity = ThreatSeverity.LOW
    detected_at: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    description: str = ""
    evidence: list[SecurityEvent] = field(default_factory=list)
    mitigation_applied: bool = False
    mitigation_action: str = ""
    confidence: float = 0.0
    false_positive_probability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "type": self.threat_type.value,
            "severity": self.severity.name,
            "detected_at": self.detected_at.isoformat(),
            "source": self.source,
            "description": self.description,
            "mitigation_applied": self.mitigation_applied,
            "confidence": self.confidence,
        }


@dataclass
class RiskAssessment:
    """Comprehensive risk assessment result."""

    overall_risk_score: float = 0.0
    threats_detected: list[Threat] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    approved: bool = True
    requires_human_review: bool = False
    assessment_confidence: float = 0.0


class PromptInjectionDetector:
    """Detects prompt injection attempts in agent inputs."""

    # Patterns indicative of prompt injection
    INJECTION_PATTERNS = [
        r"ignore\s+(previous|all|above)\s+(instructions?|prompts?)",
        r"disregard\s+(your|the)\s+(instructions?|rules?|guidelines?)",
        r"you\s+are\s+now\s+(a|an)\s+",
        r"new\s+instructions?:",
        r"override\s+(mode|instructions?)",
        r"jailbreak",
        r"pretend\s+(you|that)\s+(are|you're)",
        r"act\s+as\s+if",
        r"system\s*:\s*",
        r"\[INST\]|\[/INST\]",
        r"<\|im_start\|>|<\|im_end\|>",
        r"###\s*(instruction|system|human|assistant)",
    ]

    def __init__(self):
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]

    def detect(self, text: str) -> tuple[bool, float, list[str]]:
        """
        Detect prompt injection in text.

        Returns:
            Tuple of (is_injection, confidence, matched_patterns)
        """
        if not text:
            return False, 0.0, []

        matched = []
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(text):
                matched.append(self.INJECTION_PATTERNS[i])

        if not matched:
            return False, 0.0, []

        # Confidence based on number of patterns matched
        confidence = min(len(matched) * 0.3 + 0.4, 1.0)
        return True, confidence, matched


class ToolAbuseDetector:
    """Detects potential tool abuse patterns."""

    def __init__(self):
        self._action_counts: dict[str, list[datetime]] = defaultdict(list)
        self._rate_window_seconds = 60
        self._max_actions_per_window = 100

    def record_action(self, agent_id: str, action: str) -> None:
        """Record an action for rate limiting."""
        key = f"{agent_id}:{action}"
        self._action_counts[key].append(datetime.utcnow())
        self._cleanup_old_entries(key)

    def _cleanup_old_entries(self, key: str) -> None:
        """Remove old entries outside the rate window."""
        cutoff = datetime.utcnow() - timedelta(seconds=self._rate_window_seconds)
        self._action_counts[key] = [
            t for t in self._action_counts[key] if t > cutoff
        ]

    def check_rate_limit(self, agent_id: str, action: str) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.

        Returns:
            Tuple of (is_exceeded, current_count)
        """
        key = f"{agent_id}:{action}"
        self._cleanup_old_entries(key)
        count = len(self._action_counts[key])
        return count > self._max_actions_per_window, count

    def detect_abuse_pattern(
        self,
        agent_id: str,
        actions: list[Action],
    ) -> tuple[bool, str]:
        """Detect abuse patterns in a sequence of actions."""
        if not actions:
            return False, ""

        # Check for repeated high-risk actions
        high_risk_count = sum(
            1 for a in actions if a.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )
        if high_risk_count > 5:
            return True, "Excessive high-risk actions in short period"

        # Check for privilege escalation pattern
        risk_levels = [a.risk_level.value for a in actions]
        if len(risk_levels) >= 3:
            # Monotonically increasing risk
            if all(risk_levels[i] <= risk_levels[i + 1] for i in range(len(risk_levels) - 1)):
                if risk_levels[-1] >= RiskLevel.HIGH.value:
                    return True, "Potential privilege escalation detected"

        return False, ""


class RiskAgent(BaseAgent):
    """
    Risk Agent for security monitoring and threat detection.

    Capabilities:
    - Prompt injection detection
    - Tool abuse monitoring
    - Rate limiting enforcement
    - Anomalous behavior detection
    - Policy compliance checking
    - Human-in-the-loop triggers
    """

    def __init__(
        self,
        agent_id: str = "risk-001",
        max_risk_score: float = 0.8,
        enable_auto_mitigation: bool = True,
    ):
        super().__init__(
            agent_id=agent_id,
            name="Risk Agent",
            description="Security monitoring and threat detection",
        )
        self.max_risk_score = max_risk_score
        self.enable_auto_mitigation = enable_auto_mitigation

        self._injection_detector = PromptInjectionDetector()
        self._abuse_detector = ToolAbuseDetector()
        self._threat_history: list[Threat] = []
        self._blocked_agents: set[str] = set()
        self._event_log: list[SecurityEvent] = []

        # Policy rules
        self._policies: dict[str, dict[str, Any]] = {
            "max_concurrent_executions": {"limit": 10, "action": "throttle"},
            "critical_action_approval": {"requires_human": True},
            "data_access_logging": {"enabled": True},
        }

    def get_capabilities(self) -> list[str]:
        """Return agent capabilities."""
        return [
            "prompt_injection_detection",
            "tool_abuse_monitoring",
            "rate_limiting",
            "anomaly_detection",
            "policy_compliance",
            "threat_assessment",
            "risk_scoring",
        ]

    async def process(self, task: Task) -> Result:
        """Process a risk assessment task."""
        start_time = datetime.utcnow()
        self._record_task(task.id)

        try:
            task_type = task.context.get("task_type", "assess")

            if task_type == "assess":
                result_data = await self._assess_risk(task)
            elif task_type == "validate_action":
                result_data = await self._validate_action(task)
            elif task_type == "check_input":
                result_data = await self._check_input(task)
            elif task_type == "get_threats":
                result_data = await self._get_threats(task)
            else:
                result_data = await self._assess_risk(task)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return Result(
                task_id=task.id,
                success=True,
                data=result_data,
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
                reasoning_trace=[
                    f"Task type: {task_type}",
                    f"Threats detected: {len(self._threat_history)}",
                    f"Blocked agents: {len(self._blocked_agents)}",
                ],
            )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error("risk_assessment_failed", error=str(e), task_id=str(task.id))
            return Result(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                execution_time_ms=execution_time,
            )

    async def validate(self, action: Action) -> bool:
        """Validate an action before execution."""
        # Risk agent validates other agents' actions
        if action.risk_level == RiskLevel.CRITICAL:
            self.logger.warning(
                "critical_action_requires_approval",
                action_id=str(action.id),
            )
            return False

        return True

    async def _assess_risk(self, task: Task) -> dict[str, Any]:
        """Perform comprehensive risk assessment."""
        assessment = RiskAssessment()

        # Get context
        source_agent = task.context.get("source_agent", "unknown")
        actions = task.context.get("actions", [])
        input_text = task.context.get("input_text", "")

        # Check if agent is blocked
        if source_agent in self._blocked_agents:
            assessment.approved = False
            assessment.overall_risk_score = 1.0
            assessment.recommendations.append(f"Agent {source_agent} is blocked")
            return self._format_assessment(assessment)

        # Prompt injection check
        if input_text:
            is_injection, confidence, patterns = self._injection_detector.detect(input_text)
            if is_injection:
                threat = Threat(
                    threat_type=ThreatType.PROMPT_INJECTION,
                    severity=ThreatSeverity.HIGH,
                    source=source_agent,
                    description=f"Prompt injection detected with confidence {confidence:.2f}",
                    confidence=confidence,
                )
                assessment.threats_detected.append(threat)
                self._threat_history.append(threat)
                assessment.overall_risk_score = max(assessment.overall_risk_score, 0.9)

        # Tool abuse check
        if actions:
            parsed_actions = self._parse_actions(actions)
            is_abuse, abuse_reason = self._abuse_detector.detect_abuse_pattern(
                source_agent, parsed_actions
            )
            if is_abuse:
                threat = Threat(
                    threat_type=ThreatType.TOOL_ABUSE,
                    severity=ThreatSeverity.MEDIUM,
                    source=source_agent,
                    description=abuse_reason,
                    confidence=0.85,
                )
                assessment.threats_detected.append(threat)
                self._threat_history.append(threat)
                assessment.overall_risk_score = max(assessment.overall_risk_score, 0.7)

        # Rate limit check
        exceeded, count = self._abuse_detector.check_rate_limit(source_agent, "any")
        if exceeded:
            threat = Threat(
                threat_type=ThreatType.RATE_LIMIT_VIOLATION,
                severity=ThreatSeverity.MEDIUM,
                source=source_agent,
                description=f"Rate limit exceeded: {count} actions in window",
                confidence=1.0,
            )
            assessment.threats_detected.append(threat)
            assessment.overall_risk_score = max(assessment.overall_risk_score, 0.6)

        # Determine approval
        if assessment.overall_risk_score > self.max_risk_score:
            assessment.approved = False
            assessment.requires_human_review = True
            assessment.recommendations.append("Manual review required due to high risk score")

            if self.enable_auto_mitigation:
                await self._apply_mitigation(source_agent, assessment.threats_detected)
        else:
            assessment.approved = True

        assessment.assessment_confidence = 0.9

        return self._format_assessment(assessment)

    def _parse_actions(self, actions: list[Any]) -> list[Action]:
        """Parse action data into Action objects."""
        parsed = []
        for a in actions:
            if isinstance(a, Action):
                parsed.append(a)
            elif isinstance(a, dict):
                parsed.append(Action(
                    action_type=ActionType(a.get("type", "query")),
                    target=a.get("target", ""),
                    risk_level=RiskLevel(a.get("risk_level", 1)),
                ))
        return parsed

    async def _validate_action(self, task: Task) -> dict[str, Any]:
        """Validate a specific action."""
        action_data = task.context.get("action", {})
        source_agent = task.context.get("source_agent", "unknown")

        # Record for rate limiting
        self._abuse_detector.record_action(
            source_agent,
            action_data.get("type", "unknown"),
        )

        # Check various conditions
        is_valid = True
        reasons = []

        # Agent blocked check
        if source_agent in self._blocked_agents:
            is_valid = False
            reasons.append("Agent is blocked")

        # Risk level check
        risk_level = action_data.get("risk_level", 0)
        if risk_level >= RiskLevel.CRITICAL.value:
            is_valid = False
            reasons.append("Critical risk actions require explicit approval")

        # Rate limit check
        exceeded, _ = self._abuse_detector.check_rate_limit(source_agent, "any")
        if exceeded:
            is_valid = False
            reasons.append("Rate limit exceeded")

        return {
            "valid": is_valid,
            "reasons": reasons,
            "source_agent": source_agent,
            "action_type": action_data.get("type"),
        }

    async def _check_input(self, task: Task) -> dict[str, Any]:
        """Check input text for security issues."""
        text = task.context.get("text", "")
        source = task.context.get("source", "unknown")

        is_injection, confidence, patterns = self._injection_detector.detect(text)

        # Generate input hash for replay detection
        input_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        return {
            "safe": not is_injection,
            "injection_detected": is_injection,
            "confidence": confidence,
            "matched_patterns": patterns,
            "input_hash": input_hash,
            "source": source,
        }

    async def _get_threats(self, task: Task) -> dict[str, Any]:
        """Get recent threats."""
        hours = task.context.get("hours", 24)
        severity_filter = task.context.get("min_severity", "LOW")

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        min_severity = ThreatSeverity[severity_filter].value

        filtered = [
            t for t in self._threat_history
            if t.detected_at > cutoff and t.severity.value >= min_severity
        ]

        return {
            "threats": [t.to_dict() for t in filtered],
            "total_count": len(filtered),
            "time_range_hours": hours,
            "min_severity": severity_filter,
        }

    async def _apply_mitigation(self, agent_id: str, threats: list[Threat]) -> None:
        """Apply automatic mitigation for threats."""
        critical_count = sum(
            1 for t in threats if t.severity == ThreatSeverity.CRITICAL
        )

        if critical_count > 0:
            self._blocked_agents.add(agent_id)
            self.logger.warning(
                "agent_blocked",
                agent_id=agent_id,
                reason="Critical threats detected",
            )
            for threat in threats:
                threat.mitigation_applied = True
                threat.mitigation_action = "Agent blocked"

    def _format_assessment(self, assessment: RiskAssessment) -> dict[str, Any]:
        """Format assessment result for output."""
        return {
            "approved": assessment.approved,
            "risk_score": assessment.overall_risk_score,
            "threats": [t.to_dict() for t in assessment.threats_detected],
            "policy_violations": assessment.policy_violations,
            "recommendations": assessment.recommendations,
            "requires_human_review": assessment.requires_human_review,
            "confidence": assessment.assessment_confidence,
        }

    def unblock_agent(self, agent_id: str) -> bool:
        """Remove an agent from the blocked list."""
        if agent_id in self._blocked_agents:
            self._blocked_agents.remove(agent_id)
            self.logger.info("agent_unblocked", agent_id=agent_id)
            return True
        return False

    def get_security_status(self) -> dict[str, Any]:
        """Get current security status."""
        return {
            "blocked_agents": list(self._blocked_agents),
            "recent_threats": len([
                t for t in self._threat_history
                if t.detected_at > datetime.utcnow() - timedelta(hours=1)
            ]),
            "total_threats": len(self._threat_history),
            "policies_active": len(self._policies),
        }
