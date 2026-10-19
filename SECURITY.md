# Security and data handling

The Rust reader accepts a bounded, data-only subset of WoW SavedVariables. It rejects executable Lua, duplicate keys, trailing statements, oversized files, deep structures and unstable reads. A fresh JSON allowlist strips unrelated fields. Never replace it with a Lua interpreter.

The API independently validates bounded JSON, types, known effect IDs, counters, segment consistency, ownership, monotonic snapshots and sequences. It uses parameterized SQLite statements and database transactions. Tokens are random, stored hashed server-side and never included in URLs. Invites are one-use and expire after 24 hours. Quarantine is a heuristic, not anti-cheat verification.

Production runs as a dedicated unprivileged user on loopback behind Apache HTTPS. Do not expose Uvicorn directly. Only the local proxy may supply forwarded client addresses. Body size and read time are limited at the reverse proxy. Rate buckets use hashed client addresses and expire after 24 hours; proxy logs may additionally retain addresses according to the host's log rotation. No analytics, advertising cookies or external fonts are loaded by the website.

Keep SQLite backups private. Backups may retain deleted records until rotated; do not reintroduce deleted records when restoring. There is no automatic backup uploader. Raw SavedVariables, tokens, signing keys and personal exports must never be committed. `.secrets/` is ignored.

Limitations: data can be fabricated; invites do not establish game identity. First enrollment of a new UUID claims its upload ownership. Unknown user-supplied effects are not accepted in the public catalog. No hit-based proc probability or statistical confidence claim is made. Public bulk upload registration is deliberately disabled in the pilot.

Report vulnerabilities privately to the repository owner through GitHub private vulnerability reporting when enabled; otherwise contact the operator through the website legal contact. Do not post tokens or personal exports in issues.
