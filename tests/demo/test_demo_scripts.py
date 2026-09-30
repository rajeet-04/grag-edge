import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ["demo-reset", "demo-start", "demo-offline", "demo-online", "demo-status"]

FAKE_DOCKER = r'''#!/usr/bin/env bash
state="$FAKE_STATE"; echo "$*" >> "$state/calls"
case "$*" in
  "compose version") exit 0;;
  "compose ps -q fastapi") echo "${FAKE_CID:-cid123}";;
  *"State.Running"*) echo true;;
  *"NetworkSettings.Networks"*) [[ -f "$state/connected" ]] && echo yes || echo no;;
  "inspect -f {{.Name}} "*) echo /grag-api;;
  "network disconnect "*) rm -f "$state/connected";;
  "network connect "*) touch "$state/connected";;
  exec*/edge/status) [[ -f "$state/connected" ]] && echo '{"connectivity":"ONLINE"}' || echo '{"connectivity":"OFFLINE"}';;
  exec*) echo '{}';;
  *) exit 1;;
esac
'''


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "connected").touch()
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_STATE": str(tmp_path), "DEMO_WAIT_SECONDS": "5"}

    def run(script, **extra):
        return subprocess.run(["bash", str(ROOT / "scripts/demo" / script)], env={**env, **extra}, capture_output=True, text=True, timeout=60)

    def calls():
        return (tmp_path / "calls").read_text().splitlines()

    return run, calls, tmp_path


@pytest.mark.parametrize("target", TARGETS)
def test_make_target_exists(target):
    result = subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_offline_is_idempotent_and_cuts_exact_network(fake):
    run, calls, state = fake
    assert run("offline.sh").returncode == 0
    assert run("offline.sh").returncode == 0
    cuts = [c for c in calls() if c.startswith("network disconnect")]
    assert cuts == ["network disconnect grag-cloud-net cid123"]
    assert not (state / "connected").exists()


def test_online_when_already_online_is_safe(fake):
    run, calls, _ = fake
    assert run("online.sh").returncode == 0
    assert not [c for c in calls() if c.startswith("network connect")]


def test_offline_online_cycles_repeat(fake):
    run, calls, state = fake
    for _ in range(2):
        assert run("offline.sh").returncode == 0
        assert run("online.sh").returncode == 0
    assert (state / "connected").exists()
    assert len([c for c in calls() if c.startswith("network connect")]) == 2


def test_container_id_is_resolved_fresh_each_invocation(fake):
    run, calls, _ = fake
    run("status.sh", FAKE_CID="first")
    run("status.sh", FAKE_CID="second")
    assert any(" first" in c or c.endswith("first") for c in calls())
    assert any("second" in c for c in calls())


def test_ambiguous_container_state_fails(fake):
    run, _, _ = fake
    assert run("offline.sh", FAKE_CID="a\nb").returncode != 0
