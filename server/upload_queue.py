"""Private host-filesystem spool with transactional PostgreSQL import receipts.

A worker holds a row lock for its bounded import. A crash rolls that transaction
back, making the job available again; no in-memory queue or fragile lease needed.
"""

import fcntl
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from .models import Upload
from .storage import connect, digest, lock
from .config import postgres_enabled


def initialize():
    with connect() as db:
        db.executescript("""
CREATE TABLE IF NOT EXISTS upload_jobs (
 id TEXT PRIMARY KEY, device TEXT NOT NULL REFERENCES devices(id),
 character TEXT NOT NULL, collection TEXT NOT NULL,
 checksum TEXT NOT NULL, size BIGINT NOT NULL,
 status TEXT NOT NULL, created BIGINT NOT NULL, updated BIGINT NOT NULL,
 available BIGINT NOT NULL, attempts BIGINT NOT NULL DEFAULT 0,
 result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS upload_jobs_ready ON upload_jobs(status,available,created);
CREATE INDEX IF NOT EXISTS upload_jobs_device ON upload_jobs(device,character);
""")


def root():
    value = os.environ.get("GABBAPROC_SPOOL")
    if not value:
        raise HTTPException(503, "Upload queue is not configured")
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def spool_lock(path):
    with (path / ".lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        yield


def receipt(row):
    result = {"jobId": row["id"], "status": row["status"]}
    if row["result"]:
        result["result"] = json.loads(row["result"])
    if row["error"]:
        result["error"] = row["error"]
    return result


def enqueue(did, data):
    if not postgres_enabled():
        raise HTTPException(503, "Queued uploads require PostgreSQL")
    from .budgets import ingest_rate
    ingest_rate(did)
    if data.exportedAt > time.time() + 86400:
        raise HTTPException(422, "Export is dated in the future")
    raw = json.dumps(
        data.model_dump(exclude_none=True), sort_keys=True, separators=(",", ":")
    ).encode()
    checksum = digest(raw.decode())
    job_id = digest(did + ":" + checksum)
    path = root()
    destination = path / (job_id + ".json")
    now = int(time.time())
    with spool_lock(path), connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "device:" + did)
        if not db.execute(
            "SELECT id FROM devices WHERE id=? AND revoked=0", (did,)
        ).fetchone():
            raise HTTPException(401, "Upload token revoked")
        old = db.execute(
            "SELECT * FROM upload_jobs WHERE id=? AND device=?", (job_id, did)
        ).fetchone()
        if old:
            return receipt(old)
        total = db.execute(
            "SELECT COALESCE(SUM(size),0) FROM upload_jobs WHERE status='queued'"
        ).fetchone()[0]
        own = db.execute(
            "SELECT COALESCE(SUM(size),0) FROM upload_jobs WHERE status='queued' AND device=?",
            (did,),
        ).fetchone()[0]
        jobs = db.execute(
            "SELECT COUNT(*) FROM upload_jobs WHERE status='queued'"
        ).fetchone()[0]
        if jobs >= int(os.environ.get("GABBAPROC_QUEUE_JOBS", "10000")):
            raise HTTPException(
                503, "Upload queue temporarily full", headers={"Retry-After": "60"}
            )
        if own + len(raw) > int(
            os.environ.get("GABBAPROC_QUEUE_DEVICE_BYTES", str(64 * 1024**2))
        ):
            raise HTTPException(
                429, "Device queue capacity reached", headers={"Retry-After": "60"}
            )
        # Include orphan files, not only the database ledger, in the disk budget.
        disk_bytes = sum(p.stat().st_size for p in path.glob("*.json"))
        maximum = int(os.environ.get("GABBAPROC_QUEUE_BYTES", str(1024**3)))
        reserve = int(os.environ.get("GABBAPROC_DISK_RESERVE", str(512 * 1024**2)))
        if max(total, disk_bytes) + len(raw) > maximum or shutil.disk_usage(
            path
        ).free < reserve + len(raw):
            raise HTTPException(
                503, "Upload storage temporarily full", headers={"Retry-After": "60"}
            )
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            sync_directory(path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        db.execute(
            "INSERT INTO upload_jobs(id,device,character,collection,checksum,size,status,created,updated,available) "
            "VALUES(?,?,?,?,?,?,'queued',?,?,?)",
            (
                job_id,
                did,
                data.characterId,
                data.collectionId,
                checksum,
                len(raw),
                now,
                now,
                now,
            ),
        )
        db.commit()
    return {"jobId": job_id, "status": "queued"}


def get_status(did, job_id):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM upload_jobs WHERE id=? AND device=?", (job_id, did)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Upload job not found")
    return receipt(row)


