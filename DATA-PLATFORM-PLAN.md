# Plan: dauerhafte Messdaten, PostgreSQL und Upload-Warteschlange

Stand: 20.10.2026. Entwicklung auf `feature/durable-data-platform` begonnen;
Produktions-Datenbank und Website noch nicht umgestellt.

## Ziel und feste Entscheidungen

- Alle künftig gesammelten und erfolgreich übertragenen Kampfsegmente dauerhaft archivieren, einschließlich Kämpfen ohne Proc. Kein rollierendes Löschlimit auf dem Server.
- Abendliche Spitzen mit 100–200 Nutzern abfangen, ohne andere Dienste auf dem Server auszubremsen.
- PostgreSQL als eigener Docker-Service; API und Import-Worker als getrennte Services.
- **Alle persistenten Dateien liegen in festen Verzeichnissen des Host-Dateisystems. Keine Docker-managed/named/anonymous Volumes.** Container erhalten ausschließlich explizite Bind-Mounts für benötigte Daten.
- Dateibasierte Upload-Warteschlange mit einem zunächst einzelnen, begrenzten Worker. PostgreSQL verwaltet Importstatus und dauerhafte Messdaten.
- Keine Käufe, Infrastrukturänderungen oder Produktionsmigration im Planungsschritt.

## 1. Verzeichnisse und Installation auf dem Server

Vorgeschlagene Host-Pfade; vor Umsetzung an vorhandene Verzeichnisstruktur und freien Speicher anpassen:

| Host-Verzeichnis | Inhalt | Zugriff |
| --- | --- | --- |
| `/srv/gabbaproc/postgres/` | PostgreSQL-Daten einschließlich WAL | nur Datenbankdienst |
| `/srv/gabbaproc/spool/` | dauerhafte Upload-Dateien, temporäre und fehlerhafte Jobs | API und Worker |
| `/srv/gabbaproc/config/` | private Konfiguration und Zugangsdaten | gezielt, möglichst nur lesend |
| `/var/backups/gabbaproc/` | Datenbank-Dumps und Wiederherstellungsinformationen | Backup-Prozess |

Diese Ordner gehören zum Host und bleiben bei Container-Neuerstellung erhalten. Keine Daten im Container-Layer oder Webroot. PostgreSQL-Dateien nicht bei laufendem Dienst von Hand bearbeiten oder als gewöhnlichen Dateibaum sichern.

Installationsablauf:

1. Server-RAM, CPU, SSD-Platz, Dateisystem, bestehende Container und Backup-Ziele inventarisieren. Kein Mount über vorhandene Daten.
2. Unterstützte stabile PostgreSQL-Hauptversion und offizielles Image auswählen, getestete Version samt Digest festhalten. Den tatsächlich vom Image verwendeten Datenpfad vollständig per Bind-Mount abdecken, damit kein implizites anonymes Volume entsteht.
3. Host-Verzeichnisse mit passenden numerischen Dienst-UIDs und restriktiven Rechten anlegen; vorhandene SELinux-Regeln berücksichtigen, falls relevant.
4. PostgreSQL ohne veröffentlichte Ports starten. API und Worker erreichen die Datenbank ausschließlich im privaten Docker-Netz. Froxlor/Apache bleibt der öffentliche HTTPS-Einstieg für die API.
5. Eigene Datenbank und eingeschränkte Anwendungsrolle anlegen; Schemaänderungen über separate Migrationsrolle. Kein Superuser für API/Worker. Zugangsdaten außerhalb von Git.
6. Healthchecks, Wiederanlauf und Ressourcenlimits konfigurieren; PostgreSQL-Durabilität nicht zugunsten von Geschwindigkeit abschalten.

Die konkreten RAM- und CPU-Grenzen werden erst nach der Bestandsaufnahme festgelegt. Ein Host-Backup schützt nicht vor Ausfall desselben Hosts; eine zusätzliche externe Sicherung ist separat einzurichten.

## 2. Datenverlust bereits im Addon verhindern

Heute entfernt das Addon ältere Einträge nach 300 Segmenten. Der Server kann solche bereits verworfenen Daten nicht rekonstruieren.

