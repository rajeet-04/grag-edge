# GRAG Edge Design Specification

**Date:** 2026-09-30  
**Project:** GRAG Edge  
**Repository:** `rajeet-04/grag-edge`  
**Problem Statement:** Code Cubicle 6.0 PS3 — AI-Powered Edge Memory & Intelligence Platform  
**Status:** Approved architecture; implementation planning pending written-spec review.

## 1. Purpose

GRAG Edge upgrades the pre-existing GRAG AI architecture into an offline-first semantic memory and reasoning platform for autonomous industrial inspection robots.

The required product must:

- maintain searchable semantic memory on the edge device;
- provide low-latency dense, BM25, and hybrid search without network connectivity;
- continue operating through intermittent connectivity;
- decide what information remains local and what is eligible for synchronization;
- synchronize relevant knowledge with centralized Qdrant Server when connectivity returns;
- preserve evolving local memory, revisions, and conflicting information;
- expose memory, search results, synchronization state, conflicts, and system activity through a dedicated user-facing interface;
- demonstrate a meaningful edge-to-cloud AI workflow rather than merely embedding a local vector database.

The judging deployment runs on one physical machine with Docker Compose. Edge and cloud behavior are represented by isolated Docker networks.

## 2. Product Concept

GRAG Edge represents an autonomous industrial inspection robot that operates in facilities with unreliable connectivity.

The robot can:

1. ingest observations, procedures, incidents, operator notes, and learned facts;
2. embed and index them locally;
3. retrieve them through dense semantic search, BM25 sparse search, or hybrid search;
4. answer questions using GRAG reasoning and local Ollama inference;
5. classify each memory for local-only, approval-required, or automatic fleet synchronization;
6. queue synchronization work durably while offline;
7. upload eligible memories when connectivity returns;
8. refresh synchronized fleet knowledge from Qdrant Server;
9. detect divergent revisions and expose explicit conflict resolution;
10. expose the lifecycle through a dedicated operational control console.

The required product is the offline-first single-robot system. A lightweight Robot A → Fleet → Robot B transfer scenario is optional and is implemented only after the core product is stable.

## 3. Core Product Principle

**Edge autonomy is mandatory.**

Loss of Qdrant Server connectivity must not disable:

- memory ingestion;
- local embeddings;
- BM25 indexing;
- local dense/sparse/hybrid retrieval;
- memory inspection;
- sync-policy evaluation;
- queue persistence;
- GRAG question answering with locally available knowledge.

Cloud loss is an **OFFLINE operating mode**, not an application error.

## 4. Existing GRAG Assets Reused

The following GRAG AI capabilities remain and should be reused rather than rewritten:

- FastAPI application layer;
- LangGraph orchestration;
- local Ollama reasoning;
- existing local embedding service;
- context building and token-budget handling;
- traceable retrieval/explanation output;
- streaming response patterns;
- Neo4j temporal factual graph as optional enrichment;
- existing tests and application structure where compatible.

The production memory path changes from ChromaDB to Qdrant Edge. ChromaDB must not remain a hidden production dependency once migration is complete.

## 5. Runtime Architecture

### 5.1 One-machine Docker topology

```text
                           ONE PHYSICAL MACHINE
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  EDGE NETWORK: grag-edge-net        CLOUD NETWORK: grag-cloud-net   │
│                                                                     │
│  ┌─────────────────┐                                                │
│  │ GRAG Edge UI    │                                                │
│  └────────┬────────┘                                                │
│           │                                                         │
│           ▼                                                         │
│  ┌───────────────────────────┐      ┌────────────────────────────┐   │
│  │ GRAG EDGE API            │──────│ QDRANT SERVER              │   │
│  │ FastAPI                  │      │ Central fleet knowledge    │   │
│  │ LangGraph                │      └────────────────────────────┘   │
│  │ Qdrant Edge embedded     │                                       │
│  │ SQLite control plane     │                                       │
│  │ Sync worker              │                                       │
│  │ Policy engine            │                                       │
│  │ Connectivity monitor     │                                       │
│  └────────────┬─────────────┘                                       │
│               │                                                     │
│         ┌─────┴──────┐                                              │
│         ▼            ▼                                              │
│   ┌──────────┐  ┌──────────┐                                       │
│   │ Ollama   │  │ Neo4j    │                                       │
│   │ local AI │  │ optional │                                       │
│   └──────────┘  └──────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
```