def cancel_jobs(db, did, character=None):
    condition = " AND character=?" if character else ""
    parameters = (
        (int(time.time()), did, character) if character else (int(time.time()), did)
    )
    db.execute(
        "UPDATE upload_jobs SET status='cancelled',updated=?,error='Access or visibility changed' "
        "WHERE device=? AND status='queued'" + condition,
        parameters,
    )


def process_one():
    from .app import apply_snapshot

    if not postgres_enabled():
        raise RuntimeError("Worker requires PostgreSQL")
    now = int(time.time())
    with connect() as db:
        candidate = db.execute(
            "SELECT id,device FROM upload_jobs WHERE status='queued' AND available<=? ORDER BY available,created LIMIT 1",
            (now,),
        ).fetchone()
    if not candidate:
        return False
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Same lock order as revocation/privacy/import: device before job.
            lock(db, "device:" + candidate["device"])
            row = db.execute(
                "SELECT * FROM upload_jobs WHERE id=? AND status='queued' AND available<=? FOR UPDATE SKIP LOCKED",
                (candidate["id"], now),
            ).fetchone()
            if not row:
                return False
            source = root() / (row["id"] + ".json")
            if (
                not source.is_file()
                or source.is_symlink()
                or source.stat().st_size != row["size"]
            ):
                raise OSError("Missing or invalid spool file")
            raw = source.read_bytes()
            if digest(raw.decode()) != row["checksum"]:
                raise ValueError("Spool checksum mismatch")
            data = Upload.model_validate_json(raw)
            # A savepoint lets invalid imports leave a durable rejection receipt.
            db.execute("SAVEPOINT import_payload")
            try:
                result = apply_snapshot(db, row["device"], data)
            except HTTPException as error:
                if error.status_code >= 500 or error.status_code == 429:
                    raise
                db.execute("ROLLBACK TO SAVEPOINT import_payload")
                db.execute(
                    "UPDATE upload_jobs SET status='rejected',error=?,updated=?,attempts=attempts+1 WHERE id=?",
                    (str(error.detail), now, row["id"]),
                )
            else:
                db.execute(
                    "UPDATE upload_jobs SET status='processed',result=?,updated=?,attempts=attempts+1 WHERE id=?",
                    (json.dumps(result), now, row["id"]),
                )
            db.commit()
        from .public_cache import clear
        clear()
        # Deletion only AFTER the import and receipt have committed together.
        with spool_lock(source.parent):
            source.unlink(missing_ok=True)
            sync_directory(source.parent)
        return True
    except Exception:
        # Never include a raw payload, name, token or database DSN in logs/receipts.
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            lock(db, "device:" + candidate["device"])
            row = db.execute(
                "SELECT * FROM upload_jobs WHERE id=? FOR UPDATE", (candidate["id"],)
            ).fetchone()
            if row and row["status"] == "queued":
                attempts = row["attempts"] + 1
                db.execute(
                    "UPDATE upload_jobs SET attempts=?,available=?,updated=?,status=?,error=? WHERE id=?",
                    (
                        attempts,
                        now + min(3600, 2 ** min(attempts, 11)),
                        now,
                        "failed" if attempts >= 10 else "queued",
                        "Import temporarily failed; operator can retry",
                        row["id"],
                    ),
                )
                db.commit()
        return False


def cleanup():
    """Remove post-commit leftovers; never discard a queued/failed job payload."""
    path = root()
    with spool_lock(path), connect() as db:
        for file in path.glob("*.json"):
            row = db.execute(
                "SELECT status FROM upload_jobs WHERE id=?", (file.stem,)
            ).fetchone()
            if row and row["status"] in {"processed", "rejected", "cancelled"}:
                file.unlink(missing_ok=True)
            elif not row and time.time() - file.stat().st_mtime > 86400:
                # No receipt was committed; client is responsible for retrying.
                file.unlink(missing_ok=True)
        for file in path.glob(".pending-*"):
            if time.time() - file.stat().st_mtime > 86400:
                file.unlink(missing_ok=True)
        sync_directory(path)
        db.execute("DELETE FROM upload_jobs WHERE status IN ('processed','rejected','cancelled') AND updated<?", (int(time.time()) - 90*86400,))
