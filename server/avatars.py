"""Small provider avatars fetched only during sign-in, never from arbitrary URLs."""
import base64
import re
import httpx

def load_avatar(provider, subject, user):
    if not re.fullmatch(r"[0-9]{1,30}", subject):
        return None
    if provider == "github":
        url = f"https://avatars.githubusercontent.com/u/{subject}?s=96"
    elif provider == "discord" and re.fullmatch(r"(?:a_)?[a-f0-9]{32}", str(user.get("avatar", ""))):
        url = f"https://cdn.discordapp.com/avatars/{subject}/{user['avatar']}.png?size=128"
    else:
        return None
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"User-Agent": "GabbaProc"}) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 131072:
                        return None
        raw = bytes(content)
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            return None
        return (mime, base64.b64encode(raw).decode("ascii"))
    except (httpx.HTTPError, ValueError):
        return None
