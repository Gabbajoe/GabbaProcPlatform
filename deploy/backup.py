#!/usr/bin/env python3
"""Daily private, SQLite-consistent backup; seven-day retention."""

import os
import sqlite3
import time
from pathlib import Path

os.umask(0o077)
root = Path("/var/backups/gabbaproc")
root.mkdir(mode=0o700, parents=True, exist_ok=True)
now = int(time.time())
target = root / ("procs-%s.sqlite3" % now)
with sqlite3.connect(
    "file:/var/lib/gabbaproc/procs.sqlite3?mode=ro", uri=True
) as source:
    with sqlite3.connect(str(target)) as backup:
        source.backup(backup)
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
for old in root.glob("procs-*.sqlite3"):
    if old.is_file() and old.stat().st_mtime < now - 7 * 86400:
        old.unlink()
print("Private backup verified; seven-day retention applied")
