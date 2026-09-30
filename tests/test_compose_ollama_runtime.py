from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_local_inference_url_is_overridable_without_changing_default():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api_environment = compose["services"]["fastapi"]["environment"]
    api_environment = dict(item.split("=", 1) for item in api_environment if "=" in item)
    assert api_environment["OLLAMA_BASE_URL"] == "${OLLAMA_DOCKER_BASE_URL:-http://ollama:11434}"
    initializer = compose["services"]["ollama-init"]
    init_environment = dict(item.split("=", 1) for item in initializer["environment"] if "=" in item)
    assert init_environment["OLLAMA_HOST"] == api_environment["OLLAMA_BASE_URL"]
    assert "ollama pull ${OLLAMA_MODEL:-qwen3.5:0.8b}" in initializer["command"]


def test_env_examples_document_the_optional_host_ollama_route():
    for filename in (".env.example", "env.example"):
        text = (ROOT / filename).read_text()
        assert "OLLAMA_BASE_URL=http://localhost:11434" in text
        assert "OLLAMA_DOCKER_BASE_URL=http://ollama:11434" in text
        assert "host.docker.internal:11434" in text