Only the Edge API bridges the edge and cloud networks.

Qdrant Edge runs embedded in the Edge API process, not as another server container.

Neo4j is optional enrichment and must not be a hard dependency for offline retrieval or local reasoning.

### 5.2 Real network isolation

The demo must create real network isolation by disconnecting the Edge API from `grag-cloud-net`.

The application must not manipulate Docker itself. Host-side scripts or Make targets perform network connect/disconnect operations.

Target demo commands:

- `make demo-reset`
- `make demo-start`
- `make demo-offline`
- `make demo-online`
- `make demo-conflict`
- optional `make demo-robot-b`

## 6. Memory Architecture

### 6.1 Application-owned storage interface

GRAG agents and retrieval code depend on an application-owned interface rather than directly on Qdrant APIs.

```text
GRAG agents
    │
    ▼
MemoryService
    │
    ├── remember()
    ├── search()
    ├── retrieve()
    ├── update()
    ├── delete()
    └── inspect()
         │
         ▼
QdrantEdgeMemoryStore
    ├── mutable-local EdgeShard
    └── immutable-fleet EdgeShard
```

The Qdrant Edge dependency must be isolated behind one adapter.

### 6.2 Dual-shard local model

**mutable-local**
- writable;
- robot-created or robot-edited data;
- remains available offline;
- contains unsynchronized and locally authoritative revisions.

**immutable-fleet**
- synchronized from centralized Qdrant Server;
- treated as read-only during normal robot memory operations;
- contains fleet/shared knowledge.

Search runs across both shards and returns one logical result set after ranking and deduplication.

## 7. Memory Record

Each memory preserves identity, provenance, revision state, and synchronization policy.

| Field | Meaning |
|---|---|
| `memory_id` | globally unique immutable version identifier |
| `logical_id` | stable identity shared by revisions |
| `device_id` | originating robot/device |
| `memory_type` | observation, procedure, incident, operator_note, learned_fact |
| `content` | searchable memory text |
| `created_at` | original creation time |
| `updated_at` | current revision time |
| `revision` | monotonic revision number |
| `parent_revision` | revision this edit was based on |
| `content_hash` | deterministic change detection |
| `confidence` | source/model confidence |
| `importance` | low, normal, high, critical |
| `sensitivity` | fleet_safe, internal, restricted |
| `sync_policy` | local_only, auto, approval_required |
| `sync_state` | lifecycle state |
| `source_type` | sensor, robot, operator, fleet, document |
| `source_id` | provenance pointer |
| `tags` | machine, component, zone, anomaly, etc. |
| `embedding_version` | dense embedding compatibility |
| `sync_timestamp` | synchronization boundary/checkpoint metadata |

Dense and BM25 sparse representations are indexed alongside the payload.

## 8. Retrieval

The edge node supports:

- dense semantic search;
- BM25 sparse keyword search;
- hybrid retrieval.

Dense vectors initially use the existing GRAG local embedding service.

BM25 uses Qdrant Edge local sparse indexing.

```text
Query
  ↓
Query Agent
  ↓
Retrieval Coordinator
  ├── dense: mutable-local
  ├── dense: immutable-fleet
  ├── BM25: mutable-local
  ├── BM25: immutable-fleet
  └── optional Neo4j enrichment
         ↓
rank + fuse + dedupe + provenance
         ↓
Context Builder
         ↓
Local Ollama
         ↓
Explanation / answer
```

Search results expose `LOCAL` or `FLEET` origin and retain enough scoring data for an advanced “Explain retrieval” view.

## 9. Sync Policy Engine

The sync policy is deterministic and inspectable.

Decision order:

