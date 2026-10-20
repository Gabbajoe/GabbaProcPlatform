import hashlib, json, os, secrets, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .models import Upload, CATALOG
from .storage import init, connect, digest, lock
from starlette.concurrency import run_in_threadpool
from . import upload_queue
from .config import postgres_enabled


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("GABBAPROC_AUTO_INIT", "true") == "true":
        await run_in_threadpool(init)
        await run_in_threadpool(upload_queue.initialize)
    yield
    if postgres_enabled():
        from .postgres import close_pool

        await run_in_threadpool(close_pool)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
MAX_BODY = 2 * 1024 * 1024


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
    )
    return response


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("duplicate key")
        result[k] = v
    return result


async def body(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "JSON required")
    if request.headers.get("content-encoding", "identity") != "identity":
        raise HTTPException(415, "compressed bodies not accepted")
    parts = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise HTTPException(413, "Upload too large")
        parts.append(chunk)
    try:
        result = json.loads(
            b"".join(parts),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, "Invalid JSON")


def rate(key, maximum, period=3600):
    now = int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM limits WHERE started < ?", (now - 86400,))
        lock(db, "rate:" + key)
        old = db.execute("SELECT * FROM limits WHERE key=?", (key,)).fetchone()
        if old and now - old["started"] < period:
            if old["count"] >= maximum:
                raise HTTPException(
                    429, "Please retry later", headers={"Retry-After": str(period)}
                )
            db.execute("UPDATE limits SET count=count+1 WHERE key=?", (key,))
        else:
            db.execute(
                "INSERT INTO limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET started=excluded.started,count=1",
                (key, now),
            )
        db.commit()


