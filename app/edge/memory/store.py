"""Application-owned interface for persisted edge memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredPoint:
    """A memory point independent of the underlying vector database."""

    id: str
    dense: list[float]
    sparse: Any | None
    payload: dict[str, Any]


@runtime_checkable
class EdgeMemoryStore(Protocol):
    """Operations required by application memory consumers."""

    def upsert(self, point: StoredPoint) -> None:
        """Insert or replace a memory point."""
        ...

    def retrieve(self, point_id: str) -> StoredPoint | None:
        """Return a point by identifier, if present."""
        ...

    def close(self) -> None:
        """Flush and release store resources."""
        ...
