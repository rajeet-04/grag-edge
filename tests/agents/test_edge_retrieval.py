from types import SimpleNamespace

import pytest

from app.agents.context_builder import context_builder_node
from app.agents.graph import edge_memory_search_node
from app.agents.state import create_initial_state
from app.edge import registry
from app.edge.memory.hybrid_search import MemoryHit
from app.edge.memory.store import MemoryOrigin


def hit(pid, origin, content, **extra):
    payload = {"content": content, "memory_id": pid, "logical_id": "l-" + pid, "revision": 2,
               "device_id": "robot-7", "source_type": "operator", "source_id": "op-1", **extra}
    return MemoryHit(pid, 0.03, origin, 0.9, 0.4, payload)


class FakeSearch:
    def __init__(self, hits=None, error=None):
        self.hits, self.error, self.calls = hits or [], error, []

    async def search(self, query, mode, limit=10):
        self.calls.append((query, mode, limit))
        if self.error:
            raise self.error
        return self.hits


def install(search):
    events = []
    runtime = SimpleNamespace(search=search, device_id="robot-7",
                              activity=SimpleNamespace(append=events.append))
    registry.set_edge_runtime(runtime)
    return events


@pytest.fixture(autouse=True)
def _reset():
    yield
    registry.set_edge_runtime(None)


@pytest.mark.asyncio
async def test_local_and_fleet_hits_populate_state_and_events():
    events = install(FakeSearch([hit("a", MemoryOrigin.LOCAL, "Pump P-41 is hot"),
                                 hit("b", MemoryOrigin.FLEET, "Pump P-41 seal replaced", device_id="robot-9")]))
    state = create_initial_state("which pump is hot?", "s1")
    out = await edge_memory_search_node(state)
    hits = out["edge_memory_hits"]
    assert [h["origin"] for h in hits] == ["LOCAL", "FLEET"]
    assert hits[0]["content"] == "Pump P-41 is hot" and hits[0]["revision"] == 2
    assert hits[1]["device_id"] == "robot-9" and hits[0]["dense_score"] == 0.9 and hits[0]["score"] == 0.03
    (event,) = events
    assert event.event_type == "SEARCH_COMPLETED"
    md = event.metadata
    assert md["mode"] == "hybrid" and md["result_count"] == 2
    assert md["origin_counts"] == {"LOCAL": 1, "FLEET": 1}
    assert isinstance(md["latency_ms"], float) and md["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_missing_fleet_data_does_not_fail():
    install(FakeSearch([hit("a", MemoryOrigin.LOCAL, "Only local")]))
    out = await edge_memory_search_node(create_initial_state("q", "s"))
    assert len(out["edge_memory_hits"]) == 1


@pytest.mark.asyncio
async def test_provenance_reaches_context_builder():
    install(FakeSearch([hit("a", MemoryOrigin.LOCAL, "Pump P-41 is hot"),
                        hit("b", MemoryOrigin.FLEET, "Fleet note", device_id="robot-9")]))
    state = create_initial_state("q", "s")
    state.update(await edge_memory_search_node(state))
    ctx = (await context_builder_node(state))["merged_context"]
    assert "[LOCAL" in ctx and "[FLEET" in ctx
    assert "robot-9" in ctx and "rev 2" in ctx and "Pump P-41 is hot" in ctx


@pytest.mark.asyncio
async def test_empty_edge_memory_is_grounded_no_memory_context():
    install(FakeSearch([]))
    state = create_initial_state("q", "s")
    state.update(await edge_memory_search_node(state))
    ctx = (await context_builder_node(state))["merged_context"]
    assert "No relevant local memory" in ctx


@pytest.mark.asyncio
async def test_search_failure_degrades_without_raising():
    install(FakeSearch(error=RuntimeError("store closed")))
    out = await edge_memory_search_node(create_initial_state("q", "s"))
    assert out["edge_memory_hits"] == []
    assert any("degraded" in t for t in out["agent_trace"])
