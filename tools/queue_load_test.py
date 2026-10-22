#!/usr/bin/env python3
"""Local ASGI/PostgreSQL burst test; never use against production.

Creates 200 independent devices, concurrently submits one snapshot per device,
replays every request, processes the queue and verifies exactly 200 imports.
This measures application contention, not network/proxy or production hardware.
"""

import asyncio
import json
import os
from pathlib import Path
import secrets
import random
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from server.app import app
from server.storage import connect, digest, init
from server.upload_queue import initialize, process_one


async def main():
    if not os.environ.get("GABBAPROC_DATABASE_URL"):
        raise SystemExit(
            "Set GABBAPROC_DATABASE_URL to a dedicated PostgreSQL test database"
        )
    with connect() as db:
        if not db.execute("SELECT current_database()").fetchone()[0].endswith("_test"):
            raise SystemExit("Database must end in _test")
    init()
    initialize()
    with connect() as db:
        db.execute(
            "TRUNCATE devices,owners,snapshots,totals,segments,limits,upload_jobs CASCADE"
        )
    users = []
    for _ in range(200):
        token = secrets.token_urlsafe(32)
        did = secrets.token_hex(16)
        with connect() as db:
            db.execute(
                "INSERT INTO devices(id,token_hash,created) VALUES(?,?,?)",
                (did, digest(token), int(time.time())),
            )
        users.append(
            (
                token,
                {
                    "schemaVersion": 1,
                    "addonVersion": "0.1.1",
                    "characterId": str(uuid.uuid4()),
                    "collectionId": str(uuid.uuid4()),
                    "sequence": 1,
                    "exportedAt": int(time.time()),
                    "privacy": "anonymous",
                    "historyTruncated": False,
                    "totals": [
                        {
                            "spellId": 20007,
                            "group": "world",
                            "procs": 1,
                            "combatProcs": 1,
                            "combatSeconds": 60.0,
                        }
                    ],
                    "segments": [
                        {
                            "id": 1,
                            "group": "world",
                            "seconds": 60.0,
                            "status": "complete",
                            "rows": [{"spellId": 20007, "procs": 1, "eligible": True}],
                        }
                    ],
                },
            )
        )
    elapsed = []
    retries = 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def submit(user):
            nonlocal retries
            token, data = user
            begin = time.perf_counter()
            for attempt in range(10):
                response = await client.post(
                    "/api/upload-jobs",
                    json=data,
                    headers={"Authorization": "Bearer " + token},
                )
                if response.status_code not in (429, 503):
                    break
                retries += 1
                await asyncio.sleep(
                    float(response.headers.get("Retry-After", "2")) + random.random()
                )
            assert response.status_code == 202, (response.status_code, response.text)
            elapsed.append(time.perf_counter() - begin)
            return response.json()["jobId"]

        first = await asyncio.gather(*(submit(u) for u in users))
        replay = await asyncio.gather(*(submit(u) for u in users))
        assert first == replay
    start = time.perf_counter()
    count = 0
    while process_one():
        count += 1
    duration = time.perf_counter() - start
    with connect() as db:
        assert count == 200
        assert (
            db.execute(
                "SELECT COUNT(*) FROM upload_jobs WHERE status='processed'"
            ).fetchone()[0]
            == 200
        )
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 200
        assert db.execute("SELECT SUM(procs) FROM totals").fetchone()[0] == 200
    print(
        json.dumps(
            {
                "clients": 200,
                "requests_including_replays": 400 + retries,
                "retryable_overload_responses": retries,
                "unique_imports": count,
                "http_p95_seconds": round(sorted(elapsed)[379], 3),
                "worker_seconds_without_configured_pacing": round(duration, 3),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="gabbaproc-load-") as spool:
        os.environ["GABBAPROC_SPOOL"] = spool
        try:
            asyncio.run(main())
        finally:
            from server.postgres import close_pool

            close_pool()
