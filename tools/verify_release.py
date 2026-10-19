#!/usr/bin/env python3
"""Verify a downloaded GitHub release against the compiled updater public key.

Requires minisign. Download all release assets into one directory first.
"""

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

p = argparse.ArgumentParser()
p.add_argument("directory", type=Path)
p.add_argument("--minisign", default="minisign")
a = p.parse_args()
root = a.directory.resolve()
config = json.loads(
    (
        Path(__file__).resolve().parents[1] / "desktop/src-tauri/tauri.conf.json"
    ).read_text()
)
manifest = json.loads((root / "latest.json").read_text())
assert manifest["version"].removeprefix("v") == config["version"], "Version mismatch"
platforms = manifest["platforms"]
required = {"darwin-aarch64", "darwin-x86_64", "windows-x86_64", "linux-x86_64"}
assert required <= platforms.keys(), "Missing operating system or architecture"
assert len(platforms) <= 20, "Unexpected manifest size"
verified = {}
with tempfile.TemporaryDirectory() as temp:
    public = Path(temp) / "updater.pub"
    public.write_bytes(
        base64.b64decode(config["plugins"]["updater"]["pubkey"], validate=True)
    )
    for platform, item in platforms.items():
        url = urlsplit(item["url"])
        prefix = (
            "/Gabbajoe/GabbaProcPlatform/releases/download/v" + config["version"] + "/"
        )
        assert (
            url.scheme == "https"
            and url.netloc == "github.com"
            and url.path.startswith(prefix)
        ), "Unexpected download origin"
        assert not url.query and not url.fragment, "Unexpected URL parameters"
        name = unquote(url.path[len(prefix) :])
        assert (
            name and Path(name).name == name and "/" not in name and "\\" not in name
        ), "Unsafe asset name"
        asset = root / name
        assert (
            asset.is_file()
            and not asset.is_symlink()
            and asset.stat().st_size <= 200_000_000
        ), "Asset missing or too large"
        signature = item["signature"]
        assert signature == (root / (name + ".sig")).read_text().strip(), (
            "Manifest signature differs from asset"
        )
        if name in verified:
            assert verified[name] == signature, "Conflicting signatures"
            continue
        sig = Path(temp) / "update.minisig"
        sig.write_bytes(base64.b64decode(signature, validate=True))
        subprocess.run(
            [a.minisign, "-Vm", str(asset), "-p", str(public), "-x", str(sig)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        verified[name] = signature
        print("Verified:", name)
checksums = []
for asset in sorted(root.iterdir()):
    if (
        asset.name.endswith((".exe", ".dmg", ".deb", ".AppImage", ".tar.gz"))
        and asset.name != "tampered.exe"
    ):
        checksums.append(
            hashlib.sha256(asset.read_bytes()).hexdigest() + "  " + asset.name
        )
(root / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
print("All four OS/architecture targets verified; checksums written.")
