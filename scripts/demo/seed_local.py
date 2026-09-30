"""Idempotently seed the robot-local demo memories through the Edge API.

Runs with only the standard library so it can execute inside the API container:
  python seed_local.py [--base-url URL] [--seed-dir DIR]
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "/api/v1/edge/memories"
DEFAULT_SEED = Path(__file__).resolve().parents[2] / "demo" / "seed"


def http_api(base_url):
    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, {}
    return call


def seed(api, data):
    created = existing = 0
    entries = data["memories"]
    for entry in entries:
        status, _ = api("GET", f"{API}/{entry['memory_id']}")
        if status == 200:
            existing += 1
            continue
        if status != 404:
            raise SystemExit(f"seed_local: unexpected status {status} reading {entry['memory_id']}")
        body = {k: v for k, v in entry.items() if k != "equipment"}
        body["device_id"] = data["device_id"]
        status, _ = api("POST", API, body)
        if status != 201:
            raise SystemExit(f"seed_local: create failed with status {status} for {entry['memory_id']}")
        created += 1
    missing = [e["memory_id"] for e in entries if api("GET", f"{API}/{e['memory_id']}")[0] != 200]
    if missing:
        raise SystemExit(f"seed_local: verification failed, missing {missing}")
    return {"created": created, "existing": existing, "total": len(entries)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED))
    args = parser.parse_args()
    data = json.loads((Path(args.seed_dir) / "robot-local.json").read_text())
    print(json.dumps(seed(http_api(args.base_url), data)))


if __name__ == "__main__":
    main()
