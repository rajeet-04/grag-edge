import pytest

from app.edge.memory.models import (
    Importance,
    MemoryRecord,
    MemoryType,
    Sensitivity,
    SyncPolicy,
)
from app.edge.policy.engine import SyncPolicyEngine


def memory(**changes):
    values = dict(
        memory_id="00000000-0000-0000-0000-000000000001",
        logical_id="00000000-0000-0000-0000-000000000002",
        content="inspection observation",
        created_at="2026-09-30T00:00:00Z",
        updated_at="2026-09-30T00:00:00Z",
        revision=1,
        content_hash="abc",
    )
    values.update(changes)
    return MemoryRecord.model_validate(values)


@pytest.mark.parametrize(
    ("record", "action", "reason"),
    [
        (memory(sensitivity=Sensitivity.RESTRICTED, importance=Importance.CRITICAL), SyncPolicy.LOCAL_ONLY, "privacy_restricted"),
        (memory(requested_sync_policy=SyncPolicy.LOCAL_ONLY, memory_type=MemoryType.LEARNED_FACT), SyncPolicy.LOCAL_ONLY, "operator_local_only"),
        (memory(requested_sync_policy=SyncPolicy.APPROVAL_REQUIRED, memory_type=MemoryType.INCIDENT), SyncPolicy.APPROVAL_REQUIRED, "operator_approval_required"),
        (memory(memory_type=MemoryType.OPERATOR_NOTE), SyncPolicy.APPROVAL_REQUIRED, "operator_note_requires_review"),
        (memory(memory_type=MemoryType.INCIDENT, importance=Importance.CRITICAL, confidence=0.9), SyncPolicy.AUTO, "high_confidence_incident"),
        (memory(memory_type=MemoryType.INCIDENT, importance=Importance.HIGH, confidence=0.79), SyncPolicy.LOCAL_ONLY, "incident_confidence_below_threshold"),
        (memory(memory_type=MemoryType.OBSERVATION, importance=Importance.LOW), SyncPolicy.LOCAL_ONLY, "routine_observation_local_only"),
        (memory(memory_type=MemoryType.LEARNED_FACT), SyncPolicy.AUTO, "fleet_safe_learned_fact"),
        (memory(), SyncPolicy.LOCAL_ONLY, "default_local_only"),
    ],
)
def test_policy_precedence_and_rule_examples(record, action, reason):
    decision = SyncPolicyEngine().evaluate(record)
    assert decision.action is action
    assert reason in decision.reason_codes


def test_explicit_auto_overrides_routine_rule_but_not_privacy():
    engine = SyncPolicyEngine()
    operator_choice = engine.evaluate(memory(requested_sync_policy=SyncPolicy.AUTO, importance=Importance.LOW))
    restricted = engine.evaluate(memory(requested_sync_policy=SyncPolicy.AUTO, sensitivity=Sensitivity.RESTRICTED))
    assert operator_choice.action is SyncPolicy.AUTO
    assert restricted.action is SyncPolicy.LOCAL_ONLY
    assert "privacy_restricted" in restricted.reason_codes
