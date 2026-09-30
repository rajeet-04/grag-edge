"""Persistent Qdrant Edge adapter for application-owned memory points."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeSparseVectorParams,
    EdgeVectorParams,
    Modifier,
    Point,
    SparseVector,
    UpdateOperation,
)

from app.edge.memory.store import EdgeMemoryStore, StoredPoint


class QdrantEdgeStore:
    """Owns mutable robot memory and read-only fleet memory shards."""

    def __init__(
        self, local_path: Path, fleet_path: Path, embedding_dimension: int
    ) -> None:
        if embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        self.local_path = Path(local_path)
        self.fleet_path = Path(fleet_path)
        self.embedding_dimension = embedding_dimension
        self._local: EdgeShard | None = None
        self._fleet: EdgeShard | None = None

    def open(self) -> None:
        """Load persisted shards or create them at previously unused paths."""
        if self._local is not None or self._fleet is not None:
            raise RuntimeError("Qdrant Edge store is already open")
        config = EdgeConfig(
            vectors={"dense": EdgeVectorParams(self.embedding_dimension, Distance.Cosine)},
            sparse_vectors={"text": EdgeSparseVectorParams(modifier=Modifier.Idf)},
        )
        self._local = self._open_shard(self.local_path, config)
        try:
            self._fleet = self._open_shard(self.fleet_path, config)
        except Exception:
            self._local.close()
            self._local = None
            raise

    @staticmethod
    def _open_shard(path: Path, config: EdgeConfig) -> EdgeShard:
        existed = path.exists()
        if existed:
            if not path.is_dir() or not any(path.iterdir()):
                raise RuntimeError(
                    f"Qdrant Edge shard at {path} is empty or corrupt; "
                    "restore its shard data or choose a new path"
                )
            try:
                return EdgeShard.load(str(path), config)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load Qdrant Edge shard at {path}; "
                    "check shard files and embedding dimension"
                ) from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir()
        try:
            return EdgeShard.create(str(path), config)
        except Exception as exc:
            raise RuntimeError(f"Could not create Qdrant Edge shard at {path}") from exc

    @staticmethod
    def _point_id(point_id: str) -> str:
        try:
            return str(UUID(point_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"Qdrant Edge point id must be a UUID: {point_id!r}") from exc

    @staticmethod
    def _sparse_value(sparse: Any | None) -> SparseVector | None:
        if sparse is None:
            return None
        if isinstance(sparse, SparseVector):
            return sparse
        if isinstance(sparse, dict) and "indices" in sparse and "values" in sparse:
            return SparseVector(indices=sparse["indices"], values=sparse["values"])
        raise TypeError("sparse must be a qdrant_edge.SparseVector or indices/values mapping")

    def _require_open(self) -> tuple[EdgeShard, EdgeShard]:
        if self._local is None or self._fleet is None:
            raise RuntimeError("Qdrant Edge store is not open; call open() first")
        return self._local, self._fleet

    def upsert_local(self, point: StoredPoint) -> None:
        local, _ = self._require_open()
        if len(point.dense) != self.embedding_dimension:
            raise ValueError(
                f"dense vector dimension {len(point.dense)} does not match "
                f"configured embedding dimension {self.embedding_dimension}"
            )
        vectors: dict[str, Any] = {"dense": point.dense}
        sparse = self._sparse_value(point.sparse)
        if sparse is not None:
            vectors["text"] = sparse
        try:
            edge_point = Point(
                self._point_id(point.id), vectors, payload=dict(point.payload)
            )
            local.update(UpdateOperation.upsert_points([edge_point]))
            local.flush()
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Could not upsert point {point.id} into local shard") from exc

    def retrieve_local(self, point_id: str) -> StoredPoint | None:
        local, _ = self._require_open()
        return self._retrieve(local, point_id)

    def retrieve_fleet(self, point_id: str) -> StoredPoint | None:
        _, fleet = self._require_open()
        return self._retrieve(fleet, point_id)

    @classmethod
    def _retrieve(cls, shard: EdgeShard, point_id: str) -> StoredPoint | None:
        normalized_id = cls._point_id(point_id)
        try:
            records = shard.retrieve(
                [normalized_id], with_payload=True, with_vector=True
            )
        except Exception as exc:
            raise RuntimeError(f"Could not retrieve point {normalized_id}") from exc
        if not records:
            return None
        record = records[0]
        vectors = record.vector or {}
        dense = vectors.get("dense", []) if isinstance(vectors, dict) else vectors
        sparse = vectors.get("text") if isinstance(vectors, dict) else None
        if isinstance(sparse, SparseVector):
            sparse = {"indices": list(sparse.indices), "values": list(sparse.values)}
        return StoredPoint(
            id=str(record.id),
            dense=list(dense),
            sparse=sparse,
            payload=dict(record.payload or {}),
        )

    def upsert(self, point: StoredPoint) -> None:
        self.upsert_local(point)

    def retrieve(self, point_id: str) -> StoredPoint | None:
        return self.retrieve_local(point_id)

    def close(self) -> None:
        """Flush and close both shards; safe to call repeatedly."""
        errors: list[Exception] = []
        for name in ("_local", "_fleet"):
            shard = getattr(self, name)
            setattr(self, name, None)
            if shard is not None:
                try:
                    shard.flush()
                    shard.close()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            raise RuntimeError("Could not cleanly close Qdrant Edge shards") from errors[0]
