"""Bounded PostgreSQL connections; SQLite remains available for legacy migration.

The adapter preserves the existing repository's positional SQL parameter style.
Only application-owned SQL is passed here, never user-supplied statements.
"""

import os
import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout, TooManyRequests
from fastapi import HTTPException
from .config import value

_pool = None
_lock = threading.Lock()


class Row(dict):
    def __getitem__(self, key):
        return (
            tuple(self.values())[key]
            if isinstance(key, int)
            else super().__getitem__(key)
        )


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (Row(row) for row in self.cursor)


class Database:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        if sql == "BEGIN IMMEDIATE":
            sql = "BEGIN"
        return Cursor(self.connection.execute(sql.replace("?", "%s"), parameters))

    def executemany(self, sql, rows):
        with self.connection.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), rows)

    def executescript(self, sql):
        # Schema files contain statements only, not procedural SQL.
        for statement in sql.split(";"):
            if statement.strip():
                self.connection.execute(statement)

    def commit(self):
        self.connection.commit()


def pool():
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(
                value("GABBAPROC_DATABASE_URL"),
                min_size=1,
                max_size=int(os.environ.get("GABBAPROC_DB_POOL", "8")),
                max_waiting=32,
                timeout=5,
                open=True,
                kwargs={
                    "autocommit": True,
                    "row_factory": dict_row,
                    "options": "-c statement_timeout=15000 -c lock_timeout=5000",
                },
            )
        return _pool


@contextmanager
def connection():
    try:
        with pool().connection() as connection:
            try:
                yield Database(connection)
            finally:
                # Failed requests/workers must never return an open transaction.
                connection.rollback()
    except (PoolTimeout, TooManyRequests, OperationalError):
        raise HTTPException(
            503, "Database temporarily busy", headers={"Retry-After": "2"}
        ) from None


def close_pool():
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
