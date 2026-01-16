"""
Audit Trail System for ÆTHER-Grid

Implements Agentic Audit Trails for EU AI Act compliance.
Every decision trace, input context, policy check, and reasoning path
is recorded as a digital provenance record.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""

    # Decision events
    DECISION_MADE = "decision_made"
    DECISION_OVERRIDDEN = "decision_overridden"
    DECISION_REVERTED = "decision_reverted"

    # Action events
    ACTION_INITIATED = "action_initiated"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"
    ACTION_BLOCKED = "action_blocked"

    # Policy events
    POLICY_CHECK = "policy_check"
    POLICY_VIOLATION = "policy_violation"
    POLICY_OVERRIDE = "policy_override"

    # Human interaction
    HUMAN_APPROVAL = "human_approval"
    HUMAN_REJECTION = "human_rejection"
    HUMAN_OVERRIDE = "human_override"

    # System events
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    CONFIGURATION_CHANGE = "configuration_change"

    # Data events
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_EXPORT = "data_export"


class RiskCategory(Enum):
    """EU AI Act risk categories."""

    MINIMAL = "minimal"  # No significant risk
    LIMITED = "limited"  # Limited risk, transparency obligations
    HIGH = "high"  # High risk, full compliance required
    UNACCEPTABLE = "unacceptable"  # Prohibited applications


@dataclass
class ReasoningStep:
    """A step in the agent's reasoning process."""

    step_number: int = 0
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    alternatives_considered: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step_number,
            "description": self.description,
            "confidence": self.confidence,
            "alternatives": self.alternatives_considered,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PolicyCheck:
    """Record of a policy check."""

    policy_id: str = ""
    policy_name: str = ""
    passed: bool = True
    details: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "passed": self.passed,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class AuditRecord:
    """
    A complete audit record for a decision or action.

    This is the core unit of the Agentic Audit Trail, containing
    all information needed to understand and potentially reverse
    an AI decision.
    """

    id: UUID = field(default_factory=uuid4)
    event_type: AuditEventType = AuditEventType.DECISION_MADE
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Actor information
    agent_id: str = ""
    agent_name: str = ""
    agent_version: str = "1.0.0"

    # Context
    task_id: Optional[UUID] = None
    parent_record_id: Optional[UUID] = None
    session_id: Optional[str] = None

    # Input context
    input_data: dict[str, Any] = field(default_factory=dict)
    input_hash: str = ""  # For integrity verification

    # Reasoning trace
    reasoning_steps: list[ReasoningStep] = field(default_factory=list)
    final_confidence: float = 0.0

    # Policy compliance
    policy_checks: list[PolicyCheck] = field(default_factory=list)
    risk_category: RiskCategory = RiskCategory.LIMITED

    # Output
    output_data: dict[str, Any] = field(default_factory=dict)
    output_hash: str = ""

    # Reversibility
    is_reversible: bool = True
    reversal_instructions: Optional[str] = None
    original_state: Optional[dict] = None

    # Human oversight
    human_reviewed: bool = False
    human_reviewer_id: Optional[str] = None
    human_review_timestamp: Optional[datetime] = None
    human_notes: Optional[str] = None

    # Integrity
    record_hash: str = ""
    previous_record_hash: str = ""  # For chain integrity

    def compute_hashes(self) -> None:
        """Compute integrity hashes for the record."""
        # Hash input data
        input_str = json.dumps(self.input_data, sort_keys=True, default=str)
        self.input_hash = hashlib.sha256(input_str.encode()).hexdigest()

        # Hash output data
        output_str = json.dumps(self.output_data, sort_keys=True, default=str)
        self.output_hash = hashlib.sha256(output_str.encode()).hexdigest()

        # Hash entire record (excluding record_hash itself)
        record_data = {
            "id": str(self.id),
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "previous_record_hash": self.previous_record_hash,
        }
        record_str = json.dumps(record_data, sort_keys=True)
        self.record_hash = hashlib.sha256(record_str.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": str(self.id),
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "task_id": str(self.task_id) if self.task_id else None,
            "parent_record_id": str(self.parent_record_id) if self.parent_record_id else None,
            "session_id": self.session_id,
            "input_data": self.input_data,
            "input_hash": self.input_hash,
            "reasoning_steps": [s.to_dict() for s in self.reasoning_steps],
            "final_confidence": self.final_confidence,
            "policy_checks": [p.to_dict() for p in self.policy_checks],
            "risk_category": self.risk_category.value,
            "output_data": self.output_data,
            "output_hash": self.output_hash,
            "is_reversible": self.is_reversible,
            "reversal_instructions": self.reversal_instructions,
            "human_reviewed": self.human_reviewed,
            "human_reviewer_id": self.human_reviewer_id,
            "human_review_timestamp": (
                self.human_review_timestamp.isoformat()
                if self.human_review_timestamp else None
            ),
            "human_notes": self.human_notes,
            "record_hash": self.record_hash,
            "previous_record_hash": self.previous_record_hash,
        }


