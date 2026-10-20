"""Browser accounts and explicit device pairing. Provider credentials never leave the API."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import ssl
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from .signin_email import message as signin_message
from .config import value
from .storage import connect, digest, lock

router = APIRouter(prefix="/api")
COOKIE = "__Host-gabbaproc-session"
FLOW_COOKIE = "__Host-gabbaproc-flow"
SESSION_SECONDS = 14 * 86400
PROVIDERS = {
    "discord": (
        "https://discord.com/oauth2/authorize",
        "https://discord.com/api/oauth2/token",
        "https://discord.com/api/v10/users/@me",
        "identify",
    ),
    "github": (
        "https://github.com/login/oauth/authorize",
        "https://github.com/login/oauth/access_token",
        "https://api.github.com/user",
        "",
    ),
}


def origin():
    return value("GABBAPROC_ORIGIN", "https://gabbaproc.kellerkind.info").rstrip("/")


def enabled():
    return value("GABBAPROC_ACCOUNTS", "false") == "true"


def require_enabled():
    if not enabled():
        raise HTTPException(503, "Account sign-in unavailable")


def same_origin(request):
    if request.headers.get("origin") != origin():
        raise HTTPException(403, "Same-origin request required")


def limited(request, kind, maximum=30, period=3600):
    from .app import rate

    rate("account:" + kind + ":" + digest(request.client.host), maximum, period)


async def data(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "JSON required")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2048:
            raise HTTPException(413, "Request too large")
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid request") from None


def cookie(response, name, token, age):
    response.set_cookie(
        name, token, max_age=age, secure=True, httponly=True, samesite="lax", path="/"
    )


def session(request):
    require_enabled()
    token = request.cookies.get(COOKIE, "")
    if not 30 < len(token) < 100:
        raise HTTPException(401, "Sign in required")
    with connect() as db:
        row = db.execute(
            "SELECT account FROM account_sessions WHERE hash=? AND expires>?",
            (digest(token), int(time.time())),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Session expired")
    return row["account"]


def optional_session(request):
    try:
        return session(request)
    except HTTPException as e:
        if e.status_code == 401:
            return None
        raise


def cleanup():
    now = int(time.time())
    with connect() as db:
        db.execute("DELETE FROM account_sessions WHERE expires<=?", (now,))
        db.execute("DELETE FROM auth_flows WHERE expires<=?", (now,))
        db.execute("DELETE FROM device_links WHERE expires<=?", (now,))


def flow(request, provider, payload):
    require_enabled()
    cleanup()
    state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with connect() as db:
        db.execute(
            "INSERT INTO auth_flows(hash,binding,provider,payload,expires,attempts) VALUES(?,?,?,?,?,0)",
            (
                digest(state),
                digest(binding),
                provider,
                json.dumps(payload),
                int(time.time()) + 600,
            ),
        )
    return state, binding


def consume(request, state, provider, code=None):
    if not isinstance(state, str) or not 30 < len(state) < 100:
        raise HTTPException(400, "Invalid or expired sign-in")
    result = None
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "flow:" + digest(state))
        row = db.execute(
            "SELECT * FROM auth_flows WHERE hash=?", (digest(state),)
        ).fetchone()
        if (
            row
            and row["expires"] > time.time()
            and row["attempts"] < 5
            and row["provider"] == provider
            and hmac.compare_digest(
                row["binding"], digest(request.cookies.get(FLOW_COOKIE, ""))
            )
        ):
            payload = json.loads(row["payload"])
            if code is not None and not hmac.compare_digest(
                payload["code"], code_hash(state, code)
            ):
                db.execute(
                    "UPDATE auth_flows SET attempts=attempts+1 WHERE hash=?",
                    (digest(state),),
                )
            else:
                db.execute("DELETE FROM auth_flows WHERE hash=?", (digest(state),))
                result = payload
        db.commit()
    if result is None:
        raise HTTPException(400, "Invalid or expired sign-in")
    if result.get("link") and optional_session(request) != result["link"]:
        raise HTTPException(401, "Sign in again before linking")
    return result


def login(request, provider, subject, display, target=None, redirect=False):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "identity:" + provider + ":" + subject)
        found = db.execute(
            "SELECT account FROM account_identities WHERE provider=? AND subject=?",
            (provider, subject),
        ).fetchone()
        if target:
            lock(db, "account:" + target)
            if not db.execute(
                "SELECT id FROM accounts WHERE id=?", (target,)
            ).fetchone():
                raise HTTPException(401, "Account no longer exists")
            if found and found["account"] != target:
                raise HTTPException(409, "Identity belongs to another account")
        account = target or (found["account"] if found else secrets.token_hex(16))
        lock(db, "account:" + account)
        if (
            found
            and not db.execute(
                "SELECT id FROM accounts WHERE id=?", (account,)
            ).fetchone()
        ):
            raise HTTPException(401, "Account no longer exists")
        if not found and not target:
            db.execute("INSERT INTO accounts VALUES(?,?)", (account, int(time.time())))
        if not found:
            db.execute(
                "INSERT INTO account_identities VALUES(?,?,?,?)",
                (provider, subject, account, display[:160]),
            )
        old = request.cookies.get(COOKIE, "")
        if old:
            db.execute("DELETE FROM account_sessions WHERE hash=?", (digest(old),))
        db.execute(
            "INSERT INTO account_sessions VALUES(?,?,?)",
            (digest(token), account, int(time.time()) + SESSION_SECONDS),
        )
        db.commit()
    response = (
        RedirectResponse("/account.html", status_code=303)
        if redirect
        else JSONResponse({"status": "signed_in"})
    )
    cookie(response, COOKIE, token, SESSION_SECONDS)
    response.delete_cookie(
        FLOW_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
    )
    return response


def configured(provider):
    prefix = "GABBAPROC_" + provider.upper()
    return bool(value(prefix + "_CLIENT_ID") and value(prefix + "_CLIENT_SECRET"))


@router.get("/auth/options")
def options():
    return {
        "providers": [p for p in PROVIDERS if enabled() and configured(p)],
        "email": enabled()
        and bool(value("GABBAPROC_SMTP_PASSWORD") and value("GABBAPROC_AUTH_KEY")),
    }


@router.post("/auth/{provider}/start")
async def oauth_start(provider: str, request: Request):
    same_origin(request)
    body = await data(request)
    return await run_in_threadpool(start_oauth, provider, request, body)


def start_oauth(provider, request, body):
    require_enabled()
    if provider not in PROVIDERS or not configured(provider):
        raise HTTPException(404, "Provider unavailable")
    limited(request, "oauth", 20)
    target = session(request) if body.get("link") is True else None
    verifier = secrets.token_urlsafe(48)
    state, binding = flow(request, provider, {"verifier": verifier, "link": target})
    params = {
        "client_id": value("GABBAPROC_" + provider.upper() + "_CLIENT_ID"),
        "redirect_uri": origin() + f"/api/auth/{provider}/callback",
        "response_type": "code",
        "state": state,
        "scope": PROVIDERS[provider][3],
    }
    if provider == "github":
        params.update(
            code_challenge=base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .decode()
            .rstrip("="),
            code_challenge_method="S256",
        )
    response = JSONResponse({"url": PROVIDERS[provider][0] + "?" + urlencode(params)})
    cookie(response, FLOW_COOKIE, binding, 600)
    return response


def provider_identity(provider, code, verifier):
    prefix = "GABBAPROC_" + provider.upper()
    fields = {
        "client_id": value(prefix + "_CLIENT_ID"),
        "client_secret": value(prefix + "_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": origin() + f"/api/auth/{provider}/callback",
    }
    if provider == "github":
        fields["code_verifier"] = verifier
    try:
        with httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "GabbaProc"},
        ) as client:
            response = client.post(PROVIDERS[provider][1], data=fields)
            response.raise_for_status()
            token = response.json()["access_token"]
            response = client.get(
                PROVIDERS[provider][2], headers={"Authorization": "Bearer " + token}
            )
            response.raise_for_status()
            user = response.json()
            subject = str(user["id"])
            if not subject.isdecimal():
                raise ValueError()
            return subject, str(user.get("username") or user.get("login") or subject)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Provider sign-in failed; please retry") from None


@router.get("/auth/{provider}/callback")
def oauth_callback(provider: str, request: Request):
    require_enabled()
    if provider not in PROVIDERS or not configured(provider):
        raise HTTPException(404, "Provider unavailable")
    limited(request, "callback", 60)
    try:
        payload = consume(request, request.query_params.get("state", ""), provider)
        if request.query_params.get("error"):
            raise HTTPException(400, "Sign-in cancelled")
        if (
            provider == "discord"
            and request.query_params.get("iss") != "https://discord.com"
        ):
            raise HTTPException(400, "Unexpected issuer")
        code = request.query_params.get("code", "")
        if not code or len(code) > 1024:
            raise HTTPException(400, "Missing authorization code")
        subject, display = provider_identity(provider, code, payload["verifier"])
        return login(
            request, provider, subject, display, payload.get("link"), redirect=True
        )
    except HTTPException:
        return RedirectResponse("/account.html?auth=failed", status_code=303)


def code_hash(state, code):
    key = value("GABBAPROC_AUTH_KEY")
    if len(key) < 32:
        raise HTTPException(503, "Email sign-in unavailable")
    return hmac.new(
        key.encode(), (state + ":" + code).encode(), hashlib.sha256
    ).hexdigest()


def send_code(address, code, state):
    # Fragments stay in the browser: codes do not enter HTTP requests or access logs.
    link = (
        origin()
        + "/account.html#"
        + urlencode(
            {"emailChallenge": state, "emailCode": code, "emailAddress": address}
        )
    )
    message = signin_message(address, code, link)
    with smtplib.SMTP(
        value("GABBAPROC_SMTP_HOST", "mail.nilskeller.de"), 587, timeout=15
    ) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login("gabbaproc@kellerkind.info", value("GABBAPROC_SMTP_PASSWORD"))
        smtp.send_message(message)


@router.post("/auth/email/request")
async def email_request(request: Request):
    same_origin(request)
    return await run_in_threadpool(request_email, request, await data(request))


def request_email(request, body):
    require_enabled()
    if not options()["email"]:
        raise HTTPException(503, "Email sign-in unavailable")
    limited(request, "email", 10)
    address = body.get("email", "")
    if (
        not isinstance(address, str)
        or len(address) > 254
        or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
            address,
        )
    ):
        raise HTTPException(400, "Invalid email address")
    address = address.lower()
    from .app import rate

    rate("account:mail:" + digest(address), 5)
    rate("account:mail:global", 100)
    target = session(request) if body.get("link") is True else None
    code = f"{secrets.randbelow(100000000):08d}"
    state, binding = flow(request, "email", {"email": address, "link": target})
    with connect() as db:
        db.execute(
            "UPDATE auth_flows SET payload=? WHERE hash=?",
            (
                json.dumps(
                    {"email": address, "link": target, "code": code_hash(state, code)}
                ),
                digest(state),
            ),
        )
    try:
        send_code(address, code, state)
    except (OSError, smtplib.SMTPException):
        with connect() as db:
            db.execute("DELETE FROM auth_flows WHERE hash=?", (digest(state),))
        raise HTTPException(
            503, "Email delivery unavailable; please retry later"
        ) from None
    response = JSONResponse({"challenge": state, "expiresIn": 600})
    cookie(response, FLOW_COOKIE, binding, 600)
    return response


@router.post("/auth/email/verify")
async def email_verify(request: Request):
    same_origin(request)
    return await run_in_threadpool(verify_email, request, await data(request))


def verify_email(request, body):
    require_enabled()
    limited(request, "verify", 30)
    code = body.get("code", "")
    if not isinstance(code, str) or not re.fullmatch(r"\d{8}", code, re.ASCII):
        raise HTTPException(400, "Enter the eight-digit code")
    payload = consume(request, body.get("challenge", ""), "email", code)
    return login(
        request, "email", payload["email"], payload["email"], payload.get("link")
    )


@router.get("/account")
def account_info(request: Request):
    aid = session(request)
    with connect() as db:
        identities = [
            dict(r)
            for r in db.execute(
                "SELECT provider,display FROM account_identities WHERE account=?",
                (aid,),
            )
        ]
        devices = [
            dict(r)
            for r in db.execute(
                "SELECT d.id,d.created,d.revoked FROM devices d JOIN account_devices a ON a.device=d.id WHERE a.account=? ORDER BY d.created",
                (aid,),
            )
        ]
        profile = db.execute(
            "SELECT username FROM account_profiles WHERE account=?", (aid,)
        ).fetchone()
        browser_session = db.execute(
            "SELECT expires FROM account_sessions WHERE hash=?",
            (digest(request.cookies.get(COOKIE, "")),),
        ).fetchone()
    return {
        "sessionExpiresAt": browser_session["expires"] if browser_session else None,
        "id": aid,
        "username": profile["username"] if profile else None,
        "identities": identities,
        "devices": devices,
    }


@router.put("/account/profile")
async def profile_update(request: Request):
    same_origin(request)
    return await run_in_threadpool(save_profile, request, await data(request))


def save_profile(request, body):
    aid = session(request)
    limited(request, "profile", 20)
    name = body.get("username", "")
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{2,23}", name
    ):
        raise HTTPException(
            400, "Use 3–24 letters, digits, dots, underscores or hyphens"
        )
    key = name.lower()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + aid)
        if not db.execute("SELECT id FROM accounts WHERE id=?", (aid,)).fetchone():
            raise HTTPException(401, "Account no longer exists")
        lock(db, "username:" + key)
        owner = db.execute(
            "SELECT account FROM account_profiles WHERE username_key=?", (key,)
        ).fetchone()
        if owner and owner["account"] != aid:
            raise HTTPException(409, "Username unavailable")
        db.execute(
            "INSERT INTO account_profiles VALUES(?,?,?) ON CONFLICT(account) DO UPDATE SET username=excluded.username,username_key=excluded.username_key",
            (aid, name, key),
        )
        db.commit()
    return {"username": name}


@router.post("/auth/logout")
def logout(request: Request):
    same_origin(request)
    with connect() as db:
        db.execute(
            "DELETE FROM account_sessions WHERE hash=?",
            (digest(request.cookies.get(COOKIE, "")),),
        )
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


def attach(db, aid, did):
    lock(db, "account:" + aid)
    if not db.execute("SELECT id FROM accounts WHERE id=?", (aid,)).fetchone():
        raise HTTPException(401, "Account no longer exists")
    lock(db, "device:" + did)
    if not db.execute(
        "SELECT id FROM devices WHERE id=? AND revoked=0", (did,)
    ).fetchone():
        raise HTTPException(401, "Device unavailable")
    owner = db.execute(
        "SELECT account FROM account_devices WHERE device=?", (did,)
    ).fetchone()
    if owner and owner["account"] != aid:
        raise HTTPException(409, "Device belongs to another account")
    db.execute(
        "INSERT INTO account_devices VALUES(?,?) ON CONFLICT(device) DO NOTHING",
        (did, aid),
    )


@router.post("/account/claim-device")
def claim(request: Request):
    same_origin(request)
    aid = session(request)
    from .app import device

    did = device(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        attach(db, aid, did)
        db.commit()
    return {"status": "linked"}


@router.post("/account/devices")
def create_device(request: Request):
    same_origin(request)
    aid = session(request)
    limited(request, "new-device", 10)
    token, did = secrets.token_urlsafe(32), secrets.token_hex(16)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + aid)
        db.execute(
            "INSERT INTO devices(id,token_hash,created) VALUES(?,?,?)",
            (did, digest(token), int(time.time())),
        )
        attach(db, aid, did)
        db.commit()
    return {"token": token, "id": did}


@router.delete("/account/devices/{did}")
def revoke_device(did: str, request: Request):
    same_origin(request)
    aid = session(request)
    from .upload_queue import cancel_jobs

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + aid)
        lock(db, "device:" + did)
        if not db.execute(
            "SELECT device FROM account_devices WHERE device=? AND account=?",
            (did, aid),
        ).fetchone():
            raise HTTPException(404, "Device not found")
        cancel_jobs(db, did)
        db.execute("UPDATE devices SET revoked=1 WHERE id=?", (did,))
        db.commit()
    return {"status": "revoked"}


@router.delete("/account")
def delete_account(request: Request):
    same_origin(request)
    aid = session(request)
    from .upload_queue import cancel_jobs

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + aid)
        devices = [
            r[0]
            for r in db.execute(
                "SELECT device FROM account_devices WHERE account=? ORDER BY device",
                (aid,),
            )
        ]
        for did in devices:
            lock(db, "device:" + did)
            cancel_jobs(db, did)
            db.execute(
                "DELETE FROM snapshots WHERE character IN (SELECT character FROM owners WHERE device=?)",
                (did,),
            )
            db.execute("DELETE FROM owners WHERE device=?", (did,))
            db.execute("UPDATE devices SET revoked=1 WHERE id=?", (did,))
        db.execute("DELETE FROM device_links WHERE account=?", (aid,))
        db.execute("DELETE FROM accounts WHERE id=?", (aid,))
        db.commit()
    return logout(request)


@router.get("/device-account")
def device_account(request: Request):
    from .app import device

    did = device(request, maximum=240, kind="device-account")
    with connect() as db:
        row = db.execute(
            "SELECT a.account,p.username FROM account_devices a LEFT JOIN account_profiles p ON p.account=a.account WHERE a.device=?",
            (did,),
        ).fetchone()
    return {
        "deviceId": did,
        "linked": bool(row),
        "username": row["username"] if row else None,
        "expiresAt": None,
    }


@router.post("/device-disconnect")
def device_disconnect(request: Request):
    from .app import device
    from .upload_queue import cancel_jobs

    did = device(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "device:" + did)
        cancel_jobs(db, did)
        db.execute("UPDATE devices SET revoked=1 WHERE id=?", (did,))
        db.commit()
    return {"status": "disconnected", "deviceId": did}


@router.post("/device-link/start")
async def pair_start(request: Request):
    payload = await data(request) if request.headers.get("content-type") else {}
    return await run_in_threadpool(start_pair, request, payload)


def start_pair(request, payload):
    require_enabled()
    limited(request, "pair-start", 10)
    cleanup()
    did = None
    if request.headers.get("authorization"):
        from .app import device

        did = device(request)
    reconnect = payload.get("deviceId") if not did else None
    if reconnect is not None and (
        not isinstance(reconnect, str) or not re.fullmatch(r"[a-f0-9]{32}", reconnect)
    ):
        raise HTTPException(400, "Invalid device")
    code = secrets.token_urlsafe(32)
    user_code = secrets.token_hex(5).upper()
    with connect() as db:
        db.execute(
            "INSERT INTO device_links VALUES(?,?,NULL,?,?)",
            (digest(code), user_code, did, int(time.time()) + 600),
        )
        if reconnect:
            if not db.execute(
                "SELECT device FROM account_devices WHERE device=?", (reconnect,)
            ).fetchone():
                raise HTTPException(400, "Device cannot be reconnected")
            db.execute(
                "INSERT INTO device_reconnects VALUES(?,?)", (digest(code), reconnect)
            )
    return {
        "deviceCode": code,
        "userCode": user_code,
        "verificationUri": origin() + "/account.html",
        "expiresIn": 600,
        "interval": 5,
    }


@router.post("/device-link/approve")
async def pair_approve(request: Request):
    same_origin(request)
    return await run_in_threadpool(approve_pair, request, await data(request))


def approve_pair(request, body):
    aid = session(request)
    limited(request, "pair-approve", 20)
    code = body.get("userCode", "")
    if not isinstance(code, str) or not re.fullmatch(r"[A-F0-9]{10}", code.upper()):
        raise HTTPException(400, "Invalid device code")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + aid)
        lock(db, "pair:" + code.upper())
        row = db.execute(
            "SELECT * FROM device_links WHERE user_code=? AND expires>?",
            (code.upper(), int(time.time())),
        ).fetchone()
        if not row or row["account"]:
            raise HTTPException(400, "Code expired or already approved")
        reconnect = db.execute(
            "SELECT device FROM device_reconnects WHERE hash=?", (row["hash"],)
        ).fetchone()
        if (
            reconnect
            and not db.execute(
                "SELECT device FROM account_devices WHERE device=? AND account=?",
                (reconnect["device"], aid),
            ).fetchone()
        ):
            raise HTTPException(403, "Device belongs to another account")
        if row["device"]:
            attach(db, aid, row["device"])
        db.execute("UPDATE device_links SET account=? WHERE hash=?", (aid, row["hash"]))
        db.commit()
    return {"status": "approved"}


@router.post("/device-link/poll")
async def pair_poll(request: Request):
    return await run_in_threadpool(poll_pair, request, await data(request))


def poll_pair(request, body):
    require_enabled()
    code = body.get("deviceCode", "")
    if not isinstance(code, str) or not 30 < len(code) < 100:
        raise HTTPException(400, "Invalid device code")
    from .app import rate

    limited(request, "pair-poll", 240)
    rate("pair-poll:" + digest(code), 1, 5)
    with connect() as db:
        # Read then lock in account -> pair -> device order, matching approval/deletion.
        row = db.execute(
            "SELECT * FROM device_links WHERE hash=? AND expires>?",
            (digest(code), int(time.time())),
        ).fetchone()
        if not row:
            raise HTTPException(410, "Pairing expired; start again")
        if not row["account"]:
            return {"status": "pending"}
        db.execute("BEGIN IMMEDIATE")
        lock(db, "account:" + row["account"])
        lock(db, "pair:" + row["user_code"])
        row = db.execute(
            "SELECT * FROM device_links WHERE hash=? AND expires>?",
            (digest(code), int(time.time())),
        ).fetchone()
        if not row:
            raise HTTPException(410, "Pairing expired; start again")
        reconnect = db.execute(
            "SELECT device FROM device_reconnects WHERE hash=?", (row["hash"],)
        ).fetchone()
        if reconnect:
            did = reconnect["device"]
            lock(db, "device:" + did)
            if not db.execute(
                "SELECT device FROM account_devices WHERE device=? AND account=?",
                (did, row["account"]),
            ).fetchone():
                raise HTTPException(403, "Device belongs to another account")
            token = secrets.token_urlsafe(32)
            db.execute(
                "UPDATE devices SET token_hash=?,revoked=0 WHERE id=?",
                (digest(token), did),
            )
            # Old cancelled receipts must not prevent replay of retained local packets.
            db.execute(
                "DELETE FROM upload_jobs WHERE device=? AND status='cancelled'", (did,)
            )
            result = {
                "status": "linked",
                "token": token,
                "reconnected": True,
                "deviceId": did,
            }
        elif row["device"]:
            attach(db, row["account"], row["device"])
            result = {"status": "linked", "deviceId": row["device"]}
        else:
            token, did = secrets.token_urlsafe(32), secrets.token_hex(16)
            db.execute(
                "INSERT INTO devices(id,token_hash,created) VALUES(?,?,?)",
                (did, digest(token), int(time.time())),
            )
            attach(db, row["account"], did)
            result = {"status": "linked", "token": token, "deviceId": did}
        db.execute("DELETE FROM device_links WHERE hash=?", (digest(code),))
        db.commit()
    return result
