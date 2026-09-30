"""Publish a divergent fleet revision of the local Valve V-22 procedure.

Same logical memory, different content from another robot: the Edge runtime
detects it on the next fleet refresh and opens a conflict for the operator.
Runs inside the API container; idempotent by stable memory ID.
"""
import argparse
import asyncio
import sys

import seed_fleet

if __name__ == "__main__":
    sys.path.insert(0, "/app")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-dir", default=str(seed_fleet.DEFAULT_SEED))
    args = parser.parse_args()
    args.file = "conflict.json"
    asyncio.run(seed_fleet._main(args))