- Den sichtbaren Verlauf bei 300 Einträgen belassen, aber daneben ein dauerhaftes, nach Sammlungs-ID getrenntes Exportarchiv führen.
- Jedes abgeschlossene Segment genau einmal mit stabiler ID, Startzeit, Dauer, Gebietstyp, numerischen Gebiets-/Instanzkennungen soweit verfügbar, Effekten und Eignung speichern. Vorhandene Felder und spätere Schemaerweiterungen klar versionieren.
- Ein Zähler-Reset beginnt eine neue Sammlung und entfernt keine noch nicht gesicherten Archive. Alte und neue Sammlung müssen beide exportierbar bleiben.
- Laufende Segmente dürfen durch neuere Fassungen ergänzt werden; abgeschlossene Segmente werden unveränderlich. Fehlende Finalisierung nach einem Spielabsturz wird als unvollständig angezeigt.
- Nicht erkannte/custom Effekte dürfen nicht unbemerkt verschwinden: entweder im versionierten Messschema als ungeprüfte IDs archivieren und von öffentlichen Auswertungen trennen oder mit einer ausdrücklichen Lückenmeldung behandeln.
- Kein stilles Wegwerfen bei Größenlimits. Archivgröße anzeigen, warnen und eine ausdrücklich bestätigte Bereinigung nur gesicherter Bereiche vorsehen. Unbegrenzte Speicherung im WoW-Arbeitsspeicher ist nicht realistisch; Speicherbedarf und Ladezeit messen.

**WoW-Grenze:** SavedVariables werden normalerweise bei `/reload` oder Logout auf Disk geschrieben. Die Companion-App kann noch nicht geschriebene Kämpfe nicht lesen. Sie darf die SavedVariables einer laufenden WoW-Instanz nicht verändern. Eine automatische Rückbestätigung in das Addon wird daher nicht vorausgesetzt; eine spätere Bereinigungsfunktion braucht einen separat getesteten, expliziten Bestätigungsweg. Bereits verlorene Altsegmente und ein Spielabsturz vor dem Speichern bleiben erkennbare Lücken.

„Alle Daten“ bedeutet die vom Addon erfassten Messdaten; es existiert bisher kein vollständiges Roh-Combat-Log aller Treffer. Eine spätere Proc-Chance pro Treffer würde zusätzliche Erfassung geeigneter Angriffsversuche benötigen.

## 3. Companion: lokale Versandablage und kleine Uploads

- Beim Erkennen neuer SavedVariables ausgewählte Charakterdaten sicher parsen und in einer eigenen lokalen, persistenten Versandablage sichern.
- Große Archive in begrenzte Pakete aufteilen; keine immer größer werdenden Komplettuploads. Parser-, Datei- und HTTP-Grenzen gemeinsam anpassen und testen.
- Paket-ID, Schema-Version, Sammlung, Segment-IDs und Inhaltsprüfsumme bilden eine stabile Identität. Gesamtzähler sind versionierte Momentaufnahmen und werden niemals aus wiederholten Uploads addiert.
- Lokale Pakete bleiben bis zur bestätigten Verarbeitung erhalten. `202 Accepted` bedeutet nur „in Warteschlange“, nicht „importiert“.
- Jobstatus gezielt abfragen; Polling getrennt vom Upload begrenzen. Bei Netzfehlern, `429` und `503` mit exponentiellem Backoff, Zufallsstreuung und `Retry-After` erneut versuchen.
- Bestehende Intervalle 5–60 Minuten behalten; automatische Startzeiten leicht verteilen, damit nicht alle Clients gleichzeitig hochladen.
- UI in Deutsch/Englisch: lokal gesichert, wartet, verarbeitet, abgelehnt, unvollständige Historie. Manueller Upload bleibt möglich.
- Anonyme Nutzlast enthält keine Namen, Accountnamen, Installationspfade oder frei formulierten lokalen Texte. Benannte Identitäten getrennt von unveränderlichen Messpaketen übertragen.

## 4. Annahme und dateibasierte Warteschlange

```text
WoW → SavedVariables → lokale Companion-Versandablage
    → HTTPS-API → private Upload-Datei auf dem Host
    → begrenzter Import-Worker → PostgreSQL → Website
```

Die API authentifiziert und prüft Größen, Format sowie Struktur. Sie führt keinen vollständigen Messdatenimport im HTTP-Request aus. Zulässig ist ausschließlich das definierte JSON-Messformat; keine ausführbaren Lua-Dateien, beliebigen Anhänge oder Archive.