```text
privacy restriction
        ↓
explicit operator policy
        ↓
deterministic sync rules
        ↓
optional GRAG recommendation
        ↓
final decision
```

An LLM can recommend but cannot bypass hard privacy restrictions.

Initial behavior:

| Condition | Decision |
|---|---|
| sensitivity = restricted | local_only |
| explicit local_only policy | local_only |
| high/critical fleet-safe incident with sufficient confidence | auto |
| operator note requiring review | approval_required |
| low-importance routine observation | local_only |
| novel fleet-safe learned maintenance fact | auto |

The UI must expose the reason for each nontrivial decision.

## 10. Synchronization State Machine

Primary states:

```text
NEW
 │
 ▼
LOCAL_DIRTY
 ├──────────────► LOCAL_ONLY
 ├──────────────► AWAITING_APPROVAL
 └──────────────► QUEUED
                    │
                    ▼
                 UPLOADING
                  /     \
                 /       \
                ▼         ▼
          UPLOADED      RETRY_WAIT
                │           │
                ▼           └────► QUEUED
       SNAPSHOT_PENDING
                │
                ▼
          SYNCHRONIZED
```

Exceptional states:

- `CONFLICTED`
- `SUPERSEDED`

A Boolean synced flag is explicitly rejected.

## 11. Durable Operational State

Qdrant Edge stores searchable memory.

SQLite stores operational control-plane state only.

Expected logical tables:

- `sync_outbox`
- `sync_attempts`
- `conflicts`
- `sync_checkpoints`
- `activity_events`
- `device_state`

The outbox must survive network loss, Edge API restarts, and sync worker restarts.

Remote upload must be idempotent for a logical revision.

## 12. Edge → Cloud Synchronization

```text
SQLite Outbox
     ↓
Sync Worker
     ↓
Qdrant Server
```

Uploads are batched and idempotent.

Each attempt records:

- attempt ID;
- memory ID;
- revision;
- start/end time;
- result;
- retry count;
- error detail.

Network failure moves the item into bounded exponential retry without blocking robot operation.

## 13. Cloud → Edge Synchronization

Initial fleet bootstrap uses a full synchronized snapshot.

Subsequent refreshes use partial snapshot/update semantics.

```text
immutable-fleet manifest
        ↓
Qdrant Server partial snapshot
        ↓
download + validate
        ↓
acquire short fleet-update lock
        ↓
apply update
        ↓
refresh checkpoint/manifest
        ↓
release lock
```

Robot-created writes target `mutable-local`, so local ingestion remains available while fleet knowledge refreshes.

If refresh fails, the previous valid fleet shard remains active.

## 14. Deduplication

Equivalent local and fleet revisions must not appear twice in search.

Canonical comparison uses:

- `logical_id`;
- `revision`;
- `content_hash`;
- `sync_timestamp`.

A local copy is eligible for cleanup only after remote acknowledgment and fleet refresh confirms representation.

## 15. Conflict Model

Last-write-wins is not the universal rule.

A divergent edit exists when local and fleet revisions both changed from the same base and their content differs.

Conflict-sensitive types:
- procedure;
- learned_fact sharing a logical identity;
- configuration/instruction records.

Normally append-only:
- observation;
- incident;
- sensor event;
- ordinary operator note.

A divergent conflict becomes `CONFLICTED`.

The conflict UI exposes local revision, fleet revision, shared base, provenance, timestamps, and resolution actions.

Supported actions:

- `KEEP_LOCAL`
- `ACCEPT_FLEET`
- `MERGE`

`MERGE` creates a new revision and never rewrites history.

## 16. API Surface

Judge-facing edge APIs live under `/api/v1/edge/*`.

### Memory
- `POST /api/v1/edge/memories`
- `GET /api/v1/edge/memories`
- `GET /api/v1/edge/memories/{id}`
- `PATCH /api/v1/edge/memories/{id}`
- `POST /api/v1/edge/search`

Deletion uses tombstone semantics for synchronized/revisioned records.

