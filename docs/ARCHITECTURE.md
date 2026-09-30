# GRAG Edge Architecture

Binding design: `docs/superpowers/specs/2026-09-30-grag-edge-design.md`. This document maps that
design onto the code as implemented.

## Components

| Component | Code | Role |
|-----------|------|------|
| Edge API | `app/edge/api/{memories,sync,conflicts,operations}.py` | Judge-facing `/api/v1/edge/*` |
| Memory store | `app/edge/memory/qdrant_store.py` | Qdrant Edge with separate LOCAL and FLEET shards (dense + sparse vectors) |
| Memory service | `app/edge/memory/service.py` | Create, revise (immutable revisions), tombstone, approve/reject |
| Search | `app/edge/memory/{hybrid_search,bm25,dedupe}.py` | Dense, BM25, RRF-fused hybrid; LOCAL/FLEET dedupe |
| Policy | `app/edge/policy/{engine,rules}.py` | Privacy, operator, deterministic rules |
| Durable state | `app/edge/state/sqlite.py`, `activity.py` | Effective policy, outbox, attempts, checkpoints, conflicts, activity (SQLite) |
| Sync | `app/edge/sync/{service,outbox,workflow,server_client,connectivity,snapshot}.py` | Upload, retractions, fleet snapshot refresh, completion |
| Conflicts | `app/edge/conflicts/service.py` | Detection and explicit resolution |
| Runtime | `app/edge/runtime.py` | Owns services, background health and sync loops, restart reconciliation |
| GRAG | `app/agents/`, `app/api/openai.py` | LangGraph pipeline; edge memory is the KB, Neo4j the KR |
| Dashboard | `frontend/src/` | React, five pages, SSE-driven |
| Demo | `scripts/demo/`, `demo/` | Deterministic dataset and scripted flows |

## Two memory planes, one control plane

- **LOCAL shard**: this robot's writes and revisions; always searchable offline.
- **FLEET shard**: an immutable snapshot of the server collection, replaced atomically by publishing a new
  generation directory and a current-generation pointer; never edited locally.
- **SQLite control plane**: effective sync policy, outbox, attempts, checkpoints, conflicts, activity.
  Qdrant Edge and SQLite cannot share a transaction, so the Qdrant revision is flushed first as
  `LOCAL_DIRTY`, SQLite then owns policy/state atomically, reads overlay committed control metadata and
  startup reconciles any crash gap.
- **KR/KB separation**: Neo4j holds objective facts; episodic memory stays in Qdrant Edge.

## Sync state machine

```
NEW -> LOCAL_DIRTY -> {LOCAL_ONLY | AWAITING_APPROVAL | QUEUED}
QUEUED -> UPLOADING -> UPLOADED -> SNAPSHOT_PENDING -> SYNCHRONIZED
UPLOADING -> RETRY_WAIT -> UPLOADING            (backoff, durable)
any -> SUPERSEDED (newer revision) | CONFLICTED (divergent fleet revision)
```

`UPLOADED` alone is never `SYNCHRONIZED`: completion requires a fleet snapshot refresh that
contains the acknowledged revision. Attempts persist real start/end times and outcomes.

## Data flow: offline write to synchronized

1. `POST /memories` embeds, writes the Qdrant revision, commits policy + outbox + activity in SQLite.
2. Cloud unreachable: state stays `QUEUED`; every local API keeps working (health is a bounded probe on a
   monitor, never on the request path).
3. Connectivity returns: worker claims the item, rechecks privacy/policy/latest revision immediately before
   the network call, upserts a deterministic point, marks `UPLOADED`.
4. Fleet refresh (full or partial snapshot, staged, atomically published) confirms the revision and
   completes the run; LOCAL cleanup happens only for confirmed, non-restricted duplicates.

## Privacy boundary

`restricted` and `local_only` never enter an upload payload: checked at policy time, at claim time and again
after materializing the point, using the effective SQLite policy projected over the stored payload. Explicit
deletion of a previously shared revision queues ID-only retractions confirmed absent after a fleet refresh.
Secrets are environment variables only; `.env` is git-ignored; `.env.example` holds no credentials.

## Conflicts

A conflict opens when the local head and fleet head both descend from a shared base with different content
for the same logical memory. Records keep both revisions, provenance and the shared base; resolution
(`KEEP_LOCAL`, `ACCEPT_FLEET`, `MERGE`) writes a new revision that supersedes both. Conflicted revisions are
blocked from upload and revision until resolved.

A device whose head was resolved by a peer adopts the peer's resolution the next time the operator revises
or deletes that memory: the resolution is restored locally as the head (no fork), new revisions build on it,
and a delete also retracts the adopted resolution from the fleet. Open conflicts are closed when their fleet
branch is still present but has been superseded by a descendant or a resolution.

Trust model: `resolves_memory_ids` on a fleet record is accepted only for branches of the same
`logical_id`; IDs known to belong to another logical memory are ignored. Fleet peers are not individually
authenticated (they share the fleet Qdrant credential), so a peer can still publish a same-logical
resolution; the validation bounds its effect to that one memory and does not authenticate the peer.

## Observability

`GET /edge/status`, `/edge/stats` (local/fleet counts, origin counts, pending sync, conflicts, last sync,
last fleet refresh, search latency last and p95, sync success/failure counts, connectivity),
`/edge/activity` and `/edge/events` (SSE over persisted events with `Last-Event-ID` resume).

## Failure isolation

Qdrant Server, Neo4j or cloud LLM outages degrade to queued/offline states; local memory APIs and local
answer generation stay available. Startup does not require the cloud.

## Known limits

See "Deferred items" in `docs/superpowers/verification/p12-execution.md`.