Dateien erhalten serverseitig erzeugte Namen, keine vom Nutzer vorgegebenen Pfade. Zuerst in eine temporäre Datei auf demselben Dateisystem schreiben, Datei synchronisieren, atomar fertigstellen und Verzeichnis synchronisieren. Danach den Job im PostgreSQL-Jobregister dauerhaft registrieren. Erst wenn beides erfolgreich ist, folgt `202` mit Job-ID.

Dateisystem und Datenbank bilden keine gemeinsame Transaktion. Deshalb ausdrücklich vorsehen:

- Abbruch nach Dateierstellung, aber vor Jobregistrierung: sicherer Abgleich anhand unveränderlicher Jobmetadaten; Wiederholung erkennt bereits vorhandenen Inhalt.
- Job ohne Datei: Fehlerstatus und Alarm, niemals stillschweigend als importiert markieren.
- Abbruch nach Datenbankimport: Wiederholung erkennt denselben Import und erzeugt keine doppelten Daten.
- Alte temporäre Dateien und verwaiste Dateien nur nach dokumentierter Karenz und Abgleich bereinigen; keine noch aktiven Schreibvorgänge entfernen.

Jobs werden über atomare Datenbankzustandswechsel mit Lease und Ablaufzeit beansprucht. Bei später mehreren Workern kann `FOR UPDATE SKIP LOCKED` konkurrierende Jobauswahl ermöglichen. Abgelaufene Leases werden wieder aufgenommen; ein alter Worker darf nach Lease-Verlust keinen Import mehr bestätigen.

Ein Worker startet mit begrenzter Batchgröße und konfigurierbaren Pausen. Wiederholbare Fehler gehen verzögert zurück in die Warteschlange; endgültig ungültige Pakete erhalten einen nachvollziehbaren Fehlerstatus. Fehlerhafte Dateien haben eine begrenzte Aufbewahrung, gültige Messdaten keine automatische Ablauffrist.

Nach Datenbank-Commit und bestätigtem Jobstatus können erfolgreich verarbeitete Transportdateien entfernt werden. Die Messdaten bleiben in PostgreSQL. Eine zusätzliche ewige Ablage identischer Upload-Dateien ist für die Datenerhaltung nicht erforderlich.

## 5. Dauerhaftes Datenmodell und Parallelität

- PostgreSQL-Tabellen für Geräte/Berechtigungen, getrennte Charakteridentitäten, Sammlungen, Importpakete, Jobs, Segmente, Segment-Effekte und versionierte Gesamtzähler.
- Eindeutige Schlüssel für `(Charakter, Sammlung, Segment-ID)` und Paket-ID/Prüfsumme verhindern Doppelzählungen.
- Derselbe abgeschlossene Kampf mit abweichendem Inhalt ist ein Konflikt und wird nicht still überschrieben. Aktive Segmente haben monotone Revisionen; abgeschlossen darf nicht wieder aktiv werden.
- Alte Pakete dürfen bisher fehlende historische Segmente nachliefern, ohne neuere Gesamtzähler zurückzusetzen. Die bisherige pauschale Ablehnung älterer Exportsequenzen reicht dafür nicht.
- Importtransaktion sperrt nur die betroffene Sammlung beziehungsweise Identität. Unabhängige Charaktere können parallel verarbeitet werden.
- Kleine, begrenzte Connection-Pools und kurze Transaktionen; blockierende DB-/Dateiarbeit nicht im asynchronen HTTP-Eventloop ausführen.
- Bereits bestehende Gesamtzähler als Ausgangsbestand erhalten. Historische Segmente daraus nicht erfinden und nicht nochmals auf Gesamtzähler addieren.
- Quarantäne und Datenqualität getrennt von Speicherung behandeln: auffällige Messungen bleiben überprüfbar, aber fließen nicht automatisch in öffentliche Statistiken ein.
- Identitätsänderung, Tokenwiderruf und Löschung müssen auch ausstehende Jobs erfassen. Alte Uploads dürfen gelöschte Daten oder zuvor entfernte Namen nicht wiederherstellen; dafür einen Berechtigungs-/Löschstand prüfen.

## 6. Kapazität und Schutz des übrigen Servers