def device(request, maximum=120, kind="device"):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not 30 < len(auth) < 150:
        raise HTTPException(401, "Upload token required")
    with connect() as db:
        row = db.execute(
            "SELECT id FROM devices WHERE token_hash=? AND revoked=0",
            (digest(auth[7:]),),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Upload token invalid or revoked")
    rate(kind + ":" + row["id"], maximum)
    return row["id"]


@app.get("/api/health")
def health():
    return {"ok": True, "schemaVersion": 1}


@app.post("/api/enroll")
async def enroll(request: Request):
    # Invites are single-use, expire after a day, and are issued by the operator.
    # Public automated registration is deliberately not enabled without abuse controls.
    await run_in_threadpool(rate, "enroll:" + digest(request.client.host), 10)
    data = await body(request)
    if (
        set(data) != {"invite"}
        or not isinstance(data["invite"], str)
        or len(data["invite"]) > 100
    ):
        raise HTTPException(400, "Invalid invite")
    return await run_in_threadpool(enroll_invite, data)


def enroll_invite(data):
    token = secrets.token_urlsafe(32)
    did = secrets.token_hex(16)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        updated = db.execute(
            "UPDATE invites SET used=1 WHERE hash=? AND used=0 AND expires>?",
            (digest(data["invite"]), int(time.time())),
        ).rowcount
        if not updated:
            raise HTTPException(403, "Invite expired or already used")
        db.execute(
            "INSERT INTO devices(id,token_hash,created) VALUES(?,?,?)",
            (did, digest(token), int(time.time())),
        )
        db.commit()
    return {"token": token}


@app.post("/api/imports")
async def upload(request: Request):
    did = await run_in_threadpool(device, request)
    try:
        data = Upload.model_validate(await body(request))
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid export fields, counters or history")
    return await run_in_threadpool(import_snapshot, did, data)


@app.post("/api/upload-jobs", status_code=202)
async def queue_upload(request: Request):
    did = await run_in_threadpool(device, request, 600, "uploads")
    try:
        data = Upload.model_validate(await body(request))
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid export fields, counters or history")
    return await run_in_threadpool(upload_queue.enqueue, did, data)


@app.get("/api/upload-jobs/{job_id}")
def upload_status(request: Request, job_id: str):
    did = device(request, 3600, "job-status")
    return upload_queue.get_status(did, job_id)


def import_snapshot(did, data):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        result = apply_snapshot(db, did, data)
        db.commit()
        return result


def apply_snapshot(db, did, data):
    if data.exportedAt > time.time() + 86400:
        raise HTTPException(422, "Export is dated in the future")
    content = json.dumps(
        data.model_dump(exclude_none=True, exclude={"privacy", "name", "realm"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    checksum = digest(content)
    suspicious = any(
        (r.combatSeconds > 0 and r.combatProcs * 60 / r.combatSeconds > 600)
        or (r.combatSeconds == 0 and r.procs > 1000)
        for r in data.totals
    )
    status = "quarantine" if suspicious else "community"
    key = (data.characterId, data.collectionId)
    lock(db, "device:" + did)
    lock(db, "character:" + data.characterId)
    active_device = db.execute(
        "SELECT id FROM devices WHERE id=? AND revoked=0", (did,)
    ).fetchone()
    if not active_device:
        raise HTTPException(401, "Upload token revoked")
    owner = db.execute(
        "SELECT * FROM owners WHERE character=?", (data.characterId,)
    ).fetchone()
    if owner and owner["device"] != did:
        raise HTTPException(
            409,
            "Character belongs to another upload device; contact operator to transfer",
        )
    old = db.execute(
        "SELECT * FROM snapshots WHERE character=? AND collection=?", key
    ).fetchone()
    if old and data.sequence < old["sequence"]:
        raise HTTPException(409, "Older snapshot")
    if old and data.sequence == old["sequence"]:
        if old["digest"] != checksum:
            raise HTTPException(409, "Sequence reused with different content")
        db.execute(
            "UPDATE owners SET privacy=?,name=?,realm=? WHERE character=? AND device=?",
            (data.privacy, data.name, data.realm, data.characterId, did),
        )
        return {"status": "duplicate", "review": old["status"]}
    if not old:
        if (
            db.execute(
                "SELECT COUNT(*) FROM snapshots s JOIN owners o ON o.character=s.character WHERE o.device=?",
                (did,),
            ).fetchone()[0]
            >= 200
        ):
            raise HTTPException(429, "Collection limit reached")
    if old:
        incoming = {(r.spellId, r.group): r for r in data.totals}
        for previous in db.execute(
            "SELECT * FROM totals WHERE character=? AND collection=?", key
        ):
            new = incoming.get((previous["spell"], previous["area"]))
            if (
                not new
                or new.procs < previous["procs"]
                or new.combatProcs < previous["combat"]
                or new.combatSeconds + 0.01 < previous["seconds"]
            ):
                raise HTTPException(409, "Counters decreased within collection")
    db.execute(
        "INSERT INTO owners VALUES(?,?,?,?,?) ON CONFLICT(character) DO UPDATE SET privacy=excluded.privacy,name=excluded.name,realm=excluded.realm",
        (data.characterId, did, data.privacy, data.name, data.realm),
    )
    db.execute(
        "INSERT INTO snapshots VALUES(?,?,?,?,?,?,?) ON CONFLICT(character,collection) DO UPDATE SET sequence=excluded.sequence,digest=excluded.digest,status=excluded.status,exported=excluded.exported,updated=excluded.updated",
        (*key, data.sequence, checksum, status, data.exportedAt, int(time.time())),
    )
    db.execute("DELETE FROM totals WHERE character=? AND collection=?", key)
    db.executemany(
        "INSERT INTO totals VALUES(?,?,?,?,?,?,?)",
        [
            (*key, r.spellId, r.group, r.procs, r.combatProcs, r.combatSeconds)
            for r in data.totals
        ],
    )
    for segment in data.segments:
        previous = db.execute(
            "SELECT sequence,data FROM segments WHERE character=? AND collection=? AND id=?",
            (*key, segment.id),
        ).fetchone()
        value = segment.model_dump()
        if previous:
            before = json.loads(previous["data"])
            if before == value:
                continue
            if before["status"] == "complete":
                raise HTTPException(409, "Completed segment changed")
            if previous["sequence"] >= data.sequence:
                raise HTTPException(409, "Conflicting segment revision")
            old_rows = {row["spellId"]: row for row in before["rows"]}
            new_rows = {row["spellId"]: row for row in value["rows"]}
            if (
                before["group"] != value["group"]
                or value["seconds"] < before["seconds"]
                or any(
                    k not in new_rows
                    or new_rows[k]["procs"] < v["procs"]
                    or new_rows[k]["eligible"] != v["eligible"]
                    for k, v in old_rows.items()
                )
            ):
                raise HTTPException(409, "Segment counters decreased")
        db.execute(
            "INSERT INTO segments VALUES(?,?,?,?,?) ON CONFLICT(character,collection,id) "
            "DO UPDATE SET sequence=excluded.sequence,data=excluded.data",
            (*key, segment.id, data.sequence, json.dumps(value)),
        )
    return {"status": "accepted", "review": status, "sequence": data.sequence}


@app.post("/api/privacy")
async def privacy(request: Request):
    did = await run_in_threadpool(device, request)
    data = await body(request)
    if set(data) != {"characterId"} or not isinstance(data["characterId"], str):
        raise HTTPException(400, "characterId required")
    return await run_in_threadpool(hide_character, did, data["characterId"])


def hide_character(did, character):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "device:" + did)
        upload_queue.cancel_jobs(db, did, character)
        n = db.execute(
            "UPDATE owners SET privacy='anonymous',name=NULL,realm=NULL WHERE character=? AND device=?",
            (character, did),
        ).rowcount
        db.commit()
    if not n:
        raise HTTPException(404, "Character not found")
    return {"status": "anonymous"}


@app.delete("/api/device")
def remove_device(request: Request):
    did = device(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "device:" + did)
        upload_queue.cancel_jobs(db, did)
        chars = [
            r[0]
            for r in db.execute("SELECT character FROM owners WHERE device=?", (did,))
        ]
        for char in chars:
            db.execute("DELETE FROM snapshots WHERE character=?", (char,))
        db.execute("DELETE FROM owners WHERE device=?", (did,))
        db.execute("UPDATE devices SET revoked=1 WHERE id=?", (did,))
        db.commit()
    return {"status": "deleted"}


@app.get("/api/stats")
def stats():
    with connect() as db:
        rows = db.execute(
            """SELECT t.spell,t.area,SUM(t.procs) procs,SUM(t.combat) combat,SUM(t.seconds) seconds,COUNT(DISTINCT t.character) contributors FROM totals t JOIN snapshots s USING(character,collection) WHERE s.status='community' GROUP BY t.spell,t.area ORDER BY t.spell,t.area"""
        ).fetchall()
        meta = dict(
            db.execute(
                "SELECT COUNT(*) collections,COUNT(DISTINCT character) contributors,MAX(updated) updated FROM snapshots WHERE status='community'"
            ).fetchone()
        )
        names = [
            dict(r)
            for r in db.execute(
                "SELECT DISTINCT o.name,o.realm FROM owners o JOIN snapshots s ON s.character=o.character WHERE o.privacy='named' AND s.status='community' ORDER BY o.name LIMIT 100"
            )
        ]
    return {
        "meta": meta,
        "rows": [
            {
                "spellId": r["spell"],
                "name": CATALOG[str(r["spell"])],
                "group": r["area"],
                "procs": int(r["procs"]),
                "combatProcs": int(r["combat"]),
                "seconds": r["seconds"],
                "contributors": r["contributors"],
                "ppm": int(r["combat"]) * 60 / r["seconds"] if r["seconds"] else None,
            }
            for r in rows
        ],
        "contributors": names,
    }


ROOT = Path(__file__).resolve().parents[1] / "web"
app.mount(
    "/assets", StaticFiles(directory=ROOT / "assets", check_dir=False), name="assets"
)


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/{page}.html")
def portal_page(page: str):
    if page not in {"compare", "quality", "downloads", "account"}:
        raise HTTPException(404, "Page not found")
    return FileResponse(ROOT / (page + ".html"))
