# Legal pages and mail checks — 2026-10-20

Operator confirmed a private, non-commercial project and authorized copying the
name/address from nilskeller.de into a separate local imprint. `/imprint.html`
and `/privacy.html` are bilingual and linked from every portal footer.

The notice reflects the currently deployed invitation/device-token system.
OAuth and email sign-in are explicitly not active. It describes pseudonymous
IDs, optional names, public aggregate data, local storage, logs, queues,
contact forwarding, deletion and the current absence of automatic backup expiry.
No legal certification or complete compliance audit is claimed.

## Verified operational facts

- Server network: RIPE HETZNER-fsn1-dc11, DE, 144.76.237.248.
- Domain Apache logs: `/var/customers/logs/nilskeller-kellerkind.info-*.log`,
  combined request format, daily rotation with seven rotated files. General
  Apache logs: fourteen daily rotations. Current files are additional.
- Mail logs: four weekly rotations plus current file.
- SPF includes `mx`; MX resolves to the sending host. DMARC exists with `p=none`.
- DKIM selector `mail202608`; `opendkim-testkey` reports key OK. Its "not secure"
  message concerns DNSSEC, not a failed DKIM key check.
- Authenticated SMTP with STARTTLS and certificate validation works on
  `mail.nilskeller.de:587`. One technical test message was accepted, DKIM-signed
  and delivered through Dovecot to both the project mailbox and the operator's
  configured forwarding destination. This is not a Gmail/Outlook delivery test.
- No passwords or login codes were included in the test message or repository.

## Operations follow-up

- Define and implement bounded backup retention. Current backups have no
  automatic expiry; do not promise a fixed deletion interval until implemented.
- Handle erasure requests across live storage and backup restoration. Before
  restoring publicly, reapply revocations and deletions; document each request
  privately and reconcile it against the restore. Never restore old permissions
  blindly. Privacy text does not itself implement this procedure.
- Review hosting contractual/data-processing arrangements with the account holder;
  these were not verified through the provider customer portal.
- Review contact messages when resolved and remove them when no longer needed.
- Update notice and consent UI before enabling accounts or additional providers.

Legal references consulted:

- [DDG §5](https://www.gesetze-im-internet.de/ddg/__5.html)
- [TDDDG §25](https://www.gesetze-im-internet.de/ttdsg/__25.html)
- [GDPR](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679)
- [Hessian supervisory authority](https://datenschutz.hessen.de/service/beschwerde-uebermitteln)

Validation: seven-page browser check, both languages, footer destinations,
390px viewport and no JavaScript errors; FastAPI legal routes return 200 and
unknown HTML routes remain 404.

Published and browser-verified on the live domain. Rollback webroot:
`public-before-legal-20261020-215043` alongside the live `public` directory.