### Synchronization
- `GET /api/v1/edge/sync/status`
- `GET /api/v1/edge/sync/queue`
- `POST /api/v1/edge/sync/run`
- `POST /api/v1/edge/sync/{memory_id}/approve`
- `POST /api/v1/edge/sync/{memory_id}/reject`
- `GET /api/v1/edge/sync/history`

### Conflicts
- `GET /api/v1/edge/conflicts`
- `GET /api/v1/edge/conflicts/{id}`
- `POST /api/v1/edge/conflicts/{id}/resolve`

### Operations
- `GET /api/v1/edge/status`
- `GET /api/v1/edge/activity`
- `GET /api/v1/edge/stats`
- `GET /api/v1/edge/events` using SSE

The existing `POST /v1/chat/completions` compatibility endpoint remains.

## 17. GRAG Integration

The current direct ChromaDB retrieval path is replaced by the new retrieval coordinator.

- `app/memory/*` uses `MemoryService`;
- `app/retrieval/fallback.py` no longer calls ChromaDB directly;
- `app/agents/graph.py` replaces the existing KB search node with edge-memory retrieval;
- Neo4j remains optional enrichment;
- local Ollama remains the default reasoning runtime.

Cloud initialization failure must never prevent API readiness.

## 18. Proposed Code Boundaries

```text
app/
├── edge/
│   ├── memory/
│   │   ├── service.py
│   │   ├── models.py
│   │   ├── qdrant_store.py
│   │   └── hybrid_search.py
│   ├── policy/
│   │   ├── engine.py
│   │   └── rules.py
│   ├── sync/
│   │   ├── service.py
│   │   ├── outbox.py
│   │   ├── server_client.py
│   │   ├── snapshot.py
│   │   └── connectivity.py
│   ├── conflicts/
│   │   └── service.py
│   ├── state/
│   │   └── sqlite.py
│   └── api/
│       ├── memories.py
│       ├── sync.py
│       ├── conflicts.py
│       └── operations.py
├── agents/
├── ingestion/
├── retrieval/
└── ...
```

The exact file breakdown may be refined in the implementation plan, but subsystem responsibilities and dependency direction are fixed.

## 19. Startup and Health Model

Startup order:

```text
load configuration
↓
open SQLite control plane
↓
open/create mutable Qdrant Edge shard
↓
open/create fleet Qdrant Edge shard
↓
initialize BM25
↓
initialize MemoryService
↓
initialize sync state
↓
start connectivity monitor
↓
start sync worker
↓
initialize optional Neo4j enrichment
↓
API READY
```

Cloud initialization failure yields:

- Edge API: ready;
- connectivity: offline;
- sync: deferred.

Health states:

- `HEALTHY`
- `DEGRADED`
- `OFFLINE`
- `ERROR`

Offline must be distinguished from broken.

## 20. Failure Isolation

| Failure | Required behavior |
|---|---|
| Qdrant Server unavailable | continue fully offline |
| cloud network removed | continue fully offline |
| fleet refresh fails | retain previous fleet shard |
| upload fails | retry unacknowledged work |
| conflict detected | preserve both revisions |
| Neo4j unavailable | skip graph enrichment |
| local Ollama unavailable | memory/search still inspectable; answer generation degraded |
| Qdrant Edge cannot open | service unhealthy/error |
| SQLite control DB unavailable | sync control unsafe; service unhealthy/error |

## 21. Dashboard

A dedicated React + Vite + TypeScript control console replaces OpenWebUI as the primary judging surface.

Navigation:

- Overview;
- Search;
- Memory;
- Sync;
- Conflicts.

### Overview
Always shows:
- robot/device ID;
- edge operating state;
- Qdrant Edge state;
- local AI state;
- fleet connectivity;
- pending sync count;
- conflict count;
- last sync;
- local search latency;
- live activity timeline.

The screen must visibly distinguish **OFFLINE but operational** from **ERROR**.

### Search
Supports:
- memory search;
- “Ask GRAG” mode;
- source-backed evidence cards;
- LOCAL/FLEET provenance;
- optional retrieval score explanation.

