import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def _b():
    return COMPOSE["services"].get("robot-b-api")


def test_robot_b_only_under_fleet_demo_profile():
    b = _b()
    assert b is not None and b["profiles"] == ["fleet-demo"]


def test_robot_b_identity_and_isolated_storage():
    b, a = _b(), COMPOSE["services"]["fastapi"]
    assert "DEVICE_ID=ROBOT-02" in b["environment"]
    assert "8002:8000" in b["ports"]
    assert "robot_b_data:/data" in b["volumes"]
    assert "robot_b_data" in COMPOSE["volumes"]
    assert not set(a["volumes"]) & set(b["volumes"])
    assert "container_name" in b and b["container_name"] != a["container_name"]


def test_robot_b_uses_fleet_server_not_a():
    b = _b()
    assert any(e.startswith("QDRANT_URL=") and "qdrant-server" in e for e in b["environment"])
    assert "grag-cloud-net" in b["networks"]


@pytest.mark.skipif(not (shutil.which("docker-compose") or shutil.which("docker")), reason="compose unavailable")
def test_default_compose_excludes_robot_b():
    cmd = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    out = subprocess.run(cmd + ["config", "--services"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip(out.stderr)
    assert "robot-b-api" not in out.stdout.split()
    prof = subprocess.run(cmd + ["--profile", "fleet-demo", "config", "--services"], cwd=ROOT, capture_output=True, text=True)
    assert "robot-b-api" in prof.stdout.split()
