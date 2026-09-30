# GRAG Edge P9 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the dedicated GRAG Edge industrial operations console for memory, search, synchronization, conflicts, and live activity.

**Architecture:** A React + Vite + TypeScript SPA consumes FastAPI JSON endpoints and an SSE event stream. The UI has five destinations: Overview, Search, Memory, Sync, Conflicts. OpenWebUI remains optional/debug-only.

**Tech Stack:** React, Vite, TypeScript, React Router, native fetch/EventSource, CSS variables, Vitest/Testing Library, Playwright or equivalent browser smoke test.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Operate-mode UI: status → change → attention → detail.
- Dark industrial surface; high contrast; restrained motion.
- Monospace only for machine identifiers/logs.
- No chart-heavy dashboard.
- Offline must look operational, not broken.
- Exit gate: required backend states are visible live through real APIs/SSE without manual refresh.

## Review Focus
- SSE reconnect must not duplicate activity rows indefinitely.
- Empty memory/conflict/queue states need intentional empty-state copy.
- Very long memory content and machine IDs must not destroy layout.
- Backend offline/error responses must show actionable state, not blank screens.
- Keyboard focus and contrast must remain usable in dark mode.

---

### Task 1: Frontend shell and typed API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/styles/tokens.css`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Routes: `/`, `/search`, `/memory`, `/sync`, `/conflicts`.
- API base supplied by `VITE_EDGE_API_BASE`; default to same-origin `/api` proxy in dev/Compose.
- Produce typed methods matching P3–P7 API contracts.

- [ ] **Step 1: Write shell/navigation test**
  Assert five navigation destinations and active route label.
- [ ] **Step 2: Run**
  Run: `cd frontend && npm test -- --run`
  Expected: FAIL.
- [ ] **Step 3: Scaffold Vite React TS shell and typed client**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: scaffold GRAG Edge operations console`

### Task 2: Overview + live activity

**Files:**
- Create: `frontend/src/pages/Overview.tsx`
- Create: `frontend/src/hooks/useEdgeEvents.ts`
- Create: `frontend/src/components/StatusRail.tsx`
- Create: `frontend/src/components/ActivityFeed.tsx`
- Test: `frontend/src/pages/Overview.test.tsx`

**Interfaces:**
- Consume `GET /api/v1/edge/status`, `GET /api/v1/edge/stats`, `GET /api/v1/edge/events`.
- Status rail displays device, edge state, local AI, Qdrant Edge, fleet link, pending sync, conflicts.
- SSE updates status/activity without page reload.

- [ ] **Step 1: Write ONLINE→OFFLINE live-update test**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement status rail, metrics, activity feed, SSE reconnect**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add live edge mission overview`

### Task 3: Search and Memory surfaces

**Files:**
- Create: `frontend/src/pages/Search.tsx`
- Create: `frontend/src/pages/Memory.tsx`
- Create: `frontend/src/components/EvidenceCard.tsx`
- Create: `frontend/src/components/MemoryDetail.tsx`
- Test: `frontend/src/pages/Search.test.tsx`
- Test: `frontend/src/pages/Memory.test.tsx`

**Interfaces:**
- Search modes: memory search and Ask GRAG.
- Evidence cards render LOCAL/FLEET, device/source, revision, confidence, sync state; advanced control reveals dense/sparse/combined scores.
- Memory filters: source, type, sync state, importance, device, tag, time.

- [ ] **Step 1: Write evidence/filter/overflow tests**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement Search and Memory pages**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add provenance search and memory explorer`

### Task 4: Sync and Conflict surfaces + Compose frontend

**Files:**
- Create: `frontend/src/pages/Sync.tsx`
- Create: `frontend/src/pages/Conflicts.tsx`
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`
- Test: `frontend/src/pages/Sync.test.tsx`
- Test: `frontend/src/pages/Conflicts.test.tsx`

**Interfaces:**
- Sync renders pending/retry/conflict counts and policy reasons.
- Conflict page supports KEEP_LOCAL, ACCEPT_FLEET, MERGE.
- Compose service `grag-edge-ui` exposes the console and depends only on the edge API, not cloud Qdrant.

- [ ] **Step 1: Write sync-state and conflict-action tests**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement pages and container**
- [ ] **Step 4: Verify**
  Run frontend tests + `docker compose config -q`; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: complete GRAG Edge control console`

**Exit gate:** disconnect/reconnect, queue changes, sync completion, and conflicts update the UI without manual refresh.
