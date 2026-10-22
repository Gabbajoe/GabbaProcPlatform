# GabbaProc: OAuth-Anwendungen einrichten

Stand: 21.10.2026. Discord, GitHub und E-Mail sind implementiert und live aktiviert.
E-Mail-Anmeldung und Geräteverknüpfung wurden über öffentliches HTTPS geprüft.
Der vollständige Discord-/GitHub-Login mit echter Anbieter-Freigabe muss noch vom
Betreiber durchgespielt werden. Google, Microsoft und Apple bleiben deaktiviert.
Die Companion-App wird über die Kontoverknüpfung eingerichtet.

## Reihenfolge und Aufgabenteilung

1. **Erledigt am 20.10.2026:** Eigene Impressums- und Datenschutzseite sind live (DE/EN); SMTP, lokale Zustellung und Weiterleitung wurden geprüft.
2. Discord und GitHub registrieren und jeweils vollständig testen.
3. Google hinzufügen, öffentliche Freigabe/Branding prüfen.
4. Microsoft hinzufügen. Apple separat nach Klärung der Developer-Mitgliedschaft.
5. E-Mail-Anmeldung und Companion-Verknüpfung parallel fertigstellen.

Du erstellst die Anwendungen in deinen jeweiligen Anbieter-Konten. Ich baue die
Server-Anbindung und die Companion-Verknüpfung, hinterlege die Zugangsdaten privat
und teste den Ablauf. Anbieter-Konten bitte mit Zwei-Faktor-Anmeldung schützen.

Für unsere Architektur reicht pro Anbieter eine **Web-Anwendung**. Windows,
macOS und Linux öffnen den normalen Browser und verbinden sich danach mit dem
GabbaProc-Konto. Keine separaten Google-/Discord-Anwendungen pro Betriebssystem,
keine Anbieter-Secrets in der herunterladbaren Companion-App.

## Gemeinsame Angaben zum Kopieren

| Feld | Wert |
| --- | --- |
| App-Name | GabbaProc |
| Betreiber | Nils Keller, privates Projekt |
| Homepage | `https://gabbaproc.kellerkind.info/` |
| Kontakt | `gabbaproc@kellerkind.info` |
| Datenschutz | `https://gabbaproc.kellerkind.info/privacy.html` |
| Impressum | `https://gabbaproc.kellerkind.info/imprint.html` |
| Beschreibung | Community proc statistics for World of Warcraft Classic Era and Hardcore. |

Rechtstext-URLs erst zur Prüfung einreichen, wenn die Seiten tatsächlich erreichbar
und inhaltlich vollständig sind. Falls ein Anbieter zusätzlich Nutzungsbedingungen
verlangt, eine eigene Seite erstellen; nicht das Impressum als AGB ausgeben.

### Verbindlich geplante Callback-URLs

Diese URLs exakt übernehmen, ohne abschließenden Slash oder Wildcards:

| Anbieter | Callback / Redirect URI |
| --- | --- |
| Battle.net | `https://gabbaproc.kellerkind.info/api/auth/battlenet/callback` |
| Discord | `https://gabbaproc.kellerkind.info/api/auth/discord/callback` |
| GitHub | `https://gabbaproc.kellerkind.info/api/auth/github/callback` |
| Google | `https://gabbaproc.kellerkind.info/api/auth/google/callback` |
| Microsoft | `https://gabbaproc.kellerkind.info/api/auth/microsoft/callback` |
| Apple | `https://gabbaproc.kellerkind.info/api/auth/apple/callback` |

Für Entwicklung separate Test-Registrierungen verwenden. Keine wechselnden
localhost-Adressen oder privaten Entwicklungsserver in die produktive Konfiguration
übernehmen. Die endgültigen Test-URLs legen wir mit der Testumgebung fest.

## 1. Discord

