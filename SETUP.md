# GRAG Edge Setup

## Prerequisites

- Docker Engine with Compose (the scripts use `docker compose`, falling back to `docker-compose`).
- Python 3.12+ and [uv](https://docs.astral.sh/uv/) for local tests.
- Node 22+ for frontend tests (or any Node container).
- Disk: 10 GB+ for images and models. Hardware target: 8 GB VRAM, 16 GB RAM; a CPU Ollama image works
  for the demo.
- No cloud credentials. Ollama Cloud (`OLLAMA_CLOUD_API_KEY`) is an explicit opt-in that the demo never uses.

## Configuration

```bash
cp .env.example .env
```

Key variables (all have working defaults in `.env.example` / `docker-compose.yml`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEVICE_ID` | `robot-edge-001` | Identity stamped on this robot's memories |
| `QDRANT_EDGE_PATH` | `./data/qdrant-edge` | Local shard directory (fleet shard is a sibling) |
| `EDGE_EMBEDDING_DIMENSION` | `768` | Must match the embedding model (`nomic-embed-text`) |
| `QDRANT_URL` | `http://qdrant-server:6333` | Fleet server, reachable only on `grag-cloud-net` |
| `QDRANT_COLLECTION` | `grag_fleet_memory` | Fleet collection |
| `QDRANT_API_KEY` | unset | Optional. If the server requires a key, set the same value for both client and server; a blank value on the server enables auth unexpectedly |
| `OLLAMA_MODEL` | `qwen3.5:0.8b` | Local chat model |
| `OLLAMA_DOCKER_BASE_URL` | `http://ollama:11434` | Ollama URL as seen from containers |
| `API_KEY` | blank | Optional bearer key for the compatibility endpoint |
| `LLM_USE_CLOUD` | `false` | Keep false for offline/credential-free operation |

## Run the stack

```bash
docker compose config -q
make demo-start          # qdrant-server + fastapi (edge API) with seeded data
docker compose up -d     # optional: also Neo4j, Ollama, dashboard, Open WebUI
```

Service map: edge API `:8000` (`/docs`), dashboard `:5173`, Open WebUI `:3000`, Neo4j browser `:7474`,
Ollama `:11434`. The fleet Qdrant Server has no host port by design. Robot B (`--profile fleet-demo`) is
optional and listens on `:8002`.

## Local development

```bash
uv sync
uv run pytest tests/edge tests/demo tests/e2e tests/performance -q
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend && npm ci && npm test -- --run && npm run build
```

Local runs use the native `qdrant-edge-py` library; no Qdrant Server is needed for the edge tests
(live sync tests require Docker and skip otherwise).

## Troubleshooting

- **Dashboard shows OFFLINE after `make demo-online`**: wait one connectivity interval (a few seconds);
  check `make demo-status`.
- **API port 8000 unreachable from host in nested Docker runtimes**: the demo scripts call the API via
  `docker exec` for this reason; use `make demo-status`.
- **Ollama GPU error**: the default image is CPU; only GPU hosts need the NVIDIA Container Toolkit.
- **Stale image after code change**: `make demo-start` rebuilds (`up -d --build`).
- **Interrupted recording**: `make demo-reset` restores a clean, repeatable state.
