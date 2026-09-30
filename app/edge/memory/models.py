"""Robot memory records and write commands."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    OBSERVATION = "observation"
    PROCEDURE = "procedure"
    INCIDENT = "incident"
    OPERATOR_NOTE = "operator_note"
    LEARNED_FACT = "learned_fact"


class Importance(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Sensitivity(str, Enum):
    FLEET_SAFE = "fleet_safe"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class SyncPolicy(str, Enum):
    LOCAL_ONLY = "local_only"
    AUTO = "auto"
    APPROVAL_REQUIRED = "approval_required"


class SyncState(str, Enum):
    NEW = "NEW"
    LOCAL_DIRTY = "LOCAL_DIRTY"
    LOCAL_ONLY = "LOCAL_ONLY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    RETRY_WAIT = "RETRY_WAIT"
    SNAPSHOT_PENDING = "SNAPSHOT_PENDING"
    SYNCHRONIZED = "SYNCHRONIZED"
    CONFLICTED = "CONFLICTED"
    SUPERSEDED = "SUPERSEDED"


class MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    memory_id: str
    logical_id: str
    device_id: str | None = None
    memory_type: MemoryType = MemoryType.OBSERVATION
    content: str
    created_at: datetime
    updated_at: datetime
    revision: int
    parent_revision: int | None = None
    content_hash: str
    confidence: float | None = None
    importance: Importance = Importance.NORMAL
    sensitivity: Sensitivity = Sensitivity.FLEET_SAFE
    requested_sync_policy: SyncPolicy | None = None
    sync_policy: SyncPolicy = SyncPolicy.LOCAL_ONLY
    sync_state: SyncState = SyncState.LOCAL_DIRTY
    sync_reason_codes: tuple[str, ...] = ()
    source_type: str | None = None
    source_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding_version: str = "default"
    sync_timestamp: datetime | None = None
    is_deleted: bool = False


class CreateMemory(BaseModel):
    memory_id: UUID | None = None
    logical_id: UUID | None = None
    device_id: str | None = None
    memory_type: MemoryType = MemoryType.OBSERVATION
    content: str = Field(min_length=1)
    confidence: float | None = None
    importance: Importance = Importance.NORMAL
    sensitivity: Sensitivity = Sensitivity.FLEET_SAFE
    sync_policy: SyncPolicy = SyncPolicy.LOCAL_ONLY
    source_type: str | None = None
    source_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding_version: str = "default"


class ReviseMemory(BaseModel):
    content: str = Field(min_length=1)
    parent_revision: int
    device_id: str | None = None
    memory_type: MemoryType | None = None
    confidence: float | None = None
    importance: Importance | None = None
    sensitivity: Sensitivity | None = None
    sync_policy: SyncPolicy | None = None
    source_type: str | None = None
    source_id: str | None = None
    tags: list[str] | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
