"""Vector fallback system for weak graph queries.

Triggers:
1. Cypher returns 0 results
2. Average graph confidence < 0.70
3. Query Agent flags intent as ambiguous

Executes:
- Qdrant Edge semantic search over LOCAL and FLEET memory
- Deduplicates results
"""

from __future__ import annotations

from typing_extensions import TypedDict

import structlog

from app.schemas.retrieval import RetrievalConfig

logger = structlog.get_logger()


class FallbackTrigger(TypedDict):
    """Why fallback was triggered."""

    reason: str  # "zero_results" | "low_confidence" | "ambiguous_intent"
    details: str


class FallbackResult(TypedDict):
    """Result from vector fallback execution."""

    results: list[dict]
    trigger: FallbackTrigger
    combined_scores: list[float]


def check_fallback_trigger(
    graph_results: list[dict],
    avg_confidence: float | None = None,
    intent_is_ambiguous: bool = False,
    config: RetrievalConfig | None = None,
) -> FallbackTrigger | None:
    """Check if graph results warrant vector fallback.

    Args:
        graph_results: Results from graph traversal (empty = trigger)
        avg_confidence: Average confidence of graph results (None = no scores)
        intent_is_ambiguous: True if Query Agent flagged ambiguous intent
        config: Retrieval configuration (uses defaults if None)

    Returns:
        FallbackTrigger if fallback needed, None if graph results are sufficient

    Decision order (first match wins):
    1. Zero results -> fallback always
    2. No confidence scores -> assume weak, fallback
    3. Low confidence (< 0.70) -> fallback
    4. Ambiguous intent -> fallback
    """
    config = config or RetrievalConfig()

    # Signal 1: Zero results
    if len(graph_results) == 0:
        return FallbackTrigger(
            reason="zero_results",
            details="Cypher query returned no results",
        )

    # Signal 2: No confidence scores
    if avg_confidence is None:
        return FallbackTrigger(
            reason="low_confidence",
            details="No confidence scores available from graph",
        )

    # Signal 3: Low confidence
    if avg_confidence < config.confidence_threshold:
        return FallbackTrigger(
            reason="low_confidence",
            details=f"Average confidence {avg_confidence:.2f} < threshold {config.confidence_threshold}",
        )

    # Signal 4: Ambiguous intent
    if intent_is_ambiguous:
        return FallbackTrigger(
            reason="ambiguous_intent",
            details="Query Agent flagged intent as ambiguous",
        )

    return None


async def execute_vector_fallback(
    query: str,
    top_k: int | None = None,
    config: RetrievalConfig | None = None,
) -> FallbackResult:
    """Execute vector fallback search against local Qdrant Edge memory.

    Runs semantic search over LOCAL and FLEET origins; no cloud services or
    external vector stores are contacted.
    """
    from app.edge.memory.hybrid_search import SearchMode
    from app.edge.registry import get_edge_runtime

    config = config or RetrievalConfig()
    top_k = top_k or config.fallback_top_k
    logger.info("fallback.executing", query=query[:50], top_k=top_k)

    runtime = get_edge_runtime()
    items: list[dict] = []
    if runtime is not None:
        try:
            hits = await runtime.search.search(query, SearchMode.SEMANTIC, top_k)
        except Exception as e:
            logger.error("fallback.edge_error", error=str(e))
            hits = []
        for hit in hits:
            items.append(
                {
                    "id": hit.point_id,
                    "type": "edge",
                    "content": hit.payload.get("content", ""),
                    "similarity": hit.dense_score if hit.dense_score is not None else hit.score,
                    "metadata": {**hit.payload, "origin": hit.origin.value},
                }
            )

    combined = merge_fallback_results(items, [])
    threshold = config.similarity_threshold
    filtered = [r for r in combined if r["similarity"] >= threshold]
    logger.info("fallback.complete", combined=len(combined), filtered=len(filtered))

    return FallbackResult(
        results=filtered,
        trigger=FallbackTrigger(
            reason="fallback_executed",
            details=f"Found {len(filtered)} results above threshold {threshold}",
        ),
        combined_scores=[r["similarity"] for r in filtered],
    )


def merge_fallback_results(
    episodic: list[dict],
    semantic: list[dict],
) -> list[dict]:
    """Merge episodic and semantic results, deduplicating by content.

    Prioritizes episodic results when same content appears in both.
    """
    seen = set()
    merged = []

    # Add episodic first (higher priority)
    for item in episodic:
        content_key = item["content"][:100]
        if content_key not in seen:
            seen.add(content_key)
            merged.append(item)

    # Add semantic (lower priority)
    for item in semantic:
        content_key = item["content"][:100]
        if content_key not in seen:
            seen.add(content_key)
            merged.append(item)

    # Sort by similarity descending
    merged.sort(key=lambda x: x["similarity"], reverse=True)

    return merged
