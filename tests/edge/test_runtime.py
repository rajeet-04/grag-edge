from app.edge.runtime import EdgeRuntime
import asyncio
import threading


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


def test_runtime_owns_one_store_and_closes_it(tmp_path):
    store = Store()
    runtime = EdgeRuntime(store=store, state_path=tmp_path / "state.db")
    assert runtime.memories.store is store
    assert runtime.search is not None
    asyncio.run(runtime.close())
    assert store.closed == 1


def test_runtime_close_waits_for_blocking_connectivity_probe(tmp_path):
    class BlockingRemote:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.closed = False
        def health(self):
            self.started.set()
            self.release.wait(2)
            return "OFFLINE"
        def close(self): self.closed = True

    async def run():
        remote = BlockingRemote()
        runtime = EdgeRuntime(store=Store(), state_path=tmp_path / "state.db", remote=remote)
        runtime.connectivity_interval_seconds = 30
        runtime.start_background()
        assert await asyncio.to_thread(remote.started.wait, 1)
        closing = asyncio.create_task(runtime.close())
        await asyncio.sleep(0.03)
        assert not closing.done()
        assert not remote.closed
        remote.release.set()
        await asyncio.wait_for(closing, 1)
        assert remote.closed
    asyncio.run(run())
