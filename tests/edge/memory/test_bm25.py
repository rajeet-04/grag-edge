from uuid import uuid4

from app.edge.memory.bm25 import EdgeBm25Indexer
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import MemoryOrigin, StoredPoint


def test_bm25_exact_identifier_search_uses_local_sparse_vectors(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", embedding_dimension=2)
    store.open()
    indexer = EdgeBm25Indexer(store)
    documents = [
        ("Pump P-41 pressure sensor reports a rising temperature", "pump"),
        ("Conveyor C-19 belt alignment is within tolerance", "conveyor"),
    ]
    for text, label in documents:
        point = StoredPoint(
            id=str(uuid4()),
            dense=[1.0, 0.0],
            sparse=indexer.embed_document(text),
            payload={"content": text, "label": label},
        )
        store.upsert_local(point)

    hits = store.query_sparse(
        indexer.embed_query("Pump P-41"), limit=5, origin=MemoryOrigin.LOCAL
    )
    assert hits
    assert hits[0].payload["label"] == "pump"
    store.close()