Planungsannahme: 200 aktive Nutzer. Bei fünf Minuten Intervall ergeben sich im Mittel 40 Synchronisationen pro Minute. Die tatsächliche Requestzahl hängt von Charakteranzahl, Paketgröße und Rückständen ab; ein Abendstart kann trotzdem 200 gleichzeitige Clients erzeugen.

- Lasttest mit 100 und 200 gleichzeitig startenden Clients, mehreren Charakteren, großen Rückständen, Wiederholungen und laufenden Website-Abfragen.
- Ressourcen für API, Worker und Datenbank begrenzen. Zunächst ein Worker; Parallelität nur anhand gemessener Verarbeitungsgeschwindigkeit erhöhen.
- Pro-Token-Fairness, begrenzte gleichzeitige Uploads und feste Paketgrößen verhindern, dass ein Nutzer den gesamten Speicher oder Worker belegt.
- Quotas für Warteschlangenbytes und Jobanzahl sowie eine freie Speicherreserve festlegen. Bei ausgeschöpfter Kapazität vor Annahme mit `429`/`503` und Wiederholungshinweis ablehnen; bereits bestätigte Pakete nicht verwerfen.
- Messen: Annahme-Latenz, Queue-Alter/-Größe, Importdauer, Fehler, CPU, RAM, I/O, DB-Verbindungen und freier Speicher. Öffentliche Statistiken bei Bedarf kurz cachen und inkrementell vorberechnen.
- Vorläufiges Testziel: keine verlorenen oder doppelt gezählten bestätigten Pakete; Status/Website bleiben erreichbar; ein definierter 200-Client-Burst wird auf dem verfügbaren Host innerhalb einer vorab festgelegten Zeit abgearbeitet. Konkrete Latenz-/Zeitbudgets nach Hardwareinventur festlegen und dokumentieren.

Rate-Limits bleiben Schutzmechanismen, werden aber an Paketuploads, getrennte Statusabfragen und Mehrcharakter-Nutzung angepasst. Keine pauschale Zusage, dass jede Hardware diese Last schafft.

## 7. Migration, Sicherungen und Rückweg

1. SQLite konsistent sichern und Wiederherstellung auf einer Testkopie prüfen.
2. PostgreSQL-Schema samt versionierten Migrationen erstellen und Testmigration durchführen: Geräte/Token-Hashes, Einladungen, Besitzer, Sichtbarkeit, Sammlungen, Gesamtzähler und vorhandene Segmente übernehmen.
3. Zeilenzahlen, Schlüsselbeziehungen, Summen und Prüfsummen vergleichen. Token und Charakterzuordnung müssen erhalten bleiben.
4. Neue API zunächst mit Testdaten und getrennten Host-Verzeichnissen testen. Bestehende Clients über einen kompatiblen Importweg unterstützen, bis sie Jobstatus verstehen; ihnen nicht kommentarlos `202` als fertigen Import zurückgeben.
5. Kurzes Wartungsfenster für Schreibzugriffe, abschließendes SQLite-Backup, finale Migration und Umschaltung. Alte SQLite-Daten unverändert als Rückfallbestand sichern.
6. Funktionstest mit Wiederholungen, anonymen/benannten Uploads, Widerruf, Löschung, Statistikvergleich und Wiederanlauf.
7. Rückweg vor Öffnung des neuen Schreibbetriebs testen. Nach neuen PostgreSQL-Imports reicht das Zurückspielen der alten SQLite-Datei nicht: neue Daten müssen erhalten und kontrolliert nachgeführt werden. Bei Fehlern zuerst Schreibannahme pausieren, nicht blind zurückschalten.

PostgreSQL-Backups mit `pg_dump`/`pg_restore`, dokumentierter Aufbewahrung und regelmäßigen Wiederherstellungstests. Für ein geringeres Verlustfenster zusätzlich WAL-Archivierung/PITR planen. Backup-Sätze berücksichtigen auch noch nicht importierte Spooldateien und private Konfiguration; beim Restore Jobs und Dateien abgleichen. Tägliche Dumps allein sichern keine seitdem angenommenen Uploads gegen Hostverlust.

## 8. Umsetzungspakete und Abnahme

