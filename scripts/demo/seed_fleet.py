"""Idempotently publish deterministic fleet memories to the Qdrant Server.

Runs inside the API container (needs app imports and cloud-net access):
  python seed_fleet.py [--seed-dir DIR] [--file fleet.json]
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "demo" / "seed"


def build_point(entry, data):
    from app.edge.memory.models import MemoryRecord
    from app.edge.memory.service import MemoryService
    from app.edge.memory.store import StoredPoint

    created = datetime.fromisoformat(data["created_at"])
    fields = {k: v for k, v in entry.items() if k != "equipment"}
    record = MemoryRecord(
        **fields, device_id=data["device_id"], created_at=created, updated_at=created, revision=1, parent_revision=None,
        content_hash=MemoryService.content_hash(entry["content"]), sync_policy="auto", sync_state="SYNCHRONIZED",
    )
    return record


async def seed(cloud, embed, data):
    from app.edge.memory.store import StoredPoint

    ids = []
    for entry in data["memories"]:
        record = build_point(entry, data)
        dense = await embed.embed_with_context(record.content, "search_document")
        cloud.upsert_point(StoredPoint(record.memory_id, dense, None, {"record_type": "memory", **record.model_dump(mode="json")}))
        ids.append(record.memory_id)
    found = cloud.retrieve_ids(ids)
    if sorted(found) != sorted(ids):
        raise SystemExit(f"seed_fleet: verification failed, missing {sorted(set(ids) - set(found))}")
    return {"upserted": len(ids), "total": len(found)}


class ServerAdapter:
    def __init__(self, server):
        self.server = server

    def upsert_point(self, point):
        return self.server.upsert_point(point)

    def retrieve_ids(self, ids):
        return [str(p.id) for p in self.server.client.retrieve(self.server.collection, ids=ids)]


async def _main(args):
    from app.config import get_settings
    from app.edge.sync.server_client import QdrantServerClient
    from app.llm.embedding import get_embedding_service

    settings = get_settings()
    data = json.loads((Path(args.seed_dir) / args.file).read_text())
    server = QdrantServerClient(settings.qdrant_url, settings.qdrant_collection, settings.qdrant_api_key)
    embed = get_embedding_service()
    try:
        server.ensure_collection(settings.embedding_dimension)
        print(json.dumps(await seed(ServerAdapter(server), embed, data)))
    finally:
        await embed.close()
        server.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED))
    parser.add_argument("--file", default="fleet.json")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    main()
