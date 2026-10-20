import copy, json, time, uuid, os
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server.storage import invite, connect


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("GABBAPROC_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("GABBAPROC_SPOOL", str(tmp_path / "spool"))
    if os.environ.get("GABBAPROC_TEST_DATABASE_URL"):
        from server.postgres import close_pool
        from server.storage import init

        close_pool()
        monkeypatch.setenv(
            "GABBAPROC_DATABASE_URL", os.environ["GABBAPROC_TEST_DATABASE_URL"]
        )
        with connect() as db:
            assert (
                db.execute("SELECT current_database()").fetchone()[0].endswith("_test")
            ), "Test database name must end in _test"
        init()
        with connect() as db:
            db.execute(
                "TRUNCATE devices,invites,owners,snapshots,totals,segments,limits CASCADE"
            )
    with TestClient(app) as c:
        token = c.post("/api/enroll", json={"invite": invite()}).json()["token"]
        c.headers["Authorization"] = "Bearer " + token
        yield c
    if os.environ.get("GABBAPROC_TEST_DATABASE_URL"):
        close_pool()


@pytest.fixture
def sample():
    return {
        "schemaVersion": 1,
        "addonVersion": "0.1.0",
        "characterId": str(uuid.uuid4()),
        "collectionId": str(uuid.uuid4()),
        "sequence": 1,
        "exportedAt": int(time.time()),
        "privacy": "anonymous",
        "historyTruncated": False,
        "totals": [
            {
                "spellId": 20007,
                "group": "world",
                "procs": 2,
                "combatProcs": 2,
                "combatSeconds": 120.0,
            }
        ],
        "segments": [
            {
                "id": 1,
                "group": "world",
                "seconds": 120.0,
                "status": "complete",
                "rows": [{"spellId": 20007, "procs": 2, "eligible": True}],
            }
        ],
    }


def test_import_dedup_update_and_weighted_rate(api, sample):
    assert api.post("/api/imports", json=sample).json()["status"] == "accepted"
    assert api.post("/api/imports", json=sample).json()["status"] == "duplicate"
    data = api.get("/api/stats").json()
    assert data["rows"][0]["ppm"] == 1
    sample["sequence"] = 2
    sample["totals"][0]["combatSeconds"] = 240.0
    assert api.post("/api/imports", json=sample).status_code == 200
    assert api.get("/api/stats").json()["rows"][0]["ppm"] == 0.5
    sample["sequence"] = 1
    assert api.post("/api/imports", json=sample).status_code == 409


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x.update(privacy="anonymous", name="Private"),
        lambda x: x.update(unexpected="evil"),
        lambda x: x["totals"][0].update(procs=-1),
        lambda x: x["totals"][0].update(spellId=999999),
        lambda x: x["totals"][0].update(combatSeconds=0.0),
        lambda x: x["totals"].append(x["totals"][0]),
        lambda x: x["segments"][0]["rows"][0].update(procs=3),
        lambda x: x.update(privacy="named", name="<script>", realm="Realm"),
        lambda x: x["totals"][0].update(procs=True),
    ],
)
def test_invalid_payloads(api, sample, mutate):
    mutate(sample)
    assert api.post("/api/imports", json=sample).status_code == 422
    assert api.get("/api/stats").json()["meta"]["collections"] == 0


def test_identity_and_privacy(api, sample):
    sample.update(privacy="named", name="Tester", realm="Test Realm")
    assert api.post("/api/imports", json=sample).status_code == 200
    assert api.get("/api/stats").json()["contributors"] == [
        {"name": "Tester", "realm": "Test Realm"}
    ]
    public = api.get("/api/stats").text
    assert sample["characterId"] not in public and sample["collectionId"] not in public
    assert (
        api.post(
            "/api/privacy", json={"characterId": sample["characterId"]}
        ).status_code
        == 200
    )
    assert api.get("/api/stats").json()["contributors"] == []
    other = api.post("/api/enroll", json={"invite": invite()}).json()["token"]
    assert (
        api.post(
            "/api/imports", json=sample, headers={"Authorization": "Bearer " + other}
        ).status_code
        == 409
    )
    assert api.delete("/api/device").status_code == 200
    assert api.get("/api/stats").json()["meta"]["collections"] == 0
    assert api.post("/api/imports", json=sample).status_code == 401


