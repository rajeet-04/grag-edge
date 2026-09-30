import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT = re.compile(r"^\s*(from|import)\s+(chromadb|app\.database\.chroma_client)\b|from app\.database import chroma", re.M)


def production_files():
    return [*ROOT.glob("app/**/*.py"), ROOT / "main.py"]


def test_no_production_chroma_imports():
    offenders = [str(p.relative_to(ROOT)) for p in production_files() if p.exists() and IMPORT.search(p.read_text())]
    assert offenders == []
    assert not (ROOT / "app/database/chroma_client.py").exists()


def test_settings_no_longer_expose_chromadb_path():
    from app.config import Settings

    assert not hasattr(Settings(), "chromadb_path")


def test_dependencies_config_and_compose_have_no_chromadb():
    for name in ("pyproject.toml", "requirements.txt", "docker-compose.yml", "Dockerfile", "env.example", ".env.example", "README.md", "app/config.py"):
        text = (ROOT / name).read_text().lower()
        assert "chroma" not in text, name
    assert "chromadb" not in (ROOT / "uv.lock").read_text().lower()