Portal: [Discord Developer Portal](https://discord.com/developers/applications).

1. **New Application** → `GabbaProc`.
2. In den allgemeinen Angaben Beschreibung, Icon und verfügbare Website-/Datenschutzfelder pflegen.
3. Unter **OAuth2** die Discord-Callback-URL aus der Tabelle als Redirect speichern.
4. **Client ID** notieren; **Client Secret** erzeugen und privat speichern.
5. Unser Server verwendet den Authorization-Code-Ablauf mit `identify`. Eine
   E-Mail-Adresse ist für die Zuordnung über die Discord-Benutzer-ID nicht nötig.
   `email` erst ergänzen, wenn wir sie tatsächlich benötigen und transparent erklären.
6. Keine Bot-, Nachrichten-, Serververwaltungs- oder Guild-Berechtigungen auswählen.

Benötigt: Client ID und Client Secret. Ein Bot-Token ist hierfür ungeeignet.

Quelle: [Discord OAuth2-Dokumentation](https://docs.discord.com/developers/topics/oauth2).

## 2. GitHub

Portal: [GitHub Developer settings → OAuth Apps](https://github.com/settings/developers).

1. **New OAuth App** auswählen.
2. Application name: `GabbaProc`.
3. Homepage URL: `https://gabbaproc.kellerkind.info/`.
4. Authorization callback URL: GitHub-Callback aus der Tabelle.
5. Registrieren und ein Client Secret erzeugen.
6. Für unsere Anmeldung genügt die öffentliche Benutzeridentität; keine `repo`-,
   Organisations- oder Schreibberechtigungen anfordern. `user:email` wäre nur bei
   tatsächlichem Bedarf an privaten E-Mail-Adressen zusätzlich nötig.

Benötigt: Client ID und Client Secret. Keinen Personal Access Token verwenden.
GitHub empfiehlt generell auch die Prüfung einer GitHub App; für unseren reinen
Login planen wir hier bewusst eine OAuth App ohne Repository-Zugriff.

Quellen: [OAuth App anlegen](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app),
[OAuth-Anmeldung](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).

## 3. Google

Portal: [Google Cloud Console](https://console.cloud.google.com/).

1. Eigenes Projekt `GabbaProc` anlegen oder auswählen.
2. Unter **Google Auth Platform** Branding, Audience und Data Access konfigurieren.
3. Zielgruppe **External**, zuerst mit Testnutzern. Kontakt und eigene Website-/Datenschutz-URLs eintragen.
4. Als autorisierte Domain `kellerkind.info` hinterlegen; nötigen Eigentumsnachweis
   durchführen. DNS-Verifizierung lässt sich über die bestehende Domainverwaltung erledigen.
5. Unter **Clients** einen OAuth-Client vom Typ **Web application** erstellen.
6. Google-Callback aus der Tabelle unter **Authorized redirect URIs** eintragen.
   Für unseren serverseitigen Redirect-Ablauf werden keine JavaScript-Origins benötigt.
7. Nur `openid email profile` für die Anmeldung anfordern, keine Gmail-/Drive-APIs.
8. Client ID und Client Secret privat speichern.
9. Vor öffentlichem Betrieb Teststatus verlassen und die im Portal verlangte
   Branding-/Domainprüfung abschließen. Ein Test-Client ist kein öffentlicher Login.

Quellen: [Webserver-OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[Branding und Verifikation](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification).

## 4. Microsoft

Portal: [Microsoft Entra Admin Center](https://entra.microsoft.com/).

1. Voraussetzungen für App-Registrierungen im eigenen Entra-Verzeichnis prüfen.
2. **App registrations → New registration** → `GabbaProc`.
3. Für breite Community-Nutzung **Any Entra ID Tenant + Personal Microsoft accounts**
   auswählen. Nur ein eigenes Firmenverzeichnis würde private Outlook-/Xbox-Konten ausschließen.
4. Redirect-Plattform **Web**, Microsoft-Callback aus der Tabelle.
5. Application (client) ID notieren; unter **Certificates & secrets** ein Client Secret erstellen.
6. Den Secret-**Wert**, nicht nur dessen ID, privat sichern; Ablaufdatum notieren.
7. Für OIDC `openid profile email` verwenden. Kein Mail-, Datei- oder Kalenderzugriff;
   standardmäßig hinzugefügte, nicht benötigte Graph-Berechtigungen entfernen.

Geplant ist die Authority `common`; der Server muss Issuer und Tenant bei
Mehrmandanten-Anmeldungen korrekt validieren. Keine Implicit-/Hybrid-Flows aktivieren.

Quellen: [Anwendung registrieren](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app),
[Redirect-URI](https://learn.microsoft.com/entra/identity-platform/how-to-add-redirect-uri),
[Authority-Konfiguration](https://learn.microsoft.com/en-us/entra/identity-platform/msal-client-application-configuration).

## 5. Apple – optional später

Apple-Web-Login benötigt eine passende Developer-Konfiguration mit primärer
App ID, Services ID und privatem Schlüssel. Die reguläre Developer-Mitgliedschaft
kostet laut Apple 99 USD jährlich bzw. den lokalen Preis; nichts automatisch buchen.

1. Im [Apple Developer Account](https://developer.apple.com/account/) eine primäre
   App ID mit **Sign in with Apple** konfigurieren, gegebenenfalls für die macOS-App.
2. Eine **Services ID**, beispielsweise `info.kellerkind.gabbaproc.web`, anlegen
   und der primären App ID zuordnen.
3. Webdomain `gabbaproc.kellerkind.info` und Apple-Return-URL aus der Tabelle registrieren.
4. Sign-in-with-Apple-Schlüssel erzeugen; `.p8` sicher herunterladen.
5. Team ID, Key ID und Services ID notieren. Der Server erzeugt daraus zeitlich
   begrenzte Client-Secret-JWTs; Erneuerung gehört zum Betrieb.
6. Für Mails an Apple-Relay-Adressen später auch die Absender-Konfiguration prüfen.

Die Implementierung muss Apples POST-Callback und einmalig gelieferte Profildaten
berücksichtigen. Provider-Schlüssel und App-Update-Signaturen erfüllen verschiedene Zwecke.

Quellen: [Apple Web-Konfiguration](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web),
[Umgebung und Schlüssel](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple),
[Mitgliedschaft](https://developer.apple.com/help/account/membership/program-enrollment/).

## E-Mail-Anmeldung

Dafür wird keine OAuth-App registriert. Implementiert: ein achtstelliger Einmalcode
mit zehn Minuten Laufzeit und höchstens fünf Eingabeversuchen. Die HTML-Mail enthält
einen Anmelde-Button; die Textalternative enthält Code und Link. Der Link übergibt
Code und Challenge im URL-Fragment, das nicht an den Webserver gesendet und nach
dem Vorbelegen aus der Adresszeile entfernt wird. Die Bestätigung erfolgt im
Browser der ursprünglichen Anfrage. Versandlimits: 5 pro Adresse, 10 pro IP und
100 insgesamt je Stunde.

`gabbaproc@kellerkind.info` ist als echtes Postfach eingerichtet; die bestehende
Weiterleitung an `mail@nilskeller.de` ist erhalten. SMTP-Anmeldung über
`mail.nilskeller.de:587` mit STARTTLS und Zertifikatsprüfung wurde erfolgreich getestet. Ein Postfach allein aktiviert
noch keinen Login: SMTP-Zugang, TLS, SPF/DKIM/DMARC, Versandtests und der Code-Ablauf
müssen funktionieren. Kein Zugriff auf private Benutzer-Postfächer erforderlich.

## Companion mit dem Konto verbinden

1. In der neuen App **Mit Konto verbinden** klicken.
2. App fordert eine kurzlebige Geräte-Verknüpfung beim GabbaProc-Server an.
3. Der normale Browser öffnet unsere Kontoseite; dort Anbieter oder E-Mail auswählen.
4. Gerätecode vergleichen und Verbindung ausdrücklich bestätigen.
5. Die App erhält einen eigenen widerrufbaren Upload-Zugang und speichert ihn im System-Schlüsselbund.
6. Unter **Mein Konto → Geräte** lassen sich Verbindungen später widerrufen.

Anbieter-Tokens werden nur serverseitig zur Identitätsabfrage verwendet.
Konten werden nicht automatisch anhand gleicher E-Mail-Adressen zusammengeführt.
Mehrere Login-Anbieter lassen sich nur aus einem bereits angemeldeten Konto verbinden.

Technische Grundlage für den Geräteablauf: [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628.html).

## Zugangsdaten sicher übergeben

- Client IDs darfst du nennen; Client Secrets, SMTP-Passwort und Apple `.p8` nicht in den Chat kopieren.
- Secrets in privaten Dateien außerhalb des Repositories speichern. Geplanter
  Serverbereich: `/var/lib/gabbaproc-postgres/config/`, gezielt read-only in die API einbinden.
- Wenn du sie lokal im Passwortmanager oder einer privaten Datei hinterlegt hast,
  genügt mir die Angabe des Speicherorts. Keine Zugangsdaten in Screenshots zeigen.
- OAuth-Secrets gehören nicht in GitHub-Build-Secrets: Der Desktop-Build benötigt sie nicht.
- Ablaufdatum und Rotation dokumentieren, ohne den Secret-Wert zu dokumentieren.

## Abnahme je Anbieter

- Login, Abbruch, Logout, abgelaufener Code, Wiederverwendung und falscher `state` getestet.
- Bei OIDC Signatur, Issuer, Audience und Nonce geprüft; PKCE verwenden, soweit unterstützt.
- Keine Credentials in URLs der Companion-App, Frontend-Speichern oder Logs.
- Ein bestehendes Konto behält seine Messdaten und Geräte nach erneutem Login.
- Verknüpfung mit einem zweiten Anbieter kann kein fremdes Konto übernehmen.
- Datenschutz nennt den tatsächlich aktivierten Anbieter und die erhaltenen Daten.
- Ein deaktivierter/nicht konfigurierter Anbieter erscheint nicht als funktionierender Login.

**Als Erstes kannst du Discord und GitHub anlegen.** Danach reichen die Nachricht
„Discord/GitHub angelegt“ und der private Speicherort der Zugangsdaten, um die
Integration und den ersten vollständigen Verbindungstest fortzusetzen.


## Battle.net

Register a web client at https://community.developer.battle.net/access/clients.
Redirect URI: `https://gabbaproc.kellerkind.info/api/auth/battlenet/callback`.
Configure `GABBAPROC_BATTLENET_CLIENT_ID` and
`GABBAPROC_BATTLENET_CLIENT_SECRET` (or their `_FILE` variants).
Until both values are configured, the provider remains hidden and unavailable.

The server requests only `openid`, reads the stable `sub` and BattleTag from
userinfo and discards provider tokens. It requests no WoW character/profile
permissions. Linking uses the existing explicit account-linking flow.
Companion pairing continues through the same browser account.

References: https://community.developer.battle.net/documentation/guides/using-oauth
and https://oauth.battle.net/.well-known/openid-configuration.

Deployment: add `deploy/compose.battlenet.yaml` after the accounts overlay only
once both credential files are present in `GABBAPROC_CONFIG_DIR`.
Local private files: `.secrets/battlenet-client-id` and
`.secrets/battlenet-client-secret` (ignored by Git, mode 0600).
