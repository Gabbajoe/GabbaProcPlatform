"""Small, process-local cache for anonymous aggregate responses only."""
import os
import threading
import time
from collections import OrderedDict
from fastapi import HTTPException

_lock = threading.Lock()
_entries = OrderedDict()


def cached(key, calculate):
    namespace = (os.environ.get('GABBAPROC_DB'), os.environ.get('GABBAPROC_DATABASE_URL'))
    key = (namespace, key)
    if not _lock.acquire(timeout=0.1):
        raise HTTPException(503, 'Statistics busy; retry shortly', headers={'Retry-After':'2'})
    try:
        old = _entries.get(key)
        if old and old[0] > time.monotonic():
            return old[1]
        result = calculate()
        _entries[key] = (time.monotonic()+15, result)
        _entries.move_to_end(key)
        while len(_entries) > 128:
            _entries.popitem(last=False)
        return result
    finally:
        _lock.release()


def clear():
    with _lock:
        _entries.clear()
