import pytest

from app.llm.ollama_client import OllamaClient


@pytest.fixture
def created(monkeypatch):
    seen = []
    real = OllamaClient.__init__

    def init(self, *a, **k):
        seen.append(k.get("use_cloud", False))
        real(self, *a, **k)

    monkeypatch.setattr(OllamaClient, "__init__", init)
    monkeypatch.delenv("OLLAMA_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("LLM_USE_CLOUD", raising=False)
    from app.config import get_settings
    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
    return seen


def test_extractors_use_local_client(created):
    from app.ingestion.entity_extractor import EntityExtractionService
    from app.ingestion.relation_extractor import RelationExtractionService

    EntityExtractionService()
    RelationExtractionService()
    assert created == [False, False]


@pytest.mark.asyncio
async def test_query_and_explanation_and_stream_use_local_client(created, monkeypatch):
    async def chat(self, messages, **kw):
        return {"content": "{}"}

    async def chat_stream(self, messages, **kw):
        yield "x"

    monkeypatch.setattr(OllamaClient, "chat", chat)
    monkeypatch.setattr(OllamaClient, "chat_stream", chat_stream)
    from app.agents.explanation_agent import explanation_agent_node, stream_explanation
    from app.agents.query_agent import query_agent_node
    from app.agents.state import create_initial_state

    state = create_initial_state("q", "s")
    await query_agent_node(state)
    await explanation_agent_node({**state, "merged_context": "ctx"})
    assert [c async for c in stream_explanation({**state, "merged_context": "ctx"})] == ["x"]
    assert created and not any(created)


def test_cloud_is_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("LLM_USE_CLOUD", "true")
    from app.config import Settings
    assert Settings().llm_use_cloud is True
    monkeypatch.delenv("LLM_USE_CLOUD")
    assert Settings().llm_use_cloud is False
