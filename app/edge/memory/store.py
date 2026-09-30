"""Application-owned interface for persisted edge memory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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

    def list_points(self) -> list[StoredPoint]:
        """Return persisted local points for history and current-revision checks."""
        ...

    def retrieve_fleet(self, point_id: str) -> StoredPoint | None:
        """Return a point from the read-only fleet shard, if present."""
        ...

    def list_fleet_points(self) -> list[StoredPoint]:
        """Return persisted fleet points for cross-shard inspection."""
        ...

    def close(self) -> None:
        """Flush and release store resources."""
        ...


class MemoryOrigin(str, Enum):
    LOCAL = "LOCAL"
    FLEET = "FLEET"


@dataclass(frozen=True, slots=True)
class RawSearchHit:
    """Backend-neutral result from one vector search and one shard."""

    point_id: str
    score: float
    origin: MemoryOrigin
    payload: dict[str, Any]


class SearchableEdgeMemoryStore(EdgeMemoryStore, Protocol):
    """Backend-neutral extensions required by retrieval coordinators."""

    def embed_bm25_document(self, text: str) -> Any: ...
    def embed_bm25_query(self, text: str) -> Any: ...
    def query_dense(
        self, vector: list[float], limit: int, origin: MemoryOrigin
    ) -> list[RawSearchHit]: ...
    def query_sparse(
        self, vector: Any, limit: int, origin: MemoryOrigin
    ) -> list[RawSearchHit]: ...
