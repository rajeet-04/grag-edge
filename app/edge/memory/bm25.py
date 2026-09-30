"""Offline BM25 embedding through the Qdrant Edge adapter."""

from __future__ import annotations

from typing import Any, Protocol


class _Bm25Adapter(Protocol):
    def embed_bm25_document(self, text: str) -> Any: ...
    def embed_bm25_query(self, text: str) -> Any: ...


class EdgeBm25Indexer:
    """Generate local sparse vectors without exposing Qdrant types here."""

    def __init__(self, adapter: _Bm25Adapter) -> None:
        self._adapter = adapter

    def embed_document(self, text: str) -> Any:
        return self._adapter.embed_bm25_document(text)

    def embed_query(self, text: str) -> Any:
        return self._adapter.embed_bm25_query(text)