class AuditTrailStorage:
    """Storage backend for audit records."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._last_hash = ""
        self.logger = structlog.get_logger(__name__)

    async def store(self, record: AuditRecord) -> bool:
        """Store an audit record."""
        # Set chain reference
        record.previous_record_hash = self._last_hash

        # Compute hashes
        record.compute_hashes()

        # Store to file (one file per day, append mode)
        date_str = record.timestamp.strftime("%Y-%m-%d")
        file_path = self.storage_path / f"audit_{date_str}.jsonl"

        try:
            with open(file_path, "a") as f:
                json.dump(record.to_dict(), f)
                f.write("\n")

            self._last_hash = record.record_hash
            self.logger.debug("audit_record_stored", record_id=str(record.id))
            return True

        except Exception as e:
            self.logger.error("audit_storage_failed", error=str(e))
            return False

    async def retrieve(
        self,
        start_date: datetime,
        end_date: datetime,
        agent_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
    ) -> list[AuditRecord]:
        """Retrieve audit records matching criteria."""
        records = []
        current = start_date

        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            file_path = self.storage_path / f"audit_{date_str}.jsonl"

            if file_path.exists():
                with open(file_path) as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)

                            # Apply filters
                            if agent_id and data.get("agent_id") != agent_id:
                                continue
                            if event_type and data.get("event_type") != event_type.value:
                                continue

                            # Convert to AuditRecord
                            record = self._dict_to_record(data)
                            records.append(record)

            current = datetime(
                current.year, current.month, current.day
            ) + __import__("datetime").timedelta(days=1)

        return records

    def _dict_to_record(self, data: dict) -> AuditRecord:
        """Convert dictionary to AuditRecord."""
        record = AuditRecord(
            id=UUID(data["id"]),
            event_type=AuditEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            input_data=data.get("input_data", {}),
            input_hash=data.get("input_hash", ""),
            output_data=data.get("output_data", {}),
            output_hash=data.get("output_hash", ""),
            record_hash=data.get("record_hash", ""),
            previous_record_hash=data.get("previous_record_hash", ""),
        )

        # Reconstruct reasoning steps
        for step_data in data.get("reasoning_steps", []):
            record.reasoning_steps.append(ReasoningStep(
                step_number=step_data.get("step", 0),
                description=step_data.get("description", ""),
                confidence=step_data.get("confidence", 0.0),
            ))

        # Reconstruct policy checks
        for check_data in data.get("policy_checks", []):
            record.policy_checks.append(PolicyCheck(
                policy_id=check_data.get("policy_id", ""),
                policy_name=check_data.get("policy_name", ""),
                passed=check_data.get("passed", True),
                details=check_data.get("details", ""),
            ))

        return record

    async def verify_chain_integrity(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[bool, list[str]]:
        """Verify the integrity of the audit chain."""
        errors = []
        records = await self.retrieve(start_date, end_date)

        expected_prev_hash = ""
        for record in records:
            # Verify chain link
            if record.previous_record_hash != expected_prev_hash:
                errors.append(
                    f"Chain break at {record.id}: expected {expected_prev_hash}, "
                    f"got {record.previous_record_hash}"
                )

            # Verify record hash
            original_hash = record.record_hash
            record.compute_hashes()
            if record.record_hash != original_hash:
                errors.append(f"Hash mismatch at {record.id}: record may have been tampered")

            expected_prev_hash = original_hash

        return len(errors) == 0, errors


class AuditTrail:
    """
    Main interface for the Agentic Audit Trail system.

    Provides methods for recording decisions, actions, and events
    in a way that meets EU AI Act compliance requirements.
    """

    def __init__(
        self,
        storage_path: Path = Path("./audit_logs"),
        auto_store: bool = True,
    ):
        self.storage = AuditTrailStorage(storage_path)
        self.auto_store = auto_store
        self._session_id = str(uuid4())
        self._current_records: list[AuditRecord] = []
        self.logger = structlog.get_logger(__name__)

    async def record_decision(
        self,
        agent_id: str,
        agent_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        reasoning_steps: list[ReasoningStep],
        policy_checks: list[PolicyCheck],
        task_id: Optional[UUID] = None,
        is_reversible: bool = True,
        reversal_instructions: Optional[str] = None,
        original_state: Optional[dict] = None,
    ) -> AuditRecord:
        """Record a decision made by an agent."""
        record = AuditRecord(
            event_type=AuditEventType.DECISION_MADE,
            agent_id=agent_id,
            agent_name=agent_name,
            task_id=task_id,
            session_id=self._session_id,
            input_data=input_data,
            reasoning_steps=reasoning_steps,
            final_confidence=max((s.confidence for s in reasoning_steps), default=0.0),
            policy_checks=policy_checks,
            risk_category=self._determine_risk_category(policy_checks),
            output_data=output_data,
            is_reversible=is_reversible,
            reversal_instructions=reversal_instructions,
            original_state=original_state,
        )

        if self.auto_store:
            await self.storage.store(record)

        self._current_records.append(record)
        self.logger.info(
            "decision_recorded",
            record_id=str(record.id),
            agent_id=agent_id,
        )

        return record

    async def record_action(
        self,
        agent_id: str,
        agent_name: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
        success: bool,
        task_id: Optional[UUID] = None,
    ) -> AuditRecord:
        """Record an action taken by an agent."""
        event_type = (
            AuditEventType.ACTION_COMPLETED if success
            else AuditEventType.ACTION_FAILED
        )

        record = AuditRecord(
            event_type=event_type,
            agent_id=agent_id,
            agent_name=agent_name,
            task_id=task_id,
            session_id=self._session_id,
            input_data={
                "action_type": action_type,
                "target": target,
                "parameters": parameters,
            },
            output_data={"result": result, "success": success},
        )

        if self.auto_store:
            await self.storage.store(record)

        self._current_records.append(record)
        return record

    async def record_policy_check(
        self,
        agent_id: str,
        policy_id: str,
        policy_name: str,
        passed: bool,
        details: str,
        context: dict[str, Any],
    ) -> AuditRecord:
        """Record a policy compliance check."""
        event_type = (
            AuditEventType.POLICY_CHECK if passed
            else AuditEventType.POLICY_VIOLATION
        )

        record = AuditRecord(
            event_type=event_type,
            agent_id=agent_id,
            session_id=self._session_id,
            input_data=context,
            output_data={
                "policy_id": policy_id,
                "policy_name": policy_name,
                "passed": passed,
                "details": details,
            },
            policy_checks=[PolicyCheck(
                policy_id=policy_id,
                policy_name=policy_name,
                passed=passed,
                details=details,
            )],
        )

        if self.auto_store:
            await self.storage.store(record)

        return record

    async def record_human_review(
        self,
        original_record_id: UUID,
        reviewer_id: str,
        approved: bool,
        notes: Optional[str] = None,
    ) -> AuditRecord:
        """Record human review of an AI decision."""
        event_type = (
            AuditEventType.HUMAN_APPROVAL if approved
            else AuditEventType.HUMAN_REJECTION
        )

        record = AuditRecord(
            event_type=event_type,
            agent_id="human_reviewer",
            agent_name=reviewer_id,
            parent_record_id=original_record_id,
            session_id=self._session_id,
            input_data={"original_record_id": str(original_record_id)},
            output_data={
                "approved": approved,
                "notes": notes,
            },
            human_reviewed=True,
            human_reviewer_id=reviewer_id,
            human_review_timestamp=datetime.utcnow(),
            human_notes=notes,
        )

        if self.auto_store:
            await self.storage.store(record)

        return record

    def _determine_risk_category(
        self,
        policy_checks: list[PolicyCheck],
    ) -> RiskCategory:
        """Determine risk category based on policy checks."""
        if not policy_checks:
            return RiskCategory.LIMITED

        # If any critical policies failed, it's high risk
        failed_checks = [p for p in policy_checks if not p.passed]
        if len(failed_checks) > 2:
            return RiskCategory.HIGH
        elif len(failed_checks) > 0:
            return RiskCategory.LIMITED

        return RiskCategory.MINIMAL

    async def generate_compliance_report(
        self,
        start_date: datetime,
        end_date: datetime,
        agent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate a compliance report for the given period."""
        records = await self.storage.retrieve(start_date, end_date, agent_id)

        # Aggregate statistics
        total_decisions = len([
            r for r in records if r.event_type == AuditEventType.DECISION_MADE
        ])
        human_reviewed = len([r for r in records if r.human_reviewed])
        policy_violations = len([
            r for r in records if r.event_type == AuditEventType.POLICY_VIOLATION
        ])

        risk_distribution = {cat.value: 0 for cat in RiskCategory}
        for record in records:
            risk_distribution[record.risk_category.value] += 1

        # Verify integrity
        is_valid, integrity_errors = await self.storage.verify_chain_integrity(
            start_date, end_date
        )

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_records": len(records),
                "total_decisions": total_decisions,
                "human_reviewed": human_reviewed,
                "policy_violations": policy_violations,
                "human_review_rate": (
                    human_reviewed / total_decisions if total_decisions > 0 else 0
                ),
            },
            "risk_distribution": risk_distribution,
            "integrity": {
                "valid": is_valid,
                "errors": integrity_errors,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
