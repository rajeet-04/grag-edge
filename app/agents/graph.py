"""LangGraph agent graph for the GRAG AI system.

Agent Graph Topology:
  1. Ingestion Agent (optional — for document ingestion)
  2. Graph Builder Agent (optional — writes ingested data to Neo4j)
  3. Query Agent → extracts intent + generates Cypher
  4. Parallel KR (Neo4j, optional) + Qdrant Edge memory search
  5. Context Builder → merges with token budget enforcement
  6. Explanation Agent → generates xAI output with Mermaid

Flow (document ingestion):
  START → Ingestion → Graph Builder → Query Agent → [KR Search | Edge Memory Search] → Context Builder → Explanation → END

Flow (query mode):
  START → Ingestion (skip) → Query Agent → [KR Search | Edge Memory Search] → Context Builder → Explanation → END
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.state import GraphState

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Real agent node imports
# ---------------------------------------------------------------------------

from app.agents.context_builder import context_builder_node  # noqa: F401
from app.agents.explanation_agent import explanation_agent_node  # noqa: F401
from app.agents.graph_builder import graph_builder_agent_node  # noqa: F401
from app.agents.ingestion_agent import ingestion_agent_node  # noqa: F401
from app.agents.query_agent import query_agent_node  # noqa: F401
from app.retrieval.fallback import check_fallback_trigger
from app.schemas.retrieval import RetrievalConfig

# ---------------------------------------------------------------------------
# Parallel search node implementations
# ---------------------------------------------------------------------------


async def kr_search_node(state: GraphState) -> dict[str, Any]:
    """KR Search: Neo4j graph traversal with vector fallback.

    Flow:
    1. Execute LLM-generated Cypher query
    2. BFS validation + depth cap (handled by Neo4jClient)
    3. Check multi-signal fallback trigger
    4. Weak graph result: edge memory (always run) supplies the vector evidence
    5. Return unified results to state
    """
    config = RetrievalConfig()
    cypher = state.get("cypher_query", "")
    user_query = state.get("user_query", "")
    intent_is_ambiguous = state.get("intent_is_ambiguous", False)

    if not cypher:
        logger.info("kr_search.no_cypher", reason="skipping KR search")
        return {
            "agent_trace": state.get("agent_trace", [])
            + ["KRSearch: no cypher, skipped"]
        }

    try:
        from app.database.neo4j_client import get_neo4j_client

        client = get_neo4j_client()
        temporal = state.get("temporal_filters", {})

        # Build query parameters from temporal filters
        params: dict[str, Any] = {}
        if temporal.get("valid_from"):
            params["temporal_valid_from"] = temporal["valid_from"]
        if temporal.get("valid_to"):
            params["temporal_valid_to"] = temporal["valid_to"]

        results = await client.execute(cypher, params)

        # Separate results into entities, relations, and paths
        kr_entities: list[dict] = []
        kr_relations: list[dict] = []
        kr_paths: list[dict] = []

        for record in results:
            if isinstance(record, dict):
                for key, value in record.items():
                    if isinstance(value, dict):
                        if "type" in value and "source" in value and "target" in value:
                            kr_relations.append(value)
                        elif "name" in value or "id" in value:
                            kr_entities.append(value)
                        else:
                            kr_paths.append(value)

        # Calculate average confidence for fallback detection
        confidences = [
            r.get("confidence", 0.0) for r in kr_entities if "confidence" in r
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        # Check multi-signal fallback trigger
        trigger = check_fallback_trigger(
            graph_results=kr_entities,
            avg_confidence=avg_confidence,
            intent_is_ambiguous=intent_is_ambiguous,
            config=config,
        )

        if trigger:
            logger.info(
                "kr_search.fallback_triggered",
                reason=trigger["reason"],
                graph_entities=len(kr_entities),
            )

            # Vector fallback is served by the always-on edge memory node.
            existing_trace = state.get("agent_trace", [])
            return {
                "kr_entities": kr_entities,
                "kr_relations": kr_relations,
                "kr_paths": kr_paths,
                "agent_trace": existing_trace
                + [
                    f"KRSearch: Cypher returned {len(kr_entities)} entities",
                    f"KRSearch: weak graph result ({trigger['reason']}); edge memory is authoritative",
                ],
            }

        # No fallback — use graph results
        logger.info(
            "kr_search.complete",
            entities=len(kr_entities),
            relations=len(kr_relations),
            paths=len(kr_paths),
        )

        existing_trace = state.get("agent_trace", [])
        return {
            "kr_entities": kr_entities,
            "kr_relations": kr_relations,
            "kr_paths": kr_paths,
            "agent_trace": existing_trace
            + [f"KRSearch: {len(kr_entities)} entities, {len(kr_relations)} relations"],
        }

    except Exception as e:
        logger.warning("kr_search.error", error=str(e))
        existing_trace = state.get("agent_trace", [])
        return {
            "kr_entities": [],
            "kr_relations": [],
            "kr_paths": [],
            "agent_trace": existing_trace
            + [f"KRSearch: degraded — {str(e)[:100]}"],
        }


EDGE_SEARCH_LIMIT = 10


async def edge_memory_search_node(state: GraphState) -> dict[str, Any]:
    """Qdrant Edge hybrid memory retrieval (authoritative offline memory).

    Local and fleet hits keep their origin/revision/device provenance. Failures
    degrade to an empty hit list so answers never depend on cloud or Neo4j.
    """
    import time
    from datetime import datetime, timezone

    from app.edge.memory.hybrid_search import SearchMode
    from app.edge.registry import get_edge_runtime

    query = (state.get("user_query") or "").strip()
    if not query:
        return {"edge_memory_hits": [], "agent_trace": ["EdgeMemory: no query, skipped"]}

    runtime = get_edge_runtime()
    if runtime is None:
        logger.warning("edge_memory_search.no_runtime")
        return {"edge_memory_hits": [], "agent_trace": ["EdgeMemory: degraded - runtime unavailable"]}

    started = time.perf_counter()
    try:
        raw = await runtime.search.search(query, SearchMode.HYBRID, EDGE_SEARCH_LIMIT)
    except Exception as exc:
        logger.warning("edge_memory_search.error", error=str(exc))
        return {"edge_memory_hits": [], "agent_trace": [f"EdgeMemory: degraded - {str(exc)[:100]}"]}
    latency_ms = round((time.perf_counter() - started) * 1000, 3)

    hits: list[dict[str, Any]] = []
    for h in raw:
        payload = h.payload
        hits.append(
            {
                "id": h.point_id,
                "memory_id": payload.get("memory_id", h.point_id),
                "logical_id": payload.get("logical_id"),
                "content": payload.get("content", ""),
                "origin": h.origin.value,
                "revision": payload.get("revision"),
                "device_id": payload.get("device_id"),
                "source_type": payload.get("source_type"),
                "source_id": payload.get("source_id"),
                "memory_type": payload.get("memory_type"),
                "timestamp": str(payload.get("updated_at") or payload.get("created_at") or ""),
                "score": h.score,
                "dense_score": h.dense_score,
                "sparse_score": h.sparse_score,
            }
        )

    counts = {"LOCAL": 0, "FLEET": 0}
    for hit in hits:
        counts[hit["origin"]] = counts.get(hit["origin"], 0) + 1
    try:
        from app.edge.state.activity import ActivityEvent

        runtime.activity.append(
            ActivityEvent(
                event_type="SEARCH_COMPLETED",
                device_id=getattr(runtime, "device_id", "unknown"),
                timestamp=datetime.now(timezone.utc),
                message=f"Edge memory search returned {len(hits)} results",
                metadata={
                    "mode": SearchMode.HYBRID.value,
                    "result_count": len(hits),
                    "origin_counts": counts,
                    "latency_ms": latency_ms,
                },
            )
        )
    except Exception as exc:  # activity log must never block answering
        logger.warning("edge_memory_search.activity_failed", error=str(exc))

    return {
        "edge_memory_hits": hits,
        "agent_trace": [
            f"EdgeMemory: {len(hits)} hits (LOCAL={counts['LOCAL']}, FLEET={counts['FLEET']}) in {latency_ms}ms"
        ],
    }


# ---------------------------------------------------------------------------
# Error handling and routing
# ---------------------------------------------------------------------------


def _route_after_query(state: GraphState) -> list[str]:
    """Route after Query Agent: parallel KR + KB search, or skip to context.

    If the query agent produced a cypher_query, we fan-out to both
    KR and KB search nodes concurrently. Otherwise (e.g., simple greeting),
    skip directly to context builder.

    Both KR and edge search converge at context_builder via direct edges.
    """
    cypher = state.get("cypher_query", "")
    if cypher:
        # Edge memory always runs; Neo4j enrichment is additive
        return ["kr_search", "edge_memory_search"]
    return ["edge_memory_search"]


def _route_after_context_builder(state: GraphState) -> str:
    """Route after Context Builder.

    Fail fast to error handler when any upstream error exists to avoid
    unbounded retry loops in low-memory runtime environments.
    """
    errors = state.get("errors", [])
    if errors:
        return "fail"
    return "explanation"


def _route_after_explanation(state: GraphState) -> str:
    """Route after Explanation Agent.

    Fail fast to error handler when errors are present.
    """
    errors = state.get("errors", [])
    if errors:
        return "fail"
    return END


def error_handler_node(state: GraphState) -> dict[str, Any]:
    """Error handler: prepares graceful failure response.

    Implements cyclic recovery loops per CONTEXT.md Decision 5.
    The error handler collects all accumulated errors and produces
    a user-friendly failure message.
    """
    retry = state.get("retry_count", 0) + 1
    existing_trace = state.get("agent_trace", [])
    error_list = state.get("errors", [])

    return {
        "answer": "I encountered an issue processing your request. Please try again.",
        "errors": error_list,
        "retry_count": retry,
        "agent_trace": existing_trace
        + [f"ERROR: max retries exceeded ({len(error_list)} errors collected)"],
    }


# ---------------------------------------------------------------------------
# Ingestion routing
# ---------------------------------------------------------------------------


def _route_after_ingestion(state: GraphState) -> str:
    """Route after Ingestion Agent.

    If entities were extracted, proceed to Graph Builder to persist them.
    Otherwise (query mode or empty ingestion), skip directly to Query Agent.
    """
    entities = state.get("entities", [])
    if entities:
        return "graph_builder"
    return "query_agent"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:
    """Build the StateGraph with all agent nodes and edges.

    Topology (document ingestion mode):
      START → ingestion → graph_builder → query_agent
        → [kr_search, edge_memory_search] (parallel) → context_builder → explanation → END

    Topology (query mode — ingestion returns no entities):
      START → ingestion → query_agent
        → [kr_search, edge_memory_search] (parallel) → context_builder → explanation → END

    Error handling (cyclic recovery per CONTEXT.md Decision 5):
      - context_builder → retry on error (max 3 retries)
      - explanation → retry on error (max 3 retries)
      - error_handler → graceful failure END

    Parallel search (CONTEXT.md Decision 6):
      - Query Agent fans out to KR (Neo4j) and Qdrant Edge memory simultaneously
      - Both converge at Context Builder via direct edges
      - I/O bound, no VRAM contention
    """
    graph = StateGraph(GraphState)

    # ── Add nodes ──────────────────────────────────────────────
    graph.add_node("ingestion", ingestion_agent_node)
    graph.add_node("graph_builder", graph_builder_agent_node)
    graph.add_node("query_agent", query_agent_node)
    graph.add_node("kr_search", kr_search_node)
    graph.add_node("edge_memory_search", edge_memory_search_node)
    graph.add_node("context_builder", context_builder_node)
    graph.add_node("explanation", explanation_agent_node)
    graph.add_node("error_handler", error_handler_node)

    # ── Entry edge ─────────────────────────────────────────────
    graph.add_edge(START, "ingestion")

    # ── Ingestion → conditional routing ────────────────────────
    # If ingestion produced entities → Graph Builder
    # If no ingestion text (query mode) → skip to Query Agent
    graph.add_conditional_edges(
        "ingestion",
        _route_after_ingestion,
        ["graph_builder", "query_agent"],
    )

    # ── Graph Builder → Query Agent ────────────────────────────
    graph.add_edge("graph_builder", "query_agent")

    # ── Query Agent → conditional fan-out ──────────────────────
    # Edge memory always; KR when Cypher exists
    graph.add_conditional_edges(
        "query_agent",
        _route_after_query,
        ["kr_search", "edge_memory_search"],
    )

    # ── Parallel retrieval → Context Builder ───────────────────
    # Both KR and KB converge at context_builder (LangGraph parallelism)
    graph.add_edge("kr_search", "context_builder")
    graph.add_edge("edge_memory_search", "context_builder")

    # ── Context Builder → Explanation or retry ─────────────────
    # Cyclic recovery: retry on error, fail gracefully after MAX_RETRIES
    graph.add_conditional_edges(
        "context_builder",
        _route_after_context_builder,
        {
            "explanation": "explanation",
            "retry": "context_builder",
            "fail": "error_handler",
        },
    )

    # ── Explanation → END or retry ─────────────────────────────
    graph.add_conditional_edges(
        "explanation",
        _route_after_explanation,
        {
            END: END,
            "retry": "explanation",
            "fail": "error_handler",
        },
    )

    # ── Error handler → END ────────────────────────────────────
    graph.add_edge("error_handler", END)

    return graph


def create_agent_graph() -> Any:
    """Create and compile the GRAG AI agent graph.

    Returns:
        A compiled LangGraph application ready for invocation.
    """
    graph = _build_graph()
    return graph.compile()


def create_pipeline_graph() -> Any:
    """Create a graph that stops BEFORE the explanation node.

    Used by the streaming API path:
    1. Run this graph to get merged_context + kr_paths (fast, ~1-3s)
    2. Then stream the explanation directly from Ollama's streaming API
       so tokens reach Open WebUI in real time.

    Topology: START → ingestion → [graph_builder] → query_agent
              → [kr_search | edge_memory_search] → context_builder → END
    """
    graph = StateGraph(GraphState)

    graph.add_node("ingestion", ingestion_agent_node)
    graph.add_node("graph_builder", graph_builder_agent_node)
    graph.add_node("query_agent", query_agent_node)
    graph.add_node("kr_search", kr_search_node)
    graph.add_node("edge_memory_search", edge_memory_search_node)
    graph.add_node("context_builder", context_builder_node)

    graph.add_edge(START, "ingestion")
    graph.add_conditional_edges(
        "ingestion",
        _route_after_ingestion,
        ["graph_builder", "query_agent"],
    )
    graph.add_edge("graph_builder", "query_agent")
    graph.add_conditional_edges(
        "query_agent",
        _route_after_query,
        ["kr_search", "edge_memory_search"],
    )
    graph.add_edge("kr_search", "context_builder")
    graph.add_edge("edge_memory_search", "context_builder")
    graph.add_edge("context_builder", END)

    return graph.compile()
