"""Shared account budgets for both synchronous and queued imports."""
import os
from fastapi import HTTPException
from .storage import lock


def owner_key(db, did):
    row = db.execute('SELECT account FROM account_devices WHERE device=?', (did,)).fetchone()
    return ('account', row['account']) if row else ('device', did)


def check_storage(db, did):
    kind, owner = owner_key(db, did)
    condition = 'o.device=?' if kind == 'device' else 'o.device IN (SELECT device FROM account_devices WHERE account=?)'
    row = db.execute('SELECT COALESCE(SUM(u.bytes),0) bytes,COALESCE(SUM(u.segments),0) segments,COUNT(*) collections FROM snapshots s JOIN owners o ON o.character=s.character LEFT JOIN storage_usage u ON u.character=s.character AND u.collection=s.collection WHERE '+condition, (owner,)).fetchone()
    if (row['bytes'] > int(os.environ.get('GABBAPROC_ACCOUNT_BYTES', str(128*1024**2)))
        or row['segments'] > int(os.environ.get('GABBAPROC_ACCOUNT_SEGMENTS', '50000'))
        or row['collections'] > int(os.environ.get('GABBAPROC_ACCOUNT_COLLECTIONS', '200'))):
        raise HTTPException(413, 'Account storage limit reached; contact the operator')


def ingest_rate(did):
    from .storage import connect
    from .app import rate
    with connect() as db:
        kind, owner = owner_key(db, did)
    rate('ingest:'+kind+':'+owner, int(os.environ.get('GABBAPROC_ACCOUNT_IMPORTS_HOUR','2000')))
