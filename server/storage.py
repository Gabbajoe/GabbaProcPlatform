import sqlite3, os, hashlib, secrets, time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect():
    path = Path(os.environ.get("GABBAPROC_DB", "data/procs.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
    finally:
        db.close()


def init():
    with connect() as db:
        db.executescript("""
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS owners(character TEXT PRIMARY KEY, device TEXT NOT NULL REFERENCES devices(id), privacy TEXT NOT NULL, name TEXT, realm TEXT);
CREATE TABLE IF NOT EXISTS snapshots(character TEXT NOT NULL REFERENCES owners(character), collection TEXT NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL, exported INTEGER NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(character,collection));
CREATE TABLE IF NOT EXISTS totals(character TEXT NOT NULL, collection TEXT NOT NULL, spell INTEGER NOT NULL, area TEXT NOT NULL, procs INTEGER NOT NULL, combat INTEGER NOT NULL, seconds REAL NOT NULL, PRIMARY KEY(character,collection,spell,area), FOREIGN KEY(character,collection) REFERENCES snapshots(character,collection) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS segments(character TEXT NOT NULL, collection TEXT NOT NULL, id INTEGER NOT NULL, sequence INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(character,collection,id), FOREIGN KEY(character,collection) REFERENCES snapshots(character,collection) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, started INTEGER NOT NULL, count INTEGER NOT NULL);
""")


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def invite():
    value = secrets.token_urlsafe(24)
    with connect() as db:
        db.execute(
            "INSERT INTO invites VALUES(?,?,0)",
            (digest(value), int(time.time()) + 86400),
        )
    return value