def test_invites_single_use_and_unknown(api):
    code = invite()
    assert api.post("/api/enroll", json={"invite": code}).status_code == 200
    assert api.post("/api/enroll", json={"invite": code}).status_code == 403


def test_quarantine_and_counter_regression(api, sample):
    sample["segments"] = []
    sample["totals"][0].update(procs=500, combatProcs=500, combatSeconds=1.0)
    assert api.post("/api/imports", json=sample).json()["review"] == "quarantine"
    assert api.get("/api/stats").json()["rows"] == []
    sample["sequence"] = 2
    sample["totals"][0]["procs"] = 499
    assert api.post("/api/imports", json=sample).status_code == 422
    sample["totals"][0]["combatProcs"] = 499
    assert api.post("/api/imports", json=sample).status_code == 409


def test_body_limits_and_duplicate_keys(api):
    assert (
        api.post(
            "/api/imports",
            content=b"a" * (2 * 1024 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        api.post(
            "/api/imports",
            content='{"a":1,"a":2}',
            headers={"Content-Type": "application/json"},
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/api/imports",
            content='{"a":NaN}',
            headers={"Content-Type": "application/json"},
        ).status_code
        == 400
    )
    assert api.post("/api/imports", content="print(123)").status_code == 415


def test_visibility_change_does_not_duplicate_snapshot(api, sample):
    assert api.post("/api/imports", json=sample).status_code == 200
    sample.update(privacy="named", name="Tester", realm="Test Realm")
    assert api.post("/api/imports", json=sample).json()["status"] == "duplicate"
    assert len(api.get("/api/stats").json()["contributors"]) == 1
    sample.update(privacy="anonymous")
    sample.pop("name")
    sample.pop("realm")
    assert api.post("/api/imports", json=sample).json()["status"] == "duplicate"
    data = api.get("/api/stats").json()
    assert data["contributors"] == [] and data["rows"][0]["procs"] == 2


def test_history_is_archived_and_completed_segments_are_immutable(api, sample):
    assert api.post("/api/imports", json=sample).status_code == 200
    sample["sequence"] = 2
    sample["segments"][0]["id"] = 2
    sample["totals"][0].update(procs=4, combatProcs=4, combatSeconds=240.0)
    assert api.post("/api/imports", json=sample).status_code == 200
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 2
    sample["sequence"] = 3
    sample["segments"][0]["seconds"] = 121.0
    assert api.post("/api/imports", json=sample).status_code == 409
    with connect() as db:
        assert db.execute("SELECT MAX(sequence) FROM snapshots").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 2


def test_active_segment_can_finish_but_cannot_regress(api, sample):
    sample["segments"][0]["status"] = "active"
    assert api.post("/api/imports", json=sample).status_code == 200

    sample["sequence"] = 2
    sample["segments"][0]["seconds"] = 119.0
    assert api.post("/api/imports", json=sample).status_code == 409
    sample["segments"][0].update(seconds=120.0, status="complete")
    assert api.post("/api/imports", json=sample).status_code == 200


@pytest.mark.skipif(
    not os.environ.get("GABBAPROC_TEST_DATABASE_URL"), reason="Requires real PostgreSQL"
)
def test_durable_queue_receipt_and_duplicate(api, sample):
    from server.upload_queue import process_one, root

    response = api.post("/api/upload-jobs", json=sample)
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert api.get("/api/stats").json()["meta"]["collections"] == 0
    assert len(list(root().glob("*.json"))) == 1
    assert api.post("/api/upload-jobs", json=sample).json() == job
    assert process_one()
    status = api.get("/api/upload-jobs/" + job["jobId"]).json()
    assert status["status"] == "processed"
    assert status["result"]["status"] == "accepted"
    assert not list(root().glob("*.json"))
    assert api.post("/api/upload-jobs", json=sample).json()["status"] == "processed"
    assert api.get("/api/stats").json()["rows"][0]["procs"] == 2


@pytest.mark.skipif(
    not os.environ.get("GABBAPROC_TEST_DATABASE_URL"), reason="Requires real PostgreSQL"
)
def test_queue_revocation_capacity_and_retry(api, sample, monkeypatch):
    from server import upload_queue
    from importlib import import_module

    app_module = import_module("server.app")
    monkeypatch.setenv("GABBAPROC_QUEUE_DEVICE_BYTES", "1")
    assert api.post("/api/upload-jobs", json=sample).status_code == 429
    assert not list(upload_queue.root().glob("*.json"))

    monkeypatch.delenv("GABBAPROC_QUEUE_DEVICE_BYTES")
    job = api.post("/api/upload-jobs", json=sample).json()["jobId"]
    original = app_module.apply_snapshot

    def fail(*args):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(app_module, "apply_snapshot", fail)
    assert not upload_queue.process_one()
    assert api.get("/api/upload-jobs/" + job).json()["status"] == "queued"
    assert len(list(upload_queue.root().glob("*.json"))) == 1
    assert api.get("/api/stats").json()["meta"]["collections"] == 0
    monkeypatch.setattr(app_module, "apply_snapshot", original)
    assert api.delete("/api/device").status_code == 200
    with connect() as db:
        assert (
            db.execute("SELECT status FROM upload_jobs WHERE id=?", (job,)).fetchone()[
                0
            ]
            == "cancelled"
        )
    upload_queue.cleanup()
    assert not list(upload_queue.root().glob("*.json"))


@pytest.mark.skipif(
    not os.environ.get("GABBAPROC_TEST_DATABASE_URL"), reason="Requires real PostgreSQL"
)
def test_sqlite_migration_preserves_measurements_and_tokens(
    api, sample, tmp_path, monkeypatch
):
    from server.migrate import migrate, TABLES
    from server.storage import init

    assert api.post("/api/imports", json=sample).status_code == 200
    with connect() as db:
        original = {
            table: [tuple(row.values()) for row in db.execute(f"SELECT * FROM {table}")]
            for table in TABLES
        }
    source = tmp_path / "migration.sqlite3"
    with monkeypatch.context() as local:
        local.delenv("GABBAPROC_DATABASE_URL")
        local.setenv("GABBAPROC_DB", str(source))
        init()
        with connect() as db:
            for table, rows in original.items():
                if rows:
                    db.executemany(
                        f"INSERT INTO {table} VALUES({','.join('?' for _ in rows[0])})",
                        rows,
                    )
    with connect() as db:
        db.execute(
            "TRUNCATE devices,invites,owners,snapshots,totals,segments,limits,upload_jobs CASCADE"
        )
    migrate(source, grant=False)
    with connect() as db:
        for table, rows in original.items():
            assert [
                tuple(row.values()) for row in db.execute(f"SELECT * FROM {table}")
            ] == rows
    assert api.post("/api/imports", json=sample).json()["status"] == "duplicate"


def test_archive_batches_replay_backfill_and_combined_validation(api, sample):
    sample["schemaVersion"] = 2
    sample["totals"][0].update(procs=400, combatProcs=400, combatSeconds=400.0)
    segment = sample["segments"][0]
    segment.update(seconds=1.0)
    segment["rows"][0]["procs"] = 1
    packets = []
    for start in (1, 101, 201, 301):
        packet = copy.deepcopy(sample)
        packet["segments"] = [
            dict(copy.deepcopy(segment), id=i) for i in range(start, start + 100)
        ]
        packets.append(packet)
    for packet in reversed(packets):
        assert api.post("/api/imports", json=packet).status_code == 200
    for packet in packets:
        assert api.post("/api/imports", json=packet).status_code == 200
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 400
        assert db.execute("SELECT SUM(procs) FROM totals").fetchone()[0] == 400
    # Each packet is individually plausible; the union must also fit the totals.
    overflow = copy.deepcopy(packets[0])
    overflow["segments"] = [dict(copy.deepcopy(segment), id=401)]
    assert api.post("/api/imports", json=overflow).status_code == 409
    newer = copy.deepcopy(packets[-1])
    newer["sequence"] = 3
    newer["totals"][0]["combatSeconds"] = 500.0
    assert api.post("/api/imports", json=newer).status_code == 200
    assert api.post("/api/imports", json=packets[0]).status_code == 200
    with connect() as db:
        assert db.execute("SELECT sequence FROM snapshots").fetchone()[0] == 3
        assert db.execute("SELECT SUM(seconds) FROM totals").fetchone()[0] == 500
    conflict = copy.deepcopy(packets[0])
    conflict["segments"][0]["seconds"] = 2.0
    assert api.post("/api/imports", json=conflict).status_code == 409


def test_archive_active_revision_and_legacy_upgrade(api, sample):
    sample["segments"][0]["status"] = "active"
    assert api.post("/api/imports", json=sample).status_code == 200
    sample["schemaVersion"] = 2
    assert api.post("/api/imports", json=sample).status_code == 200
    complete = copy.deepcopy(sample)
    complete["sequence"] = 2
    complete["segments"][0]["status"] = "complete"
    assert api.post("/api/imports", json=complete).status_code == 200
    # Delayed active snapshot must not resurrect an already completed segment.
    assert api.post("/api/imports", json=sample).status_code == 200
    with connect() as db:
        assert (
            json.loads(db.execute("SELECT data FROM segments").fetchone()[0])["status"]
            == "complete"
        )


def test_archive_privacy_change_on_same_sequence(api, sample):
    sample["schemaVersion"] = 2
    sample.update(privacy="named", name="Tester", realm="Realm")
    assert api.post("/api/imports", json=sample).status_code == 200
    sample.update(privacy="anonymous")
    sample.pop("name")
    sample.pop("realm")
    assert api.post("/api/imports", json=sample).status_code == 200
    with connect() as db:
        row = db.execute("SELECT * FROM owners").fetchone()
        assert row["privacy"] == "anonymous" and row["name"] is None


def test_real_lua_archive_through_rust_packets_and_durable_worker(
    api, sample, tmp_path
):
    import subprocess
    from pathlib import Path
    from server import upload_queue
    from server.config import postgres_enabled

    executable = os.environ.get("GABBAPROC_ARCHIVE_READER")
    if not postgres_enabled() or not executable:
        pytest.skip("Requires PostgreSQL and the compiled archive_packets Rust example")

    def lua(value):
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "{" + ",".join(lua(v) for v in value) + "}"
        return (
            "{" + ",".join("[" + lua(k) + "]=" + lua(v) for k, v in value.items()) + "}"
        )

    def snapshot(collection, count):
        history = [
            {
                "id": i,
                "context": "world",
                "duration": 1,
                "status": "complete",
                "counts": {20007: 1},
                "effects": {20007: True},
            }
            for i in range(1, count + 1)
        ]
        return dict(
            schemaVersion=1,
            addonVersion="0.1.1",
            characterId=sample["characterId"],
            collectionId=collection,
            sequence=7,
            exportedAt=int(time.time()),
            character={"name": "Secretname", "realm": "Secretrealm"},
            historyTruncated=True,
            archiveVersion=1,
            archiveTruncated=False,
            totals=[
                dict(
                    spellId=20007,
                    group="world",
                    procs=count,
                    combatProcs=count,
                    combatSeconds=count,
                )
            ],
            history=history[-300:],
            archiveHistory=history,
        )

    root = {
        "export": snapshot(sample["collectionId"], 1201),
        "archivedExports": [snapshot(str(uuid.uuid4()), 501)],
        "ignoredPadding": ["x" * 5000 for _ in range(2000)],
    }
    file = tmp_path / "GabbaProcTracker.lua"
    file.write_text("GabbaProcTrackerDB=" + lua(root))
    packets = json.loads(subprocess.check_output([executable, str(file)]))
    assert len(packets) == 19
    assert "Secretname" not in json.dumps(packets)
    jobs = []
    for packet in reversed(packets):
        result = api.post("/api/upload-jobs", json=packet)
        assert result.status_code == 202, result.text
        jobs.append(result.json()["jobId"])
    # Processed receipts survive payload deletion and replay.
    for _ in packets:
        assert upload_queue.process_one()
    for job in jobs:
        assert api.get("/api/upload-jobs/" + job).json()["status"] == "processed"
    for packet in packets:
        result = api.post("/api/upload-jobs", json=packet).json()
        assert result["status"] == "processed"
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 1702
        assert db.execute("SELECT SUM(procs) FROM totals").fetchone()[0] == 1702
        assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
    assert not list(Path(os.environ["GABBAPROC_SPOOL"]).glob("*.json"))


def test_legacy_client_can_replay_after_archive_upgrade(api, sample):
    archive = copy.deepcopy(sample)
    archive["schemaVersion"] = 2
    assert api.post("/api/imports", json=archive).status_code == 200
    assert api.post("/api/imports", json=sample).status_code == 200
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 1
