"""LangChain tools wrapping GRAG AI services for agent use.

Provides tools for:
- Neo4j knowledge graph search (KR layer)
- Qdrant Edge memory search (offline KB layer)
"""

import json
from datetime import datetime
from typing import Any

import structlog
from langchain_core.tools import tool

from app.database.neo4j_client import get_neo4j_client

logger = structlog.get_logger()


@tool
def neo4j_search(query: str, temporal_filters: str = "") -> str:
    """Search Neo4j knowledge graph with a Cypher query.

    Use this tool to find entities, relationships, and paths in the
    knowledge graph. Supports temporal filtering via valid_from/valid_to.

    Args:
        query: Cypher query string to execute against Neo4j
        temporal_filters: JSON string with optional 'valid_from', 'valid_to'
            ISO datetime keys. Example: '{"valid_to": "2024-01-01T00:00:00"}'

    Returns:
        JSON string of query results or error message
    """
    import asyncio

    async def _run() -> str:
        client = get_neo4j_client()
        try:
            # Parse temporal filters if provided
            filters: dict[str, Any] = {}
            if temporal_filters:
                try:
                    filters = json.loads(temporal_filters)
                except json.JSONDecodeError:
                    logger.warning(
                        "neo4j_search.invalid_temporal_filters", raw=temporal_filters
                    )

            # Inject temporal constraints into query if filters present
            final_query = query
            params: dict[str, Any] = {}

            if filters.get("valid_from"):
                params["temporal_valid_from"] = filters["valid_from"]
            if filters.get("valid_to"):
                params["temporal_valid_to"] = filters["valid_to"]

            # If the query uses temporal filter params, wrap with WHERE
            if params and "$temporal_" in final_query:
                # Query already references temporal params — pass them through
                pass
            elif params:
                # Auto-inject temporal filter into MATCH patterns
                temporal_where = []
                if "temporal_valid_from" in params:
                    temporal_where.append(
                        "r.valid_from >= datetime($temporal_valid_from)"
                    )
                if "temporal_valid_to" in params:
                    temporal_where.append(
                        "(r.valid_to IS NULL OR r.valid_to <= datetime($temporal_valid_to))"
                    )
                if temporal_where:
                    inject_point = final_query.upper().find("WHERE")
                    if inject_point == -1:
                        # No WHERE clause — add one before RETURN/ORDER/LIMIT
                        for keyword in ["RETURN", "ORDER BY", "LIMIT"]:
                            idx = final_query.upper().find(keyword)
                            if idx != -1:
                                final_query = (
                                    final_query[:idx]
                                    + f"WHERE {' AND '.join(temporal_where)}\n"
                                    + final_query[idx:]
                                )
                                break
                    else:
                        # Append to existing WHERE
                        final_query = (
                            final_query[: inject_point + 5]
                            + (" " + " AND ".join(temporal_where) + " AND ")
                            + final_query[inject_point + 5 :]
                        )

            results = await client.execute(final_query, params)
            logger.info(
                "neo4j_search.executed",
                query_preview=query[:100],
                result_count=len(results),
            )
            return json.dumps(results, default=str)

        except Exception as e:
            logger.error("neo4j_search.error", error=str(e), query=query[:200])
            return json.dumps({"error": str(e), "query": query[:200]})

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _run()).result()
    return asyncio.run(_run())


@tool
def edge_memory_search(query: str, limit: int = 5) -> str:
    """Search local Qdrant Edge memory (LOCAL and FLEET origins).

    Use this to find robot observations, procedures, incidents and operator
    notes stored offline on this device. Every result carries its origin,
    revision and source provenance.

    Args:
        query: Natural language query
        limit: Maximum number of results to return (default 5)

    Returns:
        JSON string of matching memories with provenance and scores
    """
    import asyncio

    async def _run() -> str:
        try:
            from app.edge.memory.hybrid_search import SearchMode
            from app.edge.registry import get_edge_runtime

            runtime = get_edge_runtime()
            if runtime is None:
                return json.dumps({"error": "edge runtime unavailable"})
            hits = await runtime.search.search(query, SearchMode.HYBRID, limit)
            return json.dumps(
                [
                    {
                        "id": h.point_id,
                        "content": h.payload.get("content", ""),
                        "origin": h.origin.value,
                        "revision": h.payload.get("revision"),
                        "device_id": h.payload.get("device_id"),
                        "source_type": h.payload.get("source_type"),
                        "source_id": h.payload.get("source_id"),
                        "score": h.score,
                    }
                    for h in hits
                ],
                default=str,
            )
        except Exception as e:
            logger.error("edge_memory_search.error", error=str(e))
            return json.dumps({"error": str(e)})

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _run()).result()
    return asyncio.run(_run())


AGENT_TOOLS = [neo4j_search, edge_memory_search]
