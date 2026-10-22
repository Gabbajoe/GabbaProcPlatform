"""Operator-only CLI. Run on the server, never expose as an HTTP endpoint."""

import argparse
from .storage import init, connect

p = argparse.ArgumentParser()
p.add_argument("action", choices=["list", "approve", "revoke"])
p.add_argument("id", nargs="?")
a = p.parse_args()
init()
with connect() as db:
    if a.action == "list":
        for row in db.execute("SELECT character,collection,status,updated FROM snapshots"):
            print(dict(row))
    elif a.action == "approve":
        db.execute("UPDATE snapshots SET status=? WHERE collection=?", ("community", a.id))
    elif a.action == "revoke":
        db.execute("UPDATE devices SET revoked=1 WHERE id=?", (a.id,))
