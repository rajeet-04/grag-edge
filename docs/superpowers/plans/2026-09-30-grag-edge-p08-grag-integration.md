# GRAG Edge P8 GRAG Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace GRAG’s ChromaDB production retrieval path with Qdrant Edge while preserving LangGraph reasoning, local Ollama answers, streaming, and optional Neo4j enrichment.

**Architecture:** The LangGraph query flow calls an edge retrieval node backed by `HybridSearchService`. Neo4j enrichment may run in parallel when available, but Qdrant Edge retrieval is authoritative for offline memory. ChromaDB remains only until migration tests pass, then is removed from dependencies/config/Compose.

**Tech Stack:** LangGraph, FastAPI, Qdrant Edge, Ollama, Neo4j optional, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Cloud Qdrant must be absent/unreachable in the offline reasoning acceptance test.
- Neo4j failure cannot block Qdrant Edge retrieval or local answer generation.
- The required demo path must not require `OLLAMA_CLOUD_API_KEY` or any external LLM credential; local Ollama is the default for query, extraction, context/explanation, and answer generation.
- Existing `POST /v1/chat/completions` remains compatible.
- ChromaDB production code/config/container volume is removed by phase end.
- Exit gate: GRAG answers with Qdrant Edge evidence while cloud is disconnected.

## Review Focus
- Query with no Neo4j connection must still produce an edge-memory answer.
- Empty edge memory must degrade to a grounded “no relevant local memory” path rather than fabricate evidence.
- Streaming and non-streaming chat modes must both use the new retrieval path.
- LOCAL/FLEET provenance must survive context construction.
- No import or config reference to ChromaDB may remain in the production path.

---

### Task 1: Edge retrieval node

**Files:**
- Modify: `app/agents/graph.py`
- Modify: `app/agents/state.py`
- Modify: `app/agents/context_builder.py`
- Test: `tests/agents/test_edge_retrieval.py`

**Interfaces:**
- Replace `kb_search_node` with `edge_memory_search_node(state: GraphState) -> dict[str, Any]`.
- Add state field `edge_memory_hits: list[dict[str, Any]]`.
- Each hit carries content, origin, revision, source/device provenance, and retrieval scores.
- Emit `SEARCH_COMPLETED` with query mode, result count, local/fleet origin counts, and measured retrieval latency after successful edge retrieval.

- [ ] **Step 1: Write graph-node tests**
  Assert local and fleet hits populate state, provenance reaches context builder, missing fleet data does not fail, and `SEARCH_COMPLETED` records origin counts plus retrieval latency.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement node and context mapping**
- [ ] **Step 4: Verify**
  Run agent tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: route GRAG retrieval through Qdrant Edge`

### Task 2: Offline-first orchestration and Neo4j degradation

**Files:**
- Modify: `app/agents/graph.py`
- Modify: `app/retrieval/fallback.py`
- Modify: `app/llm/ollama_client.py`
- Modify: `app/agents/query_agent.py`
- Modify: `app/agents/explanation_agent.py`
- Modify: `app/ingestion/entity_extractor.py`
- Modify: `app/ingestion/relation_extractor.py`
- Modify where applicable: `app/agents/context_builder.py`
- Test: `tests/e2e/test_edge_offline_pipeline.py`
- Test: `tests/integration/test_local_ollama_paths.py`

**Interfaces:**
- Edge retrieval always runs for query mode.
- Neo4j result is additive when available; its failure contributes a trace event but does not clear edge hits.
- Vector fallback no longer reaches ChromaDB.
- Core services instantiate local `OllamaClient(use_cloud=False)` by default; any cloud mode remains explicit opt-in only and is not used by the required demo or offline acceptance path.

- [ ] **Step 1: Write offline/local-inference E2E tests**
  With Qdrant Server and Neo4j unavailable and with all cloud API keys unset, seed local Edge memory and assert a question receives an answer whose evidence includes LOCAL memory. Assert query, entity extraction, relation extraction, explanation/context, and streaming answer paths do not instantiate `OllamaClient(use_cloud=True)` in the required local mode.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Refactor orchestration**
- [ ] **Step 4: Verify**
  Run `uv run pytest tests/e2e/test_edge_offline_pipeline.py -v`; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: make GRAG reasoning edge autonomous`

### Task 3: Remove ChromaDB production dependency

**Files:**
- Delete: `app/database/chroma_client.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `app/config.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Test: `tests/test_no_chromadb_dependency.py`

**Interfaces:**
- Production modules must not import `chromadb` or `app.database.chroma_client`.
- Compose must not declare a ChromaDB data volume.

- [ ] **Step 1: Write dependency scan test**
  Assert production Python files contain no Chroma imports and application settings no longer expose `chromadb_path`.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Remove Chroma implementation/config/dependencies and migrate any remaining memory calls**
- [ ] **Step 4: Verify**
  Run full pytest suite; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `refactor: retire ChromaDB from GRAG Edge`

**Exit gate:** `/v1/chat/completions` uses local Qdrant Edge memory while cloud Qdrant is unreachable, with Neo4j optional and ChromaDB absent.