1. Protokoll und Datenmodell einschließlich Archiv, Paketidentität, Datenschutz und Statuszuständen festlegen.
2. PostgreSQL, Migration, dateibasierte Queue und Worker lokal implementieren.
3. Addon-Archiv und Companion-Versandablage inklusive Wiederholungen und UI umsetzen.
4. Tests: mehr als 300 Segmente, Reset, Offlinephasen, >8-MiB-Archive, Paketgrenzen, Reihenfolgevertauschung, doppelte/konkurrierende Imports, Worker-Abbruch an jedem Übergang, voller Datenträger, DB-Ausfall, ungültige Payloads und Löschung während wartender Imports.
5. 200-Client-Lasttest sowie Backup/Restore durchführen und Ergebnisse dokumentieren.
6. Konkrete Host-Konfiguration und Migration prüfen, dann separat deployen. Website-Texte und Versionshinweise an tatsächliche Archiv- und Kompatibilitätsgarantien anpassen.

Erst nach diesen Tests von einer dauerhaften Archivierung sprechen. Alte Datenlücken bleiben sichtbar; nicht gespeicherte WoW-Daten können weder Companion noch Server nachträglich retten.

## 9. Ergänzung: Nutzerkonten und WoW-Datenportal

Entscheidung vom 20.10.2026: dunkles, blaues WoW-Datenportal mit eigenständigen Bereichen für Messwerte, Vergleiche, Datenqualität, Downloads und persönliches Konto. Keine lange Werbe-Landingpage. Deutsch und Englisch bleiben gleichwertig.

Ein GabbaProc-Konto besitzt Charakterzuordnungen und mehrere widerrufbare Upload-Geräte. Öffentliche Daten lassen sich ohne Anmeldung lesen. Login-Anbieter sind nur Zugangswege zu diesem internen Konto. Stand 22.10.2026: **Battle.net, GitHub, Discord und passwortloser E-Mail-Zugang sind implementiert und live aktiviert.** Mailversand und Companion-Verknüpfung sind eingerichtet und über öffentliches HTTPS geprüft. Google, Microsoft und Apple bleiben deaktiviert. Die vollständige Anmeldung mit echter Anbieter-Freigabe für Battle.net, GitHub und Discord bleibt als Abnahme offen.

- Anbieter-Identitäten über unveränderliche Provider-/Issuer-/Subject-Kombinationen zuordnen, nicht über Anzeigenamen oder E-Mail-Adressen. Verknüpfung zusätzlicher Anbieter nur aus einem erneut bestätigten bestehenden Konto; keine automatische Kontozusammenführung bei gleicher E-Mail.
- Bestehende Geräte und Messdaten nur gegen Nachweis des bisherigen Geräte-Tokens an ein Konto anbinden. Eine Charakter-UUID allein beweist keine Berechtigung.
- Companion öffnet den Systembrowser zur Anmeldung und expliziten Gerätefreigabe. Ein kurzlebiger, einmaliger Kopplungsvorgang liefert einen eigenen widerrufbaren Gerätezugang; Provider-Tokens gehören nicht in die Companion-App.
- Für OAuth/OIDC eine gepflegte Bibliothek einsetzen; state, Nonce, PKCE soweit unterstützt, Signaturen, Issuer, Audience, Ablauf und exakte Callback-Adressen prüfen. GitHub und Discord verwenden ihren jeweiligen OAuth-Profilendpunkt statt eines vorausgesetzten OIDC-ID-Tokens.
- Browser-Sitzungen serverseitig verwalten, Cookie Secure/HttpOnly, CSRF-Schutz für Änderungen und frische Anmeldung für Verknüpfen, Löschen und Gerätefreigaben. Apple-Callback mit POST benötigt gesonderte SameSite-/State-Behandlung.
- E-Mail-Zugang mit kurzlebigen Einmallinks oder Einmalcodes, Rate-Limits und generischen Antworten. Kein Passwortbestand. Versand erst nach SMTP-Konfiguration und Prüfung von Absender, SPF/DKIM/DMARC aktivieren; keine Anmeldetokens in Logs.
- Die öffentliche Sichtbarkeit eines Charakters ist unabhängig vom Konto-Login. Login-Mail und Providerprofil werden nicht zu öffentlichen Beitragsnamen.
- Accountlöschung und Gerätewiderruf umfassen wartende Jobs. Das Trennen eines Login-Anbieters darf nicht versehentlich den letzten Zugangsweg entfernen.
- Einladungen und manuelle Token-Einrichtung sind entfernt. Die Companion-App wird ausschließlich über die Anmeldung im Browser und die ausdrückliche Gerätefreigabe eingerichtet.
- Nur konfigurierte und getestete Anbieter als Login-Schaltflächen anbieten. Keine scheinbar funktionierenden Platzhalter. Live-Abnahme jedes Anbieters erfordert dessen Registrierung und Zugangsdaten außerhalb von Git.