### Memory
Supports filtering by:
- source;
- memory type;
- sync state;
- importance;
- device;
- tags;
- time.

Detail view shows provenance, revision history, policy decision, indexing state, and synchronization state.

### Sync
Shows pending, retrying, conflicted, and synchronized items plus the policy reason for each decision.

### Conflicts
Shows local vs fleet revisions, shared base, provenance, and resolution actions.

## 22. Visual Direction

The control console is an **industrial operations interface**, not a generic analytics dashboard.

Principles:

- dark operational surface;
- high contrast;
- large connectivity/state indicators;
- monospace reserved for machine IDs and logs;
- conventional readable UI typography elsewhere;
- restrained purposeful motion;
- visual hierarchy: **status → change → attention → detail**;
- no chart-heavy dashboard for its own sake.

## 23. Demo Dataset

The deterministic demo uses:

- Pump P-41;
- Compressor C-17;
- Motor M-08;
- Valve V-22.

Fleet seed data includes:
- operating procedures;
- known failure modes;
- maintenance history;
- safe thresholds;
- previous fleet observations.

Robot-01 creates new observations during the demo.

## 24. Required Judging Flow

1. start online with fleet knowledge synchronized;
2. disconnect cloud network;
3. dashboard switches to OFFLINE while local capability stays healthy;
4. create Pump P-41 observation;
5. policy marks eligible item for auto sync;
6. Sync Center shows queued work;
7. ask GRAG about Pump P-41 while still offline;
8. answer cites LOCAL evidence;
9. reconnect network;
10. queued work uploads;
11. fleet refresh completes;
12. memory state becomes synchronized;
13. optionally show a seeded divergent conflict and explicit resolution.

## 25. Optional Fleet-Transfer Scenario

After the core product is stable:

```text
Robot A offline
    ↓
learns new anomaly
    ↓
reconnects and syncs
    ↓
Qdrant Server fleet memory
    ↓
Robot B refreshes
    ↓
Robot B retrieves Robot A's lesson
```

Robot B should be started through an optional Docker Compose profile so it cannot destabilize the required product.

## 26. Security and Privacy Boundary

The initial product makes narrow, testable guarantees.

A memory marked `restricted` or `local_only` must never enter a remote upload payload.

Decision precedence:

```text
privacy restriction
↓
explicit operator policy
↓
deterministic sync rules
↓
optional AI recommendation
```

The LLM never has authority to override privacy constraints.

Secrets come from environment configuration. The repository contains `.env.example` only and must not commit real keys or tokens.

The local demo must function without external SaaS credentials.

## 27. Observability

Every important state transition becomes an `ActivityEvent` with:

- event ID;
- event type;
- device ID;
- optional memory ID;
- timestamp;
- severity;
- message;
- metadata.

Required event types include:

- DEVICE_STARTED;
- CLOUD_LINK_UP;
- CLOUD_LINK_DOWN;
- MEMORY_CREATED;
- MEMORY_REVISED;
- POLICY_LOCAL_ONLY;
- POLICY_SYNC_APPROVED;
- SYNC_QUEUED;
- SYNC_STARTED;
- SYNC_RETRY;
- SYNC_COMPLETED;
- FLEET_REFRESH_STARTED;
- FLEET_REFRESH_COMPLETED;
- CONFLICT_DETECTED;
- CONFLICT_RESOLVED;
- SEARCH_COMPLETED.

Useful operational metrics:

- local memory count;
- fleet memory count;
- pending sync count;
- conflict count;
- last sync timestamp;
- last fleet refresh;
- search latency;
- result origin counts;
- sync success/failure count;
- connectivity state.

No large external observability stack is required for the hackathon.

## 28. Performance Targets

For the demo dataset, target:

- local search p95 < 250 ms;
- memory write p95 < 300 ms excluding model warm-up;
- status API < 100 ms;
- dashboard connectivity update < 2 s after detected network transition.

GRAG answer generation latency is measured separately from retrieval latency.

## 29. Recovery Requirements

