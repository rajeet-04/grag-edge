"""Offline acceptance: /v1/chat/completions answers from local Qdrant Edge memory."""
import json

import pytest
from fastapi.testclient import TestClient

from app.edge.memory.models import CreateMemory
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime
from app.llm.ollama_client import OllamaClient

SEED = "Pump P-41 bearing temperature is above normal"


class Embeddings:
    def _vec(self, text):
        return [1.0, 0.0, 0.0, 0.0] if "pump" in text.lower() else [0.0, 1.0, 0.0, 0.0]

    async def embed_text(self, text):
        return self._vec(text)

    async def embed_with_context(self, text, task_type):
        return self._vec(text)


@pytest.fixture
def offline(monkeypatch, tmp_path, request):
    import app.database.neo4j_client as neo4j_module
    import app.edge.runtime as runtime_module
    import app.schemas.graph_schema as graph_module
    from app.main import app

    for key in ("OLLAMA_CLOUD_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "QDRANT_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def new_runtime():
        store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
        store.open()
        # Qdrant Server URL is unreachable: no listener on this port.
        rt = EdgeRuntime(store, Embeddings(), state_path=tmp_path / "state.db")
        return rt

    monkeypatch.setattr(runtime_module, "EdgeRuntime", new_runtime)

    class DownNeo4j:
        async def verify_connectivity(self):
            return False

        async def execute(self, *a, **k):
            raise ConnectionError("neo4j unavailable")

        async def close(self):
            pass

    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: DownNeo4j())

    async def no_init():
        return {}

    monkeypatch.setattr(graph_module, "init_graph_schema", no_init)

    clients, prompts = [], []
    real_init = OllamaClient.__init__

    def init(self, *a, **k):
        clients.append(k.get("use_cloud", a[3] if len(a) > 3 else False))
        real_init(self, *a, **k)

    monkeypatch.setattr(OllamaClient, "__init__", init)

    async def chat(self, messages, **kw):
        prompts.append(messages[-1]["content"])
        text = messages[-1]["content"]
        if "Cypher" in messages[0]["content"]:
            return {"content": "MATCH (e:Entity) RETURN e LIMIT 5"}
        if "query analysis" in messages[0]["content"]:
            return {"content": json.dumps({"intent": "pump temperature", "temporal_filters": {}, "entity_types": []})}
        return {"content": "## Natural Language Answer\nPump P-41 is running hot.\n\n## Step-by-Step Reasoning Path\n- a → b\n\n## Mermaid\n```mermaid\ngraph TD\nA-->B\n```"}

    async def chat_stream(self, messages, **kw):
        prompts.append(messages[-1]["content"])
        yield "Pump P-41 "
        yield "is hot."

    monkeypatch.setattr(OllamaClient, "chat", chat)
    monkeypatch.setattr(OllamaClient, "chat_stream", chat_stream)

    with TestClient(app) as client:
        rt = app.state.edge_runtime
        import asyncio

        if not request.node.get_closest_marker("empty_memory"):
            asyncio.new_event_loop().run_until_complete(
                rt.memories.create(CreateMemory(content=SEED, device_id="robot-7", source_type="sensor", source_id="t-1"))
            )
        yield client, prompts, clients


def test_non_streaming_answer_uses_local_edge_memory(offline):
    client, prompts, clients = offline
    r = client.post("/v1/chat/completions", json={"model": "grag-pipeline-v1",
                    "messages": [{"role": "user", "content": "which pump is overheating?"}]})
    assert r.status_code == 200, r.text
    assert "Pump P-41 is running hot" in r.json()["choices"][0]["message"]["content"]
    final = prompts[-1]
    assert "[LOCAL" in final and SEED in final and "robot-7" in final
    assert clients and not any(clients)


def test_streaming_answer_uses_local_edge_memory(offline):
    client, prompts, clients = offline
    r = client.post("/v1/chat/completions", json={"model": "grag-pipeline-v1", "stream": True,
                    "messages": [{"role": "user", "content": "which pump is overheating?"}]})
    assert r.status_code == 200
    assert "is hot." in r.text
    assert "[LOCAL" in prompts[-1] and SEED in prompts[-1]
    assert clients and not any(clients)


@pytest.mark.empty_memory
def test_empty_edge_memory_is_grounded_not_fabricated(offline):
    client, prompts, _ = offline
    client.post("/v1/chat/completions", json={"model": "grag-pipeline-v1",
                "messages": [{"role": "user", "content": "what is the weather"}]})
    assert "No relevant local memory" in prompts[-1] and SEED not in prompts[-1]