Einrichtung: je Anbieter eine Web-Anwendung für `https://gabbaproc.kellerkind.info` registrieren, exakte Callbacks unter `/api/auth/<anbieter>/callback` hinterlegen und minimale Login-Berechtigungen verwenden. Battle.net verwendet `https://gabbaproc.kellerkind.info/api/auth/battlenet/callback`. Weitere geplante Anbieter: Google, Microsoft mit expliziter Unterstützung persönlicher Konten und Apple nach Services-ID/App-ID/Schlüssel-Konfiguration. Aktueller Einrichtungsstatus und Anbieter-Portale stehen in [OAUTH-SETUP.md](OAUTH-SETUP.md).

Primärquellen zur Anmeldung: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [GitHub OAuth](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps), [Discord OAuth](https://discord.com/developers/docs/topics/oauth2), [Microsoft-Kontotypen](https://learn.microsoft.com/en-us/security/zero-trust/develop/identity-supported-account-types), [Apple-Webkonfiguration](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web).

## Primärquellen

- [Offizielles PostgreSQL-Docker-Image und Datenpfade](https://hub.docker.com/_/postgres)
- [PostgreSQL: SELECT und SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html)
- [PostgreSQL: konsistente Dumps und Wiederherstellung](https://www.postgresql.org/docs/current/backup-dump.html)


## Security and performance review — 2026-10-22

Implementation prepared and locally tested:

1. Existing-identity sign-in within ten minutes is required to link an identity
   or delete an account. Linking does not renew this deadline. Browser sessions
   and sign-out-everywhere are available; duplicate account JSON keys are rejected.
2. Companion TLS verifier updated to rustls-webpki 0.103.16. Weekly/manual/PR
   dependency audit added. Transitive GTK/updater advisories remain visible in
   audit output; this does not claim all dependencies are vulnerability-free.
3. Addon 0.1.5 reuses immutable completed segments, omits duplicate export history,
   indexes attack counters, reads combat events once, throttles combat UI updates,
   and defers automatic exports during combat. Archive detail capacity is visible
   and preserved across reset; cleanup is explicit after verified upload.
4. Both import paths enforce account-wide budgets: 128 MiB stored detail JSON
   plus per-row allowance, 50,000 segments, 200 collections, 2,000 imports/hour.
   Override with GABBAPROC_ACCOUNT_BYTES/SEGMENTS/COLLECTIONS/IMPORTS_HOUR.
   Processed/rejected/cancelled receipts expire after 90 days; replay is idempotent.
   Public aggregates are cached 15 seconds with bounded concurrency/rate/cache
   size. Public names are never cached. Group/class filters precede analysis LIMIT.
   Global email allowance is configurable via GABBAPROC_EMAILS_HOUR (default 500).
5. Companion previews run outside the state lock on a blocking worker. UI previews
   show one actual packet plus total packet count. Parser allocations have a
   conservative structural budget. Durable packet data is separate from progress;
   anonymous-mode transitions survive restart without restoring public names.
6. LIVE: native Froxlor SubDomains HSTS is 31536000 for gabbaproc.kellerkind.info,
   without includeSubDomains/preload. Apache configtest and public header verified.

Validation: PostgreSQL 53 passing / 1 skipped; SQLite 49 passing / 5 skipped;
addon Lua and six packaging tests passing; 15 Rust core + 1 Companion tests passing; browser parser and account reauth
Playwright checks passing. Synthetic Lua export measurements are not WoW FPS.
Production API/worker/web rollout completed on 2026-10-22 after explicit user
approval. A fresh PostgreSQL/spool backup succeeded before the additive migration.
API and worker run gabbaproc:security-20261022; public pages, aggregate endpoints,
HSTS and served asset hashes were verified. A temporary account confirmed stale
session rejection for linking/deletion, session listing, logout-all, duplicate JSON
rejection and storage ledger backfill. Test account/sessions were removed; no email
was sent. Addon/Companion packages remain local artifacts, not public releases.
