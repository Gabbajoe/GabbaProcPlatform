import httpx
from server import avatars


def test_avatar_download_is_bounded_and_uses_fixed_hosts(monkeypatch):
    seen = []
    content = b"\x89PNG\r\n\x1a\nimage"
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=content)
    original = httpx.Client
    monkeypatch.setattr(avatars.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    assert avatars.load_avatar("discord", "123", {"avatar": "a" * 32})[0] == "image/png"
    assert seen[-1] == "https://cdn.discordapp.com/avatars/123/" + "a" * 32 + ".png?size=128"
    assert avatars.load_avatar("github", "456", {"avatar_url": "http://127.0.0.1/private"})
    assert seen[-1] == "https://avatars.githubusercontent.com/u/456?s=96"
    content = b"<svg onload='evil'/>"
    assert avatars.load_avatar("github", "456", {}) is None
    content = b"\x89PNG\r\n\x1a\n" + b"x" * 131072
    assert avatars.load_avatar("github", "456", {}) is None
    count = len(seen)
    assert avatars.load_avatar("discord", "123", {"avatar": "../../secret"}) is None
    assert avatars.load_avatar("github", "../123", {}) is None
    assert avatars.load_avatar("battlenet", "123", {}) is None
    assert len(seen) == count
