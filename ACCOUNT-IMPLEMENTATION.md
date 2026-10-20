# Accounts, companion pairing and legal pages

Status: implementation in progress, 2026-10-20. Existing invitation tokens remain valid.

## Account and device flow

- Passwordless email sign-in with a short-lived, single-use code, bound to the
  initiating browser; bounded attempts and IP/address rate limits.
- Server-side sessions, hashed session secrets, Secure/HttpOnly/SameSite cookies,
  explicit same-origin checks for authenticated mutations and session expiry.
- Companion opens the system browser. A short-lived pairing code must be
  explicitly approved in an authenticated account. Polling uses a separate
  high-entropy secret; an approval code is not an upload token.
- Existing invitation credentials can be attached only after proving possession.
  Do not silently merge accounts by a provider's email address or move another
  account's device. Preserve existing character ownership and queued uploads.
- Account page lists connected devices and supports revocation. Revocation must
  cancel queued work before it can import more data. Account deletion must cover
  linked devices, measurements, sessions and pending authorizations.
- Discord, GitHub, Google, Microsoft and Apple require operator-owned OAuth/OIDC
  registrations. Only configured providers may appear as working login choices.
  Provider subject IDs identify users; linking requires explicit reauthentication.

## Legal pages

Private operator: Nils Keller, Mittlere Hasengasse 6, 64625 Bensheim, Germany.
Source: existing nilskeller.de imprint, confirmed by operator for GabbaProc.
Public contact: gabbaproc@kellerkind.info. Host separate bilingual `/imprint.html`
and `/privacy.html`; do not substitute an external imprint link.

Describe actual hosting, technical logs, local language preference, account and
device credentials, optional public names, pseudonymous IDs, combat archives,
upload queues, mail forwarding, backups, rights and deletion. The anonymous
upload option is pseudonymization, not irreversible anonymization. Provider
notices must match the providers actually enabled.

Current observations: Froxlor access logs rotate daily with seven retained files;
general Apache logs retain fourteen. PostgreSQL/spool backups currently have no
automatic retention. Do not claim deleted data disappears immediately from
backups. Define bounded retention and restoration deletion handling before
presenting a stronger guarantee. No analytics or marketing cookies are present.

References: GDPR Articles 6, 13 and 15–22; DDG §5; TDDDG §25. Legal content should
describe actual operation and remain reviewable; automated tests are not legal
certification.

## Acceptance checks

Test code expiry/replay/brute-force limits, session fixation and logout, cross-site
requests, pairing denial/expiry/concurrent redemption, existing-device ownership,
revocation with pending jobs, deletion and provider linking boundaries. Verify
SMTP delivery and sender authentication before enabling email sign-in publicly.
Test browser and companion in DE/EN. Migrate on staging first; retain the current
invitation flow until the new flow is verified end to end.

## Mailbox provisioned — 2026-10-20

Created the real `gabbaproc@kellerkind.info` mailbox through Froxlor's EmailAccounts
API; existing forwarding to `mail@nilskeller.de` was preserved. Initialized INBOX
and verified authenticated SMTP on `mail.nilskeller.de:587` with STARTTLS and
certificate validation. No test message was sent; end-to-end deliverability and
SPF/DKIM/DMARC still require verification. Froxlor's effective quota is currently
unlimited (requested 256 MiB is not enforced by the existing mail configuration).
Password is in a root-private host configuration file, not this repository.
The API container does not yet mount it. Email sign-in is not implemented/enabled.

Operator registration guide: [OAUTH-SETUP.md](OAUTH-SETUP.md).
