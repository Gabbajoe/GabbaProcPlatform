#!/usr/bin/env python3
"""Host-side consistent PostgreSQL dump plus pending upload files.

Queue writers and post-commit cleanup share this filesystem lock. Workers may
commit during the dump, but files cannot disappear until the snapshot is saved.
Run with private host directories, not inside the webroot.
"""

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import tarfile
import time


def backup(engine, container, database, user, spool, backups):
    os.umask(0o077)
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    temporary = backups / (".pending-" + stamp)
    temporary.mkdir(mode=0o700)
    with (spool / ".lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        with (temporary / "database.dump").open("wb") as output:
            subprocess.run(
                [engine, "exec", container, "pg_dump", "-U", user, "-Fc", database],
                stdout=output,
                check=True,
            )
            output.flush()
            os.fsync(output.fileno())
        with tarfile.open(temporary / "spool.tar", "w") as archive:
            for file in sorted(spool.glob("*.json")):
                if file.is_symlink() or not file.is_file():
                    raise RuntimeError("Unexpected spool entry")
                archive.add(file, arcname=file.name, recursive=False)
        with (temporary / "spool.tar").open("rb") as archive:
            os.fsync(archive.fileno())
    target = backups / ("postgres-" + stamp)
    fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(temporary, target)
    fd = os.open(backups, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    parser.add_argument("--container", required=True)
    parser.add_argument("--database", default="gabbaproc")
    parser.add_argument("--user", default="gabbaproc_admin")
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--backups", type=Path, required=True)
    args = parser.parse_args()
    backup(
        args.engine,
        args.container,
        args.database,
        args.user,
        args.spool.resolve(strict=True),
        args.backups.resolve(),
    )
