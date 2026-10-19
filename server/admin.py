"""Operator-only CLI. Run on the server, never expose as an HTTP endpoint."""

import argparse
from .storage import init, invite, connect

p = argparse.ArgumentParser()
p.add_argument("action", choices=["invite", "list", "approve", "revoke"])
p.add_argument("id", nargs="?")
a = p.parse_args()
init()
if a.action == "invite":
    print(invite())
else:
    with connect() as db:
        if a.action == "list":
            for row in db.execute(
                "SELECT character,collection,status,updated FROM snapshots"
            ):
                print(dict(row))
        elif a.action == "approve":
            db.execute(
                'UPDATE snapshots SET status="community" WHERE collection=?', (a.id,)
            )
        elif a.action == "revoke":
            db.execute("UPDATE devices SET revoked=1 WHERE id=?", (a.id,))
