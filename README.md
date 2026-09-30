# GRAG Edge

Offline-first semantic memory and reasoning for autonomous industrial inspection robots
(Code Cubicle 6.0, PS3: AI-Powered Edge Memory & Intelligence Platform).

A robot keeps a searchable memory on the device with **Qdrant Edge**, keeps working through
network loss, decides per memory what may leave the device, and reconciles with a fleet-wide
**Qdrant Server** when connectivity returns. Divergent revisions are surfaced as conflicts,
never silently overwritten. A dedicated dashboard shows memory, search, sync and conflicts live.

Pre-existing work and import provenance: see [PREEXISTING_WORK.md](PREEXISTING_WORK.md).
The imported GRAG AI base (Neo4j knowledge graph, LangGraph agents, OpenAI-compatible endpoint)
is reused for reasoning; everything under `app/edge/`, `frontend/`, `scripts/demo/` and the
edge tests is GRAG Edge work.

## What it does

- **Local memory**: dense, BM25 (keyword) and hybrid (RRF) search on the device, no network needed.
- **Sync policy engine**: privacy restriction, then operator policy, then deterministic rules decide
  `local_only`, `approval_required` or `auto` sync. `restricted` and `local_only` memories never enter
  a remote upload payload.
- **Durable outbox**: queued uploads, attempts and checkpoints live in SQLite and survive restarts.
- **Fleet refresh**: full and partial Qdrant snapshots are staged and published atomically; a memory is
  `SYNCHRONIZED` only after the fleet refresh confirms it.
- **Revisions and conflicts**: immutable revision chains, tombstones, conflict detection with explicit
  resolution (keep local, keep fleet, or merge).
- **GRAG answers offline**: `POST /v1/chat/completions` answers from LOCAL evidence with a local Ollama
  model; no cloud key is required.
- **Dashboard**: Overview, Search, Memory, Sync Center and Conflicts pages, updated via SSE.
- **Optional fleet transfer**: a second robot receives the first robot's memory through the fleet server.

## Architecture in one picture

```
 Robot A (grag-edge-net)                          Fleet (grag-cloud-net)
 +-----------------------------------+            +-------------------+
 | FastAPI  /api/v1/edge/*  /v1/chat |  HTTP      | Qdrant Server     |
 |  Qdrant Edge: LOCAL + FLEET shards| <--------> | fleet collection  |
 |  SQLite: policy, outbox, activity |  (cut by   +-------------------+
 |  Ollama (local LLM + embeddings)  |   demo)
 |  Neo4j (knowledge graph, KR)      |
 +-----------------------------------+
        ^ dashboard (React, port 5173)
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quickstart (judging run)

Requirements: Docker with Compose, Python 3 on the host (demo scripts use it for JSON checks).
No cloud credentials are needed.

```bash
cp .env.example .env            # secret-free defaults; keep existing .env if present
docker compose config -q        # validate configuration
make demo-reset                 # clean edge and fleet state
make demo-start                 # build, start fleet + edge, seed deterministic dataset
open http://localhost:5173      # dashboard (EDGE_UI_PORT overrides)
```

The full scripted flow (reset, sync, real network cut, offline write/search/GRAG answer, reconnect,
queue drain, fleet refresh) is one command:

```bash
make demo-acceptance
```

Step-by-step commands with expected UI state: [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md).

## Tests

```bash
make test               # backend pytest
make baseline-check     # full suite; passes with exactly the 10 recorded imported baseline failures
make compose-config     # compose validation
cd frontend && npm ci && npm test -- --run && npm run build
```

Ten imported GRAG AI baseline tests fail for reasons recorded in
`docs/superpowers/verification/2026-09-30-p00-known-failures.txt`; `make baseline-check` enforces that
the failure set never grows or changes.

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, state machine, privacy boundary |
| [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) | Exact reset/start/offline/online/conflict commands |
| [docs/PS3_REQUIREMENTS_TRACEABILITY.md](docs/PS3_REQUIREMENTS_TRACEABILITY.md) | Requirement to code and proof map |
| [SETUP.md](SETUP.md) | Environment and manual setup |
| [docs/OPENWEBUI_INTEGRATION.md](docs/OPENWEBUI_INTEGRATION.md) | Optional Open WebUI chat frontend |
| [docs/superpowers/specs/2026-09-30-grag-edge-design.md](docs/superpowers/specs/2026-09-30-grag-edge-design.md) | Binding design spec |
| [docs/superpowers/verification/](docs/superpowers/verification/) | Per-phase execution evidence and ledger |

## License

GNU General Public License v3