Persist and recover correctly across:

- Edge API restart while offline;
- restart with queued uploads;
- restart after upload but before fleet refresh;
- restart with unresolved conflict.

After restart:
- local memories remain;
- queue remains;
- conflicts remain;
- sync checkpoint remains;
- activity history remains.

## 30. Testing Strategy

Four levels:

1. **unit tests**
   - policy rules;
   - sync state transitions;
   - revision logic;
   - deduplication;
   - ranking/fusion.

2. **integration tests**
   - Qdrant Edge persistence;
   - BM25/dense/hybrid indexing;
   - SQLite outbox;
   - Qdrant Server upload;
   - fleet refresh.

3. **offline system tests**
   - real cloud network disconnect;
   - continued local memory operations;
   - queued synchronization;
   - recovery on reconnect.

4. **demo/E2E tests**
   - reset → seed → offline → operate → reconnect → synchronize;
   - deterministic conflict preparation/resolution;
   - optional Robot A → Fleet → Robot B propagation.

## 31. Hard Acceptance Criteria

With Qdrant Server unreachable, all of the following must still work:

- POST memory;
- PATCH memory;
- GET/list memory;
- dense search;
- BM25 search;
- hybrid search;
- GRAG local answer generation;
- policy evaluation;
- queue inspection;
- memory inspection;
- activity stream.

Cloud-specific operations degrade to queued/offline state rather than producing application-wide 500 errors.

Queued sync work must survive process restart.

A divergent revision must never be silently overwritten.

The dashboard must update connectivity, queue, sync, and conflict state without manual refresh.

## 32. Implementation Phases and Exit Gates

| Phase | Deliverable | Exit gate |
|---|---|---|
| P0 | Baseline verification + container cleanup | imported GRAG build/tests understood; Docker baseline reproducible |
| P1 | Storage abstraction + Qdrant Edge | persistent local memory works through application interface |
| P2 | Dense + BM25 + hybrid retrieval | all three retrieval modes verified locally |
| P3 | Robot memory schema + provenance | revision/provenance data persisted and inspectable |
| P4 | Sync policy + durable outbox | deterministic policy and restart-safe queue pass tests |
| P5 | Connectivity + edge→server upload | real network loss detected; upload recovers after reconnect |
| P6 | Server→edge fleet refresh | initial full and subsequent incremental refresh verified |
| P7 | Revisioning, dedupe, conflicts | divergent revisions and all resolution paths tested |
| P8 | GRAG/LangGraph migration | GRAG reasoning works with Qdrant Edge while cloud is disconnected |
| P9 | Dedicated dashboard | required states visible live through actual APIs/SSE |
| P10 | Deterministic demo tooling | repeatable reset → offline → operate → reconnect → sync |
| P11 | Optional fleet transfer | Robot A → Fleet → Robot B propagation works |
| P12 | Hardening + submission readiness | full tests, clean setup, docs, reproducible judge run |

A later phase cannot be declared complete by bypassing an earlier phase's exit gate.

## 33. Explicit Non-Goals

The hackathon release does not include:

- real ROS hardware integration;
- Kubernetes;
- multi-region cloud architecture;
- arbitrary fleets of physical robots;
- custom model training;
- automatic LLM-driven conflict resolution;
- enterprise RBAC;
- end-to-end cryptographic fleet identity;
- distributed consensus.

These are intentionally excluded to keep the core PS3 workflow reliable.

## 34. Final Product Contract

GRAG Edge is a containerized offline-first semantic memory and reasoning platform for autonomous inspection robots. Each robot stores and searches evolving knowledge locally through Qdrant Edge, uses dense and BM25 retrieval without connectivity, applies explicit privacy-aware rules to decide what becomes fleet knowledge, persists synchronization work during outages, synchronizes bidirectionally with Qdrant Server when connectivity returns, preserves divergent revisions through explicit conflict handling, and exposes the complete lifecycle through an operational control console.

The optional extension demonstrates fleet learning by transferring synchronized knowledge from Robot A → Fleet → Robot B.
