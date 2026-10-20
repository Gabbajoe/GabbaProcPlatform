import os
from urllib.parse import urlparse, parse_qs
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server import accounts
from server.storage import connect, invite


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv("GABBAPROC_DB", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("GABBAPROC_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setenv("GABBAPROC_ACCOUNTS", "true")
    monkeypatch.setenv("GABBAPROC_ORIGIN", "https://testserver")
    monkeypatch.setenv("GABBAPROC_AUTH_KEY", "test-key-only-" * 4)
    monkeypatch.setenv("GABBAPROC_SMTP_PASSWORD", "test-only")
    for p in ("DISCORD", "GITHUB"):
        monkeypatch.setenv("GABBAPROC_" + p + "_CLIENT_ID", "test-id")
        monkeypatch.setenv("GABBAPROC_" + p + "_CLIENT_SECRET", "test-secret")
    pg = os.environ.get("GABBAPROC_TEST_DATABASE_URL")
    if pg:
        from server.postgres import close_pool
        from server.storage import init

        close_pool()
        monkeypatch.setenv("GABBAPROC_DATABASE_URL", pg)
        with connect() as db:
            assert (
                db.execute("SELECT current_database()").fetchone()[0].endswith("_test")
            )
        init()
        with connect() as db:
            db.execute(
                "TRUNCATE devices,invites,accounts,auth_flows,device_links,limits CASCADE"
            )
    sent = []
    monkeypatch.setattr(
        accounts, "send_code", lambda email, code, state: sent.append((email, code))
    )
    with (
        TestClient(app, base_url="https://testserver") as a,
        TestClient(app, base_url="https://testserver") as b,
    ):
        for c in (a, b):
            c.headers["Origin"] = "https://testserver"
        yield a, b, sent
    if pg:
        close_pool()


def signin(c, sent, email="one@example.org", link=False):
    r = c.post("/api/auth/email/request", json={"email": email, "link": link})
    assert r.status_code == 200, r.text
    state = r.json()["challenge"]
    r = c.post("/api/auth/email/verify", json={"challenge": state, "code": sent[-1][1]})
    assert r.status_code == 200, r.text
    return state


def test_email_session_binding_replay_and_csrf(clients):
    a, b, sent = clients
    r = a.post("/api/auth/email/request", json={"email": "one@example.org"})
    state = r.json()["challenge"]
    code = sent[-1][1]
    assert (
        b.post(
            "/api/auth/email/verify", json={"challenge": state, "code": code}
        ).status_code
        == 400
    )
    r = a.post("/api/auth/email/verify", json={"challenge": state, "code": code})
    assert r.status_code == 200
    assert "HttpOnly" in r.headers["set-cookie"] and "Secure" in r.headers["set-cookie"]
    assert a.get("/api/account").status_code == 200
    assert (
        a.post(
            "/api/auth/email/verify", json={"challenge": state, "code": code}
        ).status_code
        == 400
    )
    assert (
        a.post(
            "/api/auth/logout", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert a.post("/api/auth/logout").status_code == 200
    assert a.get("/api/account").status_code == 401


def test_email_expiry_attempts_and_delivery_failure(clients, monkeypatch):
    a, b, sent = clients
    state = a.post("/api/auth/email/request", json={"email": "one@example.org"}).json()[
        "challenge"
    ]
    good = sent[-1][1]
    wrong = "00000000" if good != "00000000" else "11111111"
    for _ in range(5):
        assert (
            a.post(
                "/api/auth/email/verify", json={"challenge": state, "code": wrong}
            ).status_code
            == 400
        )
    assert (
        a.post(
            "/api/auth/email/verify", json={"challenge": state, "code": good}
        ).status_code
        == 400
    )
    state = a.post("/api/auth/email/request", json={"email": "two@example.org"}).json()[
        "challenge"
    ]
    with connect() as db:
        db.execute("UPDATE auth_flows SET expires=0")
    assert (
        a.post(
            "/api/auth/email/verify", json={"challenge": state, "code": sent[-1][1]}
        ).status_code
        == 400
    )

    def fail(*args):
        raise OSError("private SMTP detail")

    monkeypatch.setattr(accounts, "send_code", fail)
    r = a.post("/api/auth/email/request", json={"email": "three@example.org"})
    assert r.status_code == 503
    assert "private SMTP" not in r.text


def test_oauth_binding_pkce_and_linking(clients, monkeypatch):
    a, b, sent = clients
    monkeypatch.setattr(
        accounts, "provider_identity", lambda *args: ("1234", "example")
    )
    r = a.post("/api/auth/github/start", json={})
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["code_challenge_method"] == ["S256"]
    url = "/api/auth/github/callback?state=" + q["state"][0] + "&code=good"
    assert "auth=failed" in b.get(url, follow_redirects=False).headers["location"]
    assert a.get(url, follow_redirects=False).headers["location"] == "/account.html"
    assert "auth=failed" in a.get(url, follow_redirects=False).headers["location"]
    first = a.get("/api/account").json()["id"]
    signin(a, sent, link=True)
    assert a.get("/api/account").json()["id"] == first
    assert len(a.get("/api/account").json()["identities"]) == 2
    signin(b, sent, "other@example.org")
    r = b.post("/api/auth/github/start", json={"link": True})
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert (
        "auth=failed"
        in b.get(
            "/api/auth/github/callback?state=" + q["state"][0] + "&code=good",
            follow_redirects=False,
        ).headers["location"]
    )
    assert b.get("/api/account").json()["id"] != first


def test_discord_issuer_checked(clients, monkeypatch):
    a, b, sent = clients
    called = []
    monkeypatch.setattr(
        accounts, "provider_identity", lambda *args: called.append(args)
    )
    r = a.post("/api/auth/discord/start", json={})
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["scope"] == ["identify"]
    r = a.get(
        "/api/auth/discord/callback?state="
        + q["state"][0]
        + "&code=x&iss=https://evil.example",
        follow_redirects=False,
    )
    assert "auth=failed" in r.headers["location"]
    assert not called


def test_device_claim_ownership_and_revoke(clients):
    a, b, sent = clients
    signin(a, sent)
    signin(b, sent, "two@example.org")
    token = a.post("/api/enroll", json={"invite": invite()}).json()["token"]
    auth = {"Authorization": "Bearer " + token}
    assert a.post("/api/account/claim-device", headers=auth).status_code == 200
    assert b.post("/api/account/claim-device", headers=auth).status_code == 409
    did = a.get("/api/account").json()["devices"][0]["id"]
    assert b.delete("/api/account/devices/" + did).status_code == 404
    assert a.delete("/api/account/devices/" + did).status_code == 200
    assert a.post("/api/account/claim-device", headers=auth).status_code == 401


def test_pairing_approval_and_single_redemption(clients):
    a, b, sent = clients
    signin(a, sent)
    pair = b.post("/api/device-link/start").json()
    assert (
        b.post("/api/device-link/poll", json={"deviceCode": pair["deviceCode"]}).json()[
            "status"
        ]
        == "pending"
    )
    assert (
        b.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 200
    )
    with connect() as db:
        db.execute("DELETE FROM limits")
    r = b.post("/api/device-link/poll", json={"deviceCode": pair["deviceCode"]})
    assert r.status_code == 200
    assert r.json()["token"]
    with connect() as db:
        db.execute("DELETE FROM limits")
    assert (
        b.post(
            "/api/device-link/poll", json={"deviceCode": pair["deviceCode"]}
        ).status_code
        == 410
    )
    assert len(a.get("/api/account").json()["devices"]) == 1


def test_pair_existing_preserves_token_and_delete_account(clients):
    a, b, sent = clients
    signin(a, sent)
    token = b.post("/api/enroll", json={"invite": invite()}).json()["token"]
    pair = b.post(
        "/api/device-link/start", headers={"Authorization": "Bearer " + token}
    ).json()
    assert (
        a.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 200
    )
    result = b.post(
        "/api/device-link/poll", json={"deviceCode": pair["deviceCode"]}
    ).json()
    assert result["status"] == "linked" and "token" not in result
    assert len(result["deviceId"]) == 32
    assert a.delete("/api/account").status_code == 200
    assert a.get("/api/account").status_code == 401
    assert (
        b.post(
            "/api/device-link/start", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )


def test_disabled_and_email_validation(clients, monkeypatch):
    a, b, sent = clients
    assert (
        a.post(
            "/api/auth/email/request", json={"email": "bad\r\nBcc: x@y.org"}
        ).status_code
        == 400
    )
    monkeypatch.setenv("GABBAPROC_ACCOUNTS", "false")
    assert a.get("/api/auth/options").json() == {"providers": [], "email": False}
    assert a.post("/api/device-link/start").status_code == 503


def test_email_rate_limit_and_session_expiry(clients):
    a, b, sent = clients
    for _ in range(5):
        assert (
            a.post(
                "/api/auth/email/request", json={"email": "limited@example.org"}
            ).status_code
            == 200
        )
    assert (
        a.post(
            "/api/auth/email/request", json={"email": "limited@example.org"}
        ).status_code
        == 429
    )
    signin(a, sent, "other@example.org")
    with connect() as db:
        db.execute("UPDATE account_sessions SET expires=0")
    assert a.get("/api/account").status_code == 401


def test_pairing_cannot_take_foreign_device(clients):
    a, b, sent = clients
    signin(a, sent)
    signin(b, sent, "two@example.org")
    token = a.post("/api/account/devices").json()["token"]
    pair = b.post(
        "/api/device-link/start", headers={"Authorization": "Bearer " + token}
    ).json()
    assert (
        b.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 409
    )
    assert (
        a.post(
            "/api/device-link/approve",
            headers={"Origin": "https://evil.example"},
            json={"userCode": pair["userCode"]},
        ).status_code
        == 403
    )
    with connect() as db:
        db.execute("UPDATE device_links SET expires=0")
    assert (
        a.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 400
    )


def test_delete_removes_imported_data_and_cancels_jobs(clients):
    import time, uuid
    from server.config import postgres_enabled

    a, b, sent = clients
    signin(a, sent)
    token = a.post("/api/account/devices").json()["token"]
    headers = {"Authorization": "Bearer " + token}
    payload = {
        "schemaVersion": 1,
        "addonVersion": "0.1.2",
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
                "procs": 1,
                "combatProcs": 1,
                "combatSeconds": 60,
            }
        ],
        "segments": [],
    }
    assert a.post("/api/imports", headers=headers, json=payload).status_code == 200
    if postgres_enabled():
        payload["sequence"] = 2
        assert (
            a.post("/api/upload-jobs", headers=headers, json=payload).status_code == 202
        )
    assert a.delete("/api/account").status_code == 200
    with connect() as db:
        assert db.execute("SELECT count(*) FROM owners").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM account_identities").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM account_sessions").fetchone()[0] == 0
        if postgres_enabled():
            assert (
                db.execute(
                    "SELECT count(*) FROM upload_jobs WHERE status='queued'"
                ).fetchone()[0]
                == 0
            )


def test_provider_exchange_uses_fixed_endpoint_and_identity(clients, monkeypatch):
    import httpx

    a, b, sent = clients
    seen = []

    def handler(req):
        seen.append(req)
        if str(req.url) == "https://github.com/login/oauth/access_token":
            assert b"code_verifier=verifier" in req.content
            return httpx.Response(
                200, json={"access_token": "test-access", "refresh_token": "not-stored"}
            )
        assert str(req.url) == "https://api.github.com/user"
        assert req.headers["authorization"] == "Bearer test-access"
        return httpx.Response(
            200, json={"id": 123, "login": "demo", "email": "ignored@example.org"}
        )

    original = httpx.Client
    monkeypatch.setattr(
        accounts.httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    assert accounts.provider_identity("github", "test-code", "verifier") == (
        "123",
        "demo",
    )
    assert len(seen) == 2


def test_email_html_link_and_plaintext(monkeypatch):
    from email import policy
    from email.parser import BytesParser
    from html import unescape
    import re

    captured = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            pass

        def starttls(self, context):
            assert context.check_hostname

        def login(self, name, password):
            assert name == "gabbaproc@kellerkind.info"

        def send_message(self, message):
            captured.append(message)

    monkeypatch.setattr(accounts.smtplib, "SMTP", SMTP)
    monkeypatch.setenv("GABBAPROC_ORIGIN", "https://gabbaproc.kellerkind.info")
    accounts.send_code("person@example.org", "01234567", "A" * 43)
    message = BytesParser(policy=policy.default).parsebytes(captured[0].as_bytes())
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "01234567" in plain and "01234567" in html
    assert "text/plain" in message.as_string() and "text/html" in message.as_string()
    link = unescape(re.search(r'href="([^"]+#emailChallenge[^"]+)"', html)[1])
    parsed = urlparse(link)
    assert not parsed.query
    assert parsed.netloc == "gabbaproc.kellerkind.info"
    assert parse_qs(parsed.fragment) == {
        "emailChallenge": ["A" * 43],
        "emailCode": ["01234567"],
        "emailAddress": ["person@example.org"],
    }
    assert link in plain and "<img" not in html and "<script" not in html


def test_profile_username_uniqueness_validation_and_deletion(clients):
    a, b, sent = clients
    assert a.put("/api/account/profile", json={"username": "Gabba"}).status_code == 401
    signin(a, sent)
    signin(b, sent, "two@example.org")
    assert (
        a.put("/api/account/profile", json={"username": "GabbaJoe"}).status_code == 200
    )
    assert a.get("/api/account").json()["username"] == "GabbaJoe"
    assert (
        b.put("/api/account/profile", json={"username": "gabbajoe"}).status_code == 409
    )
    assert (
        a.put("/api/account/profile", json={"username": "Gabbajoe"}).status_code == 200
    )
    for name in ["a", "a" * 25, "<script>", " bad", "mail@example.org"]:
        assert a.put("/api/account/profile", json={"username": name}).status_code == 400
    assert (
        a.put(
            "/api/account/profile",
            json={"username": "Changed"},
            headers={"Origin": "https://other.example"},
        ).status_code
        == 403
    )
    assert a.delete("/api/account").status_code == 200
    assert (
        b.put("/api/account/profile", json={"username": "GabbaJoe"}).status_code == 200
    )


def test_disconnect_reconnect_keeps_device_and_rotates_token(clients):
    import time, uuid
    from server.config import postgres_enabled

    a, b, sent = clients
    signin(a, sent)
    signin(b, sent, "two@example.org")
    assert (
        a.put("/api/account/profile", json={"username": "TestUser"}).status_code == 200
    )
    device = a.post("/api/account/devices").json()
    old = {"Authorization": "Bearer " + device["token"]}
    info = a.get("/api/device-account", headers=old).json()
    assert info == {
        "deviceId": device["id"],
        "linked": True,
        "username": "TestUser",
        "expiresAt": None,
    }
    assert (
        time.time() + 13 * 86400
        < a.get("/api/account").json()["sessionExpiresAt"]
        <= time.time() + 14 * 86400
    )
    payload = {
        "schemaVersion": 1,
        "addonVersion": "0.1.2",
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
                "procs": 1,
                "combatProcs": 1,
                "combatSeconds": 60,
            }
        ],
        "segments": [],
    }
    assert a.post("/api/imports", headers=old, json=payload).status_code == 200
    if postgres_enabled():
        payload["sequence"] = 2
        job = a.post("/api/upload-jobs", headers=old, json=payload).json()["jobId"]
    assert a.post("/api/device-disconnect", headers=old).status_code == 200
    assert a.get("/api/device-account", headers=old).status_code == 401
    pair = a.post("/api/device-link/start", json={"deviceId": device["id"]}).json()
    assert (
        b.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 403
    )
    assert (
        a.post(
            "/api/device-link/approve", json={"userCode": pair["userCode"]}
        ).status_code
        == 200
    )
    result = a.post(
        "/api/device-link/poll", json={"deviceCode": pair["deviceCode"]}
    ).json()
    assert result["deviceId"] == device["id"] and result["reconnected"] is True
    assert result["token"] != device["token"]
    new = {"Authorization": "Bearer " + result["token"]}
    assert a.get("/api/device-account", headers=old).status_code == 401
    assert a.get("/api/device-account", headers=new).json()["username"] == "TestUser"
    with connect() as db:
        assert (
            db.execute(
                "SELECT device FROM owners WHERE character=?", (payload["characterId"],)
            ).fetchone()[0]
            == device["id"]
        )
    if postgres_enabled():
        assert a.get("/api/upload-jobs/" + job, headers=new).status_code == 404
        assert (
            a.post("/api/upload-jobs", headers=new, json=payload).json()["status"]
            == "queued"
        )
    else:
        assert (
            a.post("/api/imports", headers=new, json=payload).json()["status"]
            == "duplicate"
        )
