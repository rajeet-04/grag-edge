# GRAG Edge P5 Connectivity and Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect real cloud connectivity changes and drain eligible outbox work idempotently to Qdrant Server after reconnect.

**Architecture:** Qdrant Server lives only on `grag-cloud-net`; the Edge API bridges edge and cloud networks. A background connectivity monitor updates durable device state, and a sync worker uploads queued revisions without blocking memory/search APIs.

**Tech Stack:** Qdrant Server, qdrant-client/httpx, asyncio, Docker Compose, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Edge API starts successfully when Qdrant Server is unreachable.
- Qdrant Server is not exposed to host in the normal demo topology.
- Upload is idempotent for `(logical_id, revision)`.
- Remote failure never blocks local ingestion/search.
- Exit gate: real network loss is detected and queued upload recovers after reconnect.

## Review Focus
- DNS refusal, timeout, and connection reset all map to OFFLINE rather than ERROR.
- A 4xx authentication/configuration response is ERROR/DEGRADED, not “offline”.
- Worker restart during UPLOADING must safely retry.
- Duplicate upload after ambiguous timeout must not duplicate logical memory.
- Connectivity flapping must not spawn overlapping sync runs.

---

### Task 1: Cloud topology and Qdrant Server client

**Files:**
- Modify: `docker-compose.yml`
- Modify: `env.example`
- Modify: `app/config.py`
- Create: `app/edge/sync/server_client.py`
- Test: `tests/edge/sync/test_server_client.py`

**Interfaces:**
- Produce Docker network `grag-cloud-net` and service `qdrant-server`.
- Only `fastapi` joins both `grag-edge-net` and `grag-cloud-net`.
- Produce: `QdrantServerClient.health() -> CloudHealth`.
- Produce: `upsert_memory(memory: MemoryRecord) -> RemoteAck` using deterministic remote point identity derived from `memory_id`.

- [ ] **Step 1: Write client classification/idempotency tests**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Add server service, config, and client**
- [ ] **Step 4: Verify**
  Run unit tests and `docker compose config -q`; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add fleet Qdrant server boundary`

### Task 2: Connectivity monitor

**Files:**
- Create: `app/edge/sync/connectivity.py`
- Test: `tests/edge/sync/test_connectivity.py`

**Interfaces:**
- Produce enum: `ConnectivityState.ONLINE`, `OFFLINE`, `ERROR`, `UNKNOWN`.
- Produce: `ConnectivityMonitor.run_once() -> ConnectivityState`.
- Persist state transition time in `device_state`.
- Emit `CLOUD_LINK_UP` and `CLOUD_LINK_DOWN` activity events only on transitions.

- [ ] **Step 1: Write transition tests**
  Cover timeout/refusal, auth/config failure, recovery, and flapping without duplicate transition events.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement monitor**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: monitor fleet connectivity`

### Task 3: Non-blocking sync worker and status API

**Files:**
- Create: `app/edge/sync/service.py`
- Modify: `app/edge/api/sync.py`
- Create: `app/edge/api/operations.py`
- Modify: `app/main.py`
- Test: `tests/edge/sync/test_sync_service.py`
- Test: `tests/edge/api/test_edge_status.py`

**Interfaces:**
- Produce: `SyncService.run_once() -> SyncRunResult`.
- Produce: `GET /api/v1/edge/sync/status`, `POST /api/v1/edge/sync/run`, `GET /api/v1/edge/status`.
- State transitions: QUEUED → UPLOADING → UPLOADED; failures → RETRY_WAIT → QUEUED with bounded exponential backoff.

- [ ] **Step 1: Write worker/API tests**
  Assert local APIs remain usable while server client fails; restart of an UPLOADING item retries safely; manual run triggers work but does not wait for all remote operations.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement worker lifecycle and status**
- [ ] **Step 4: Verify**
  Run all sync tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: upload queued edge memories after reconnect`

**Exit gate:** disconnecting Edge API from `grag-cloud-net` yields OFFLINE while local memory works; reconnect drains queued eligible work without duplicates.
