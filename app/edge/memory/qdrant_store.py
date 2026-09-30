"""Persistent Qdrant Edge adapter for application-owned memory points."""

from __future__ import annotations

from pathlib import Path
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
import shutil
import threading
from uuid import uuid4
from typing import Any
from uuid import UUID

from qdrant_edge import (
    Bm25,
    Bm25Config,
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeSparseVectorParams,
    EdgeVectorParams,
    Modifier,
    Point,
    Query,
    SearchRequest,
    SparseVector,
    ScrollRequest,
    UpdateOperation,
)

from app.edge.memory.store import (
    EdgeMemoryStore,
    MemoryOrigin,
    RawSearchHit,
    StoredPoint,
)


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
        self._fleet_lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._fleet_metadata: dict[str, Any] | None = None
        self._fleet_active_path = self.fleet_path
        self._bm25 = Bm25(Bm25Config(language="english"))

    def open(self) -> None:
        """Load persisted shards or create them at previously unused paths."""
        if self._local is not None or self._fleet is not None:
            raise RuntimeError("Qdrant Edge store is already open")
        config = EdgeConfig(
            vectors={"dense": EdgeVectorParams(self.embedding_dimension, Distance.Cosine)},
            sparse_vectors={"text": EdgeSparseVectorParams(modifier=Modifier.Idf)},
        )
        self._config = config
        self._local = self._open_shard(self.local_path, config)
        try:
            metadata = self._read_fleet_pointer()
            if metadata:
                self._fleet_active_path = self._generation_path(metadata)
                try:
                    self._fleet = EdgeShard.load(str(self._fleet_active_path), config)
                    self._validate_fleet(self._fleet)
                except Exception:
                    if self._fleet:
                        self._fleet.close()
                        self._fleet = None
                    previous = self._read_json(self._previous_pointer)
                    if not previous or previous == metadata:
                        raise RuntimeError("Committed fleet generation cannot be opened")
                    metadata = previous
                    self._fleet_active_path = self._generation_path(metadata)
                    self._fleet = EdgeShard.load(str(self._fleet_active_path), config)
                    self._validate_fleet(self._fleet)
                    self._write_pointer(self._pointer, metadata)
                self._fleet_metadata = metadata
            else:
                self._fleet = self._open_shard(self.fleet_path, config)
        except Exception as exc:
            if not isinstance(exc, RuntimeError) or "empty or corrupt" not in str(exc):
                self._local.close()
                self._local = None
                raise
            # Fleet data is optional for local-only retrieval; callers can still
            # query the mutable shard while the fleet shard is repaired.
            self._fleet = None

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

    def _require_open(self) -> EdgeShard:
        if self._local is None:
            raise RuntimeError("Qdrant Edge store is not open; call open() first")
        return self._local

    def _shard_for_origin(self, origin: MemoryOrigin) -> EdgeShard | None:
        local = self._require_open()
        return local if origin is MemoryOrigin.LOCAL else self._fleet

    def embed_bm25_document(self, text: str) -> SparseVector:
        return self._bm25.embed_document(text)

    def embed_bm25_query(self, text: str) -> SparseVector:
        return self._bm25.embed_query(text)

    def query_dense(
        self, vector: list[float], limit: int, origin: MemoryOrigin
    ) -> list[RawSearchHit]:
        if len(vector) != self.embedding_dimension:
            raise ValueError(
                f"dense vector dimension {len(vector)} does not match "
                f"configured embedding dimension {self.embedding_dimension}"
            )
        return self._query(vector, "dense", limit, origin)

    def query_sparse(
        self, vector: Any, limit: int, origin: MemoryOrigin
    ) -> list[RawSearchHit]:
        sparse = self._sparse_value(vector)
        if sparse is None:
            raise ValueError("sparse query vector must not be empty")
        return self._query(sparse, "text", limit, origin)

    def _query(
        self, vector: Any, using: str, limit: int, origin: MemoryOrigin
    ) -> list[RawSearchHit]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._fleet_lock if origin is MemoryOrigin.FLEET else nullcontext():
            shard = self._shard_for_origin(origin)
            if shard is None:
                return []
            try:
                points = shard.search(
                    SearchRequest(
                        query=Query.Nearest(vector, using=using),
                        limit=limit,
                        with_payload=True,
                    )
                )
            except Exception as exc:
                raise RuntimeError(f"Qdrant Edge {using} query failed for {origin.value}") from exc
            return [
                RawSearchHit(
                    point_id=str(point.id),
                    score=float(point.score),
                    origin=origin,
                    payload=dict(point.payload or {}),
                )
                for point in points
            ]

    def upsert_local(self, point: StoredPoint) -> None:
        local = self._require_open()
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
        local = self._require_open()
        return self._retrieve(local, point_id)

    def retrieve_fleet(self, point_id: str) -> StoredPoint | None:
        self._require_open()
        with self._fleet_lock:
            if self._fleet is None:
                return None
            return self._retrieve(self._fleet, point_id)

    def list_points(self) -> list[StoredPoint]:
        return self._list_shard(self._require_open())

    def list_fleet_points(self) -> list[StoredPoint]:
        self._require_open()
        with self._fleet_lock:
            return [] if self._fleet is None else self._list_shard(self._fleet)

    @classmethod
    def _list_shard(cls, shard: EdgeShard) -> list[StoredPoint]:
        result: list[StoredPoint] = []
        offset = None
        while True:
            records, offset = shard.scroll(ScrollRequest(offset=offset, limit=256, with_payload=True, with_vector=True))
            for record in records:
                vectors = record.vector or {}
                dense = vectors.get("dense", []) if isinstance(vectors, dict) else vectors
                sparse = vectors.get("text") if isinstance(vectors, dict) else None
                if isinstance(sparse, SparseVector):
                    sparse = {"indices": list(sparse.indices), "values": list(sparse.values)}
                result.append(StoredPoint(str(record.id), list(dense), sparse, dict(record.payload or {})))
            if offset is None:
                return result

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

    @property
    def _pointer(self) -> Path:
        return self.fleet_path.with_name(self.fleet_path.name + "-current.json")

    @property
    def _previous_pointer(self) -> Path:
        return self.fleet_path.with_name(self.fleet_path.name + "-previous.json")

    @property
    def _generations(self) -> Path:
        return self.fleet_path.with_name(self.fleet_path.name + "-generations")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _generation_path(self, metadata: dict[str, Any]) -> Path:
        generation = metadata["generation"]
        if not isinstance(generation, str) or str(UUID(generation)) != generation:
            raise ValueError("Invalid fleet generation identifier")
        return self._generations / generation

    def _validate_pointer_metadata(self, metadata: dict[str, Any]) -> None:
        self._generation_path(metadata)
        if str(UUID(metadata["refresh_id"])) != metadata["refresh_id"]:
            raise ValueError("Invalid refresh identifier")
        timestamp = datetime.fromisoformat(metadata["timestamp"])
        if timestamp.tzinfo is None or metadata["kind"] not in {"full", "partial"}:
            raise ValueError("Invalid fleet publication metadata")

    def _read_fleet_pointer(self) -> dict[str, Any] | None:
        try:
            metadata = self._read_json(self._pointer)
            if metadata:
                self._validate_pointer_metadata(metadata)
                return metadata
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        previous = self._read_json(self._previous_pointer)
        if previous:
            self._validate_pointer_metadata(previous)
            self._write_pointer(self._pointer, previous)
            return previous
        if self._pointer.exists():
            raise RuntimeError("Fleet generation pointer is corrupt and has no recovery metadata")
        return None

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _write_pointer(cls, path: Path, metadata: dict[str, Any]) -> None:
        temporary = path.with_name(path.name + ".tmp-" + str(uuid4()))
        try:
            with temporary.open("w") as file:
                json.dump(metadata, file, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def fleet_snapshot_metadata(self) -> dict[str, Any] | None:
        with self._fleet_lock:
            return dict(self._fleet_metadata) if self._fleet_metadata else None

    def _validate_fleet(self, shard: EdgeShard) -> None:
        from app.edge.memory.models import MemoryRecord
        for point in self._list_shard(shard):
            if len(point.dense) != self.embedding_dimension:
                raise ValueError("Fleet snapshot has incompatible dense vectors")
            if point.payload.get("record_type") != "memory":
                raise ValueError("Fleet snapshot contains a non-memory payload")
            record = MemoryRecord.model_validate(point.payload)
            if record.memory_id != point.id:
                raise ValueError("Fleet snapshot point/payload identity mismatch")
        # Both indexes must be usable even for an empty snapshot.
        shard.search(SearchRequest(query=Query.Nearest([1.0] * self.embedding_dimension, using="dense"), limit=1))
        shard.search(SearchRequest(query=Query.Nearest(SparseVector(indices=[1], values=[1.0]), using="text"), limit=1))

    def _publish_generation(self, path: Path, shard: EdgeShard, kind: str) -> None:
        shard.flush()
        # Native flush persists index state; fsync all generation files before pointer publication.
        for entry in path.rglob("*"):
            if entry.is_file():
                with entry.open("rb") as file:
                    os.fsync(file.fileno())
        self._fsync_directory(path)
        self._fsync_directory(path.parent)
        metadata = {"generation": path.name, "refresh_id": str(uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(), "kind": kind}
        with self._fleet_lock:
            previous = self._fleet_metadata
            # First bootstrap also needs a committed recovery reference; orphan
            # stages without either pointer remain ignored on startup.
            self._write_pointer(self._previous_pointer, previous or metadata)
            self._write_pointer(self._pointer, metadata)
            old = self._fleet
            self._fleet = shard
            self._fleet_active_path = path
            self._fleet_metadata = metadata
            if old:
                try:
                    old.close()
                except Exception:
                    # This immutable old generation is retained for recovery; a
                    # retirement error cannot undo a committed publication.
                    pass

    def replace_fleet_from_snapshot(self, snapshot_path: Path) -> None:
        self._require_open()
        with self._refresh_lock:
            self._generations.mkdir(parents=True, exist_ok=True)
            stage = self._generations / str(uuid4())
            stage.mkdir()
            shard = None
            published = False
            try:
                EdgeShard.unpack_snapshot(str(snapshot_path), str(stage))
                shard = EdgeShard.load(str(stage), self._config)
                self._validate_fleet(shard)
                self._publish_generation(stage, shard, "full")
                published = True
            finally:
                if not published:
                    pointers = [self._read_json(self._pointer), self._read_json(self._previous_pointer)]
                    if any(pointer and pointer.get("generation") == stage.name for pointer in pointers):
                        # The pointer may have been replaced before a directory fsync
                        # failed. Retain this validated target for restart recovery.
                        if shard:
                            try:
                                shard.close()
                            except Exception:
                                pass
                        continue_cleanup = False
                    else:
                        continue_cleanup = True
                    if shard and continue_cleanup:
                        try:
                            shard.close()
                        except Exception:
                            pass
                    if continue_cleanup:
                        shutil.rmtree(stage, ignore_errors=True)

    def fleet_manifest(self) -> dict[str, Any]:
        self._require_open()
        with self._fleet_lock:
            if self._fleet is None:
                raise RuntimeError("No valid fleet shard is available")
            return self._fleet.snapshot_manifest()

    def fleet_snapshot_base(self) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Capture the opaque manifest and its generation under one reader lock."""
        with self._fleet_lock:
            return self.fleet_manifest(), self.fleet_snapshot_metadata()

    def stage_and_apply_fleet_snapshot(self, snapshot_path: Path, expected_generation: str | None = None) -> None:
        self._require_open()
        with self._refresh_lock:
            if expected_generation is not None and (self._fleet_metadata or {}).get("generation") != expected_generation:
                raise RuntimeError("Fleet snapshot base generation changed during download")
            self._generations.mkdir(parents=True, exist_ok=True)
            stage = self._generations / str(uuid4())
            shard = None
            published = False
            try:
                with self._fleet_lock:
                    if self._fleet is None:
                        raise RuntimeError("No valid fleet shard is available")
                    # Close only while copying a stable immutable base; local writes do not take this lock.
                    self._fleet.flush()
                    self._fleet.close()
                    self._fleet = None
                    try:
                        shutil.copytree(self._fleet_active_path, stage)
                    finally:
                        self._fleet = EdgeShard.load(str(self._fleet_active_path), self._config)
                shard = EdgeShard.load(str(stage), self._config)
                shard.update_from_snapshot(str(snapshot_path))
                shard.flush()
                shard.close()
                shard = EdgeShard.load(str(stage), self._config)
                self._validate_fleet(shard)
                self._publish_generation(stage, shard, "partial")
                published = True
            finally:
                if not published:
                    pointers = [self._read_json(self._pointer), self._read_json(self._previous_pointer)]
                    if any(pointer and pointer.get("generation") == stage.name for pointer in pointers):
                        # The pointer may have been replaced before a directory fsync
                        # failed. Retain this validated target for restart recovery.
                        if shard:
                            try:
                                shard.close()
                            except Exception:
                                pass
                        continue_cleanup = False
                    else:
                        continue_cleanup = True
                    if shard and continue_cleanup:
                        try:
                            shard.close()
                        except Exception:
                            pass
                    if continue_cleanup:
                        shutil.rmtree(stage, ignore_errors=True)

    def close(self) -> None:
        """Flush and close both shards; safe to call repeatedly."""
        with self._refresh_lock, self._fleet_lock:
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
