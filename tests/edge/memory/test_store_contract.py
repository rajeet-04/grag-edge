from pathlib import Path

import pytest

from app.config import Settings
from app.edge.memory.store import EdgeMemoryStore, StoredPoint


def test_settings_use_qdrant_edge_defaults_and_environment(monkeypatch):
    monkeypatch.delenv("QDRANT_EDGE_PATH", raising=False)
    monkeypatch.delenv("EDGE_EMBEDDING_DIMENSION", raising=False)
    settings = Settings()
    assert settings.qdrant_edge_path == Path("./data/qdrant-edge")
    assert settings.embedding_dimension == 768

    monkeypatch.setenv("QDRANT_EDGE_PATH", "/tmp/edge")
    monkeypatch.setenv("EDGE_EMBEDDING_DIMENSION", "4")
    settings = Settings()
    assert settings.qdrant_edge_path == Path("/tmp/edge")
    assert settings.embedding_dimension == 4


def test_stored_point_preserves_application_owned_values():
    point = StoredPoint(id="memory-1", dense=[0.1, 0.2], sparse=None, payload={"text": "hello"})
    assert point.id == "memory-1"
    assert point.dense == [0.1, 0.2]
    assert point.sparse is None
    assert point.payload == {"text": "hello"}


def test_store_protocol_has_expected_operations():
    assert {"upsert", "retrieve", "close"} <= set(EdgeMemoryStore.__protocol_attrs__)
