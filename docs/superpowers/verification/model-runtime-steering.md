# Ollama model runtime steering

## Requested models

- `gemma4:12b-mlx` is the selected local model. The official Gemma 4 tag list marks it as MLX, approximately 7.7 GB, with a 256K context window: https://ollama.com/library/gemma4/tags
- `nemotron-3-nano:30b-cloud` is the selected optional cloud model. The official tag list identifies it as cloud-only and low usage: https://ollama.com/library/nemotron-3-nano/tags
- Ollama's official Apple Silicon MLX instructions use the Gemma tag directly and require current macOS Ollama: https://ollama.com/blog/mlx-performance

## Runtime discovery

- The host Ollama daemon responds on `127.0.0.1:11434`, version `0.35.0`; its model list was initially empty.
- The Docker API container reaches that Mac daemon at `http://host.docker.internal:11434` (resolved as `192.168.127.254` in this runtime); `/api/version` returned `0.35.0`. This uses ordinary HTTP and requires no host Docker socket.
- The native `.env` keeps `OLLAMA_BASE_URL=http://localhost:11434`. Compose now uses a separate `OLLAMA_DOCKER_BASE_URL`, defaulting to the existing `http://ollama:11434` Linux service. The isolated `.env` sets it to `http://host.docker.internal:11434`; API and model initializer use the same override.
- Compose config tests were RED before URL parameterization (2 failed) and GREEN after (2 passed). Rendered configuration resolved FastAPI and initializer to the host route and retained `OLLAMA_MODEL=gemma4:12b-mlx`.
- Host `OLLAMA_API_KEY` is configured, but `OLLAMA_CLOUD_API_KEY` is absent. No cloud inference request was sent; Ollama's cloud-model documentation says cloud execution requires signing in: https://ollama.com/blog/cloud-models

## Model readiness status

Authorized host pulls were started for `gemma4:12b-mlx` and `nomic-embed-text`. Pulls were still running at the time of this record; completion and real chat/embedding checks must be recorded after they finish. The embedding check should confirm one returned vector has the required 768 dimensions.
