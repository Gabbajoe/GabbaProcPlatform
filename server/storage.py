import sqlite3, os, hashlib, secrets, time
from contextlib import contextmanager
from pathlib import Path
from .config import postgres_enabled


@contextmanager
def connect():
    if postgres_enabled():
        from .postgres import connection

        with connection() as db:
            yield db
        return
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
        schema = """
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS invites(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS owners(character TEXT PRIMARY KEY, device TEXT NOT NULL REFERENCES devices(id), privacy TEXT NOT NULL, name TEXT, realm TEXT);
CREATE TABLE IF NOT EXISTS snapshots(character TEXT NOT NULL REFERENCES owners(character), collection TEXT NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL, exported INTEGER NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(character,collection));
CREATE TABLE IF NOT EXISTS totals(character TEXT NOT NULL, collection TEXT NOT NULL, spell INTEGER NOT NULL, area TEXT NOT NULL, procs INTEGER NOT NULL, combat INTEGER NOT NULL, seconds REAL NOT NULL, PRIMARY KEY(character,collection,spell,area), FOREIGN KEY(character,collection) REFERENCES snapshots(character,collection) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS segments(character TEXT NOT NULL, collection TEXT NOT NULL, id INTEGER NOT NULL, sequence INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(character,collection,id), FOREIGN KEY(character,collection) REFERENCES snapshots(character,collection) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS archive_usage(character TEXT NOT NULL, collection TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(character,collection), FOREIGN KEY(character,collection) REFERENCES snapshots(character,collection) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS account_identities(provider TEXT NOT NULL, subject TEXT NOT NULL, account TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, display TEXT NOT NULL, PRIMARY KEY(provider,subject));
CREATE TABLE IF NOT EXISTS account_profiles(account TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS account_sessions(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS account_devices(device TEXT PRIMARY KEY REFERENCES devices(id), account TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS auth_flows(hash TEXT PRIMARY KEY, binding TEXT NOT NULL, provider TEXT NOT NULL, payload TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS device_links(hash TEXT PRIMARY KEY, user_code TEXT UNIQUE NOT NULL, account TEXT REFERENCES accounts(id) ON DELETE CASCADE, device TEXT REFERENCES devices(id), expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS device_reconnects(hash TEXT PRIMARY KEY REFERENCES device_links(hash) ON DELETE CASCADE, device TEXT NOT NULL REFERENCES devices(id));
CREATE INDEX IF NOT EXISTS account_sessions_expiry ON account_sessions(expires);
CREATE INDEX IF NOT EXISTS auth_flows_expiry ON auth_flows(expires);
CREATE INDEX IF NOT EXISTS device_links_expiry ON device_links(expires);
CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, started INTEGER NOT NULL, count INTEGER NOT NULL);
"""
        if postgres_enabled():
            schema = schema.replace("INTEGER", "BIGINT").replace(
                " REAL", " DOUBLE PRECISION"
            )
        db.executescript(schema)


def lock(db, key):
    """Serialize a logical operation within its transaction on PostgreSQL."""
    if postgres_enabled():
        number = int.from_bytes(
            hashlib.sha256(key.encode()).digest()[:8], "big", signed=True
        )
        db.execute("SELECT pg_advisory_xact_lock(?)", (number,))


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
