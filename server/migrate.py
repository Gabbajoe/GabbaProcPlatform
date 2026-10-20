"""Initialize the PostgreSQL schema; optional offline SQLite migration.

Use the migration role, never application credentials. The source is read-only.
"""

import argparse
import sqlite3
from pathlib import Path
from .config import postgres_enabled
from .storage import connect, init, lock
from .upload_queue import initialize

TABLES = ("devices", "invites", "owners", "snapshots", "totals", "segments", "limits")


def migrate(source=None, grant=True):
    if not postgres_enabled():
        raise RuntimeError("A PostgreSQL destination is required")
    init()
    initialize()
    if source:
        source = Path(source).resolve(strict=True)
        with (
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as old,
            connect() as db,
        ):
            if old.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity check failed")
            old.execute("BEGIN")
            db.execute("BEGIN IMMEDIATE")
            lock(db, "sqlite-migration")
            for table in TABLES:
                if db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                    raise RuntimeError(
                        "Destination is not empty; refusing to overwrite data"
                    )
            for table in TABLES:
                cursor = old.execute(f"SELECT * FROM {table}")
                columns = [c[0] for c in cursor.description]
                query = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                expected = 0
                while rows := cursor.fetchmany(500):
                    db.executemany(query, rows)
                    expected += len(rows)
                if (
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    != expected
                ):
                    raise RuntimeError("Migration row count mismatch")
            db.commit()
    if grant:
        with connect() as db:
            db.execute("GRANT USAGE ON SCHEMA public TO gabbaproc_app")
            db.execute(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO gabbaproc_app"
            )
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        type=Path,
        help="Read-only consistent SQLite backup, imports into empty database only",
    )
    args = parser.parse_args()
    migrate(args.sqlite)
    print("Schema ready; optional SQLite import completed")
