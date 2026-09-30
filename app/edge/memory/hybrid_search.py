"""Offline dense, keyword, and reciprocal-rank-fused memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Protocol

from app.edge.memory.bm25 import EdgeBm25Indexer
from app.edge.memory.dedupe import dedupe_hits
from app.edge.memory.store import MemoryOrigin, RawSearchHit, SearchableEdgeMemoryStore
from app.llm.embedding import get_embedding_service


class SearchMode(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class MemoryHit:
    point_id: str
    score: float
    origin: MemoryOrigin
    dense_score: float | None
    sparse_score: float | None
    payload: dict[str, Any]


class _EmbeddingService(Protocol):
    async def embed_text(self, text: str) -> list[float]: ...


class HybridSearchService:
    """Coordinate local-only vector searches and deterministic result fusion."""

    RRF_K = 60

    def __init__(
        self,
        store: SearchableEdgeMemoryStore,
        embedding_service: _EmbeddingService | None = None,
        state_db: Any | None = None,
    ) -> None:
        self._store = store
        self._embedding_service = embedding_service or get_embedding_service()
        self._bm25 = EdgeBm25Indexer(store)
        self._state_db = state_db

    def _confirmed_hits(self, hits: list[MemoryHit]) -> list[MemoryHit]:
        if self._state_db is None:
            return hits
        with self._state_db._lock:
            rows = self._state_db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%'"
            ).fetchall()
        confirmed: dict[tuple[str, str, int, str], str] = {}
        for row in rows:
            try:
                run = json.loads(row["value"])
                if run.get("status") != "SYNCHRONIZED":
                    continue
                timestamp = run["updated_at"]
                for entry in run.get("acknowledged", []):
                    key = (entry["memory_id"], entry["logical_id"], int(entry["revision"]), entry["content_hash"])
                    confirmed[key] = max(timestamp, confirmed.get(key, timestamp))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        result = []
        for hit in hits:
            if hit.origin is not MemoryOrigin.FLEET:
                result.append(hit)
                continue
            payload = hit.payload
            key = (payload.get("memory_id", hit.point_id), payload.get("logical_id"),
                   int(payload.get("revision", 0)), payload.get("content_hash"))
            timestamp = confirmed.get(key)
            if timestamp is not None and not payload.get("sync_timestamp"):
                hit = MemoryHit(hit.point_id, hit.score, hit.origin, hit.dense_score, hit.sparse_score,
                                {**payload, "sync_timestamp": timestamp})
            result.append(hit)
        return result

    def _visibility(self) -> tuple[set[str] | None, int]:
        list_local = getattr(self._store, "list_points", None)
        if list_local is None:
            return None, 0
        points = list_local()
        list_fleet = getattr(self._store, "list_fleet_points", None)
        if list_fleet is not None:
            points.extend(list_fleet())
        latest_revision: dict[str, int] = {}
        for point in points:
            payload = point.payload
            if payload.get("record_type") != "memory":
                continue
            logical_id = payload.get("logical_id")
            latest_revision[logical_id] = max(latest_revision.get(logical_id, 0), int(payload.get("revision", 0)))
        visible = {
            point.payload.get("memory_id", point.id)
            for point in points
            if point.payload.get("record_type") != "memory"
            or (int(point.payload.get("revision", 0)) == latest_revision.get(point.payload.get("logical_id"))
                and not point.payload.get("is_deleted"))
        }
        return visible, len(points)

    @staticmethod
    def _visible_hits(hits: list[RawSearchHit], visible_ids: set[str] | None) -> list[RawSearchHit]:
        if visible_ids is None:
            return hits
        return [hit for hit in hits if hit.payload.get("record_type") != "memory" or hit.payload.get("memory_id", hit.point_id) in visible_ids]

    async def search(
        self, query: str, mode: SearchMode, limit: int = 10
    ) -> list[MemoryHit]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = query.strip()
        origins = (MemoryOrigin.LOCAL, MemoryOrigin.FLEET)
        visible_ids, total_points = self._visibility()
        candidate_limit = max(limit, total_points)

        if mode is SearchMode.SEMANTIC:
            vector = await self._embedding_service.embed_text(query)
            hits = [
                hit
                for origin in origins
                for hit in self._store.query_dense(vector, candidate_limit, origin)
            ]
            hits = self._visible_hits(hits, visible_ids)
            return dedupe_hits(self._confirmed_hits([
                MemoryHit(hit.point_id, hit.score, hit.origin, hit.score, None, hit.payload)
                for hit in self._ranked_unique(hits)
            ]))[:limit]

        if mode is SearchMode.KEYWORD:
            vector = self._bm25.embed_query(query)
            hits = [
                hit
                for origin in origins
                for hit in self._store.query_sparse(vector, candidate_limit, origin)
            ]
            hits = self._visible_hits(hits, visible_ids)
            return dedupe_hits(self._confirmed_hits([
                MemoryHit(hit.point_id, hit.score, hit.origin, None, hit.score, hit.payload)
                for hit in self._ranked_unique(hits)
            ]))[:limit]

        if mode is not SearchMode.HYBRID:
            raise ValueError(f"unsupported search mode: {mode!r}")

        dense_vector = await self._embedding_service.embed_text(query)
        sparse_vector = self._bm25.embed_query(query)
        dense_hits = self._ranked_unique(
            [
                hit
                for origin in origins
                for hit in self._store.query_dense(dense_vector, candidate_limit, origin)
            ]
        )
        dense_hits = self._ranked_unique(self._visible_hits(dense_hits, visible_ids))
        sparse_hits = self._ranked_unique(
            [
                hit
                for origin in origins
                for hit in self._store.query_sparse(sparse_vector, candidate_limit, origin)
            ]
        )
        sparse_hits = self._ranked_unique(self._visible_hits(sparse_hits, visible_ids))
        return dedupe_hits(self._confirmed_hits(self._fuse(dense_hits, sparse_hits)))[:limit]

    @staticmethod
    def _ranked_unique(hits: list[RawSearchHit]) -> list[RawSearchHit]:
        """Deduplicate by point ID, choosing best score and preferring LOCAL ties."""
        unique: dict[tuple[MemoryOrigin, str], RawSearchHit] = {}
        for hit in hits:
            key = (hit.origin, hit.point_id)
            current = unique.get(key)
            if current is None or hit.score > current.score or (
                hit.score == current.score
                and hit.origin is MemoryOrigin.LOCAL
                and current.origin is MemoryOrigin.FLEET
            ):
                unique[key] = hit
        return sorted(unique.values(), key=lambda hit: (-hit.score, hit.point_id))

    @classmethod
    def _fuse(
        cls, dense_hits: list[RawSearchHit], sparse_hits: list[RawSearchHit]
    ) -> list[MemoryHit]:
        by_id: dict[tuple[MemoryOrigin, str], dict[str, Any]] = {}
        for modality, hits in (("dense", dense_hits), ("sparse", sparse_hits)):
            for rank, hit in enumerate(hits, start=1):
                key = (hit.origin, hit.point_id)
                item = by_id.setdefault(
                    key,
                    {
                        "origin": hit.origin,
                        "payload": hit.payload,
                        "dense_score": None,
                        "sparse_score": None,
                        "score": 0.0,
                    },
                )
                if hit.origin is MemoryOrigin.LOCAL:
                    item["origin"] = MemoryOrigin.LOCAL
                    item["payload"] = hit.payload
                item[f"{modality}_score"] = hit.score
                item["score"] += 1.0 / (cls.RRF_K + rank)
        results = [MemoryHit(point_id=point_id, **item) for (_, point_id), item in by_id.items()]
        return sorted(results, key=lambda hit: (-hit.score, hit.point_id))
