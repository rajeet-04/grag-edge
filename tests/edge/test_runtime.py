from app.edge.runtime import EdgeRuntime


class Store:
    def __init__(self): self.closed = 0
    def close(self): self.closed += 1
    def list_points(self): return []
    def retrieve(self, _): return None
    def upsert(self, _): pass
    def embed_bm25_document(self, _): return {"indices": [1], "values": [1.0]}
    def embed_bm25_query(self, _): return {"indices": [1], "values": [1.0]}
    def query_dense(self, *_): return []
    def query_sparse(self, *_): return []


def test_runtime_owns_one_store_and_closes_it():
    store = Store()
    runtime = EdgeRuntime(store=store)
    assert runtime.memories.store is store
    assert runtime.search is not None
    import asyncio
    asyncio.run(runtime.close())
    assert store.closed == 1
