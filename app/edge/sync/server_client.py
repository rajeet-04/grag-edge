"""Qdrant Server boundary for idempotent fleet uploads."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from qdrant_client import QdrantClient, models

from app.edge.memory.store import StoredPoint


class CloudHealth(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class QdrantServerClient:
    def __init__(self, url: str, collection: str = "grag_fleet_memory", api_key: str | None = None, client: Any | None = None, timeout: float = 2.0):
        self.collection = collection
        self.timeout = timeout
        self.client = client or QdrantClient(url=url, api_key=api_key, timeout=timeout)

    def health(self) -> CloudHealth:
        try:
            self.client.get_collections()
            return CloudHealth.ONLINE
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if (status is not None and 400 <= status < 500) or "401" in str(exc) or "403" in str(exc) or "unauthorized" in str(exc).lower():
                return CloudHealth.ERROR
            return CloudHealth.OFFLINE

    def ensure_collection(self, embedding_dimension: int = 768) -> None:
        if embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        if self.client.collection_exists(self.collection):
            return
        try:
            self.client.create_collection(
                collection_name=self.collection,
                shard_number=1,
                vectors_config={"dense": models.VectorParams(size=embedding_dimension, distance=models.Distance.COSINE)},
                sparse_vectors_config={"text": models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        except Exception:
            # Creation can race another API replica; only suppress if it now exists.
            if not self.client.collection_exists(self.collection):
                raise

    def upsert_point(self, point: StoredPoint):
        vector: dict[str, Any] = {"dense": point.dense}
        if point.sparse is not None:
            sparse = point.sparse
            if isinstance(sparse, dict):
                sparse = models.SparseVector(indices=sparse["indices"], values=sparse["values"])
            vector["text"] = sparse
        result = self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(id=point.id, vector=vector, payload=point.payload)],
            wait=True,
        )
        return result

    def close(self) -> None:
        self.client.close()
