"""Ordered deterministic synchronization policy evaluation."""
from dataclasses import dataclass

from app.edge.memory.models import (
    Importance,
    MemoryRecord,
    MemoryType,
    Sensitivity,
    SyncPolicy,
)
from app.edge.policy import rules


@dataclass(frozen=True, slots=True)
class SyncDecision:
    action: SyncPolicy
    reason_codes: tuple[str, ...]


class SyncPolicyEngine:
    MIN_INCIDENT_CONFIDENCE = 0.8

    def evaluate(self, memory: MemoryRecord) -> SyncDecision:
        if memory.sensitivity is Sensitivity.RESTRICTED:
            return SyncDecision(SyncPolicy.LOCAL_ONLY, (rules.PRIVACY_RESTRICTED,))

        explicit = memory.requested_sync_policy
        if explicit is SyncPolicy.LOCAL_ONLY:
            return SyncDecision(SyncPolicy.LOCAL_ONLY, (rules.OPERATOR_LOCAL_ONLY,))
        if explicit is SyncPolicy.APPROVAL_REQUIRED:
            return SyncDecision(SyncPolicy.APPROVAL_REQUIRED, (rules.OPERATOR_APPROVAL_REQUIRED,))
        if explicit is SyncPolicy.AUTO:
            return SyncDecision(SyncPolicy.AUTO, (rules.OPERATOR_AUTO,))

        if memory.memory_type is MemoryType.OPERATOR_NOTE:
            return SyncDecision(SyncPolicy.APPROVAL_REQUIRED, (rules.OPERATOR_NOTE_REQUIRES_REVIEW,))

        if memory.memory_type is MemoryType.INCIDENT and memory.importance in (Importance.HIGH, Importance.CRITICAL):
            if memory.sensitivity is Sensitivity.FLEET_SAFE and (memory.confidence or 0.0) >= self.MIN_INCIDENT_CONFIDENCE:
                return SyncDecision(SyncPolicy.AUTO, (rules.HIGH_CONFIDENCE_INCIDENT,))
            return SyncDecision(SyncPolicy.LOCAL_ONLY, (rules.INCIDENT_CONFIDENCE_BELOW_THRESHOLD,))

        if memory.memory_type is MemoryType.OBSERVATION and memory.importance is Importance.LOW:
            return SyncDecision(SyncPolicy.LOCAL_ONLY, (rules.ROUTINE_OBSERVATION_LOCAL_ONLY,))

        if memory.memory_type is MemoryType.LEARNED_FACT and memory.sensitivity is Sensitivity.FLEET_SAFE:
            return SyncDecision(SyncPolicy.AUTO, (rules.FLEET_SAFE_LEARNED_FACT,))

        return SyncDecision(SyncPolicy.LOCAL_ONLY, (rules.DEFAULT_LOCAL_ONLY,))
