"""Canonicalize duplicate logical memories across local and fleet search results."""
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from app.edge.memory.hybrid_search import MemoryHit


def _confirmed(hit) -> bool:
    payload = hit.payload
    return bool(payload.get("sync_timestamp") or payload.get("sync_state") == "SYNCHRONIZED")


def dedupe_hits(hits: Sequence["MemoryHit"]) -> list["MemoryHit"]:
    """Keep the newest equivalent revision while retaining same-revision conflicts.

    A FLEET hit can replace its LOCAL twin only when their content hashes agree
    and the fleet payload carries an explicit synchronization confirmation.
    Unknown/non-memory hits retain ordinary point-identity semantics.
    """
    by_logical: dict[str, list[int]] = {}
    for index, hit in enumerate(hits):
        logical_id = hit.payload.get("logical_id")
        if logical_id:
            by_logical.setdefault(str(logical_id), []).append(index)

    keep = set(range(len(hits)))
    for indexes in by_logical.values():
        highest_revision = max(int(hits[i].payload.get("revision", 0)) for i in indexes)
        latest = [i for i in indexes if int(hits[i].payload.get("revision", 0)) == highest_revision]
        hashes: dict[str | None, list[int]] = {}
        for i in latest:
            hashes.setdefault(hits[i].payload.get("content_hash"), []).append(i)
        winners = set()
        for content_hash, same_content in hashes.items():
            if content_hash is None:
                # Missing hashes cannot prove equivalence, so retain each candidate.
                winners.update(same_content)
                continue
            fleet = [i for i in same_content if getattr(hits[i].origin, "value", hits[i].origin) == "FLEET" and _confirmed(hits[i])]
            if fleet:
                winners.add(min(fleet, key=lambda i: (hits[i].point_id, i)))
            else:
                winners.add(min(same_content, key=lambda i: (getattr(hits[i].origin, "value", hits[i].origin) != "LOCAL", hits[i].point_id, i)))
        keep.difference_update(indexes)
        keep.update(winners)
    return [hit for i, hit in enumerate(hits) if i in keep]
