"use strict";
const { invoke } = window.__TAURI__.core;
const $ = (id) => document.getElementById(id);
const de = {
  tabcharacters: "Charaktere",
  tabsync: "Sync",
  tabaccount: "Account",
  tabsettings: "Einstellungen",
  settings: "Einstellungen",
  tag: "Kleine App. Gemeinsame Erkenntnisse.",
  connect: "Account",
  pairHelp:
    "Melde dich im Browser an und bestätige den hier angezeigten Gerätecode. Dein bestehender Upload-Zugang bleibt erhalten.",
  pairStart: "Mit Konto verbinden",
  connected: "Verbunden",
  disconnect: "Trennen",
  connectionSettings: "Verbindung einrichten",
  manualAccess: "Upload-Token manuell verwenden",
  pairCancel: "Verbindung abbrechen",
  tokenHelp:
    "Alternativ einen bestehenden Upload-Token einfügen oder auf der Website erstellen. Er wird im System-Schlüsselbund gespeichert, andernfalls nur für diese Sitzung.",
  token: "Upload-Token",
  save: "Token speichern",
  characters: "Charaktere auswählen",
  help: "Im Addon exportieren (/gpt export), danach /reload oder ausloggen. Nur ausgewählte Charaktere werden hochgeladen. Anonyme Uploads nutzen eine dauerhafte pseudonyme ID.",
  scan: "WoW suchen",
  folder: "WoW-Ordner auswählen",
  sync: "Synchronisieren",
  auto: "Auto-Upload",
  interval: "Intervall",
  bandwidth: "Bandbreite",
  unlimited: "Unbegrenzt",
  localBuild:
    "Lokale Testversion: Uploads gehen nur an den lokalen Testserver.",
  quit: "App beenden",
  languageLabel: "Sprache",
  systemLanguage: "Systemsprache",
  closeToTray: "Beim Schließen in den Infobereich minimieren",
  startup: "Bei der Anmeldung starten",
  updates: "Signierte App-Updates automatisch installieren (App startet neu)",
  running:
    "Wenn aktiviert, wird das Fenster beim Schließen im Infobereich ausgeblendet. Ohne verfügbaren Infobereich beendet das Schließen die App.",
  upload: "Ausgewählte Charaktere hochladen",
  update: "Nach Updates suchen",
  preview: "Upload-Vorschau",
  deleteTitle: "Meine gespendeten Daten löschen",
  deleteHelp:
    "Löscht alle Daten dieses Upload-Tokens und sperrt ihn. Danach brauchst du eine neue Einladung.",
  delete: "Daten endgültig löschen",
  source: "Quellcode & Releases: github.com/Gabbajoe/GabbaProcPlatform",
};
const original = new Map(
  [...document.querySelectorAll("[data-t]")].map((el) => [el, el.textContent]),
);
let languageChoice = localStorage.getItem("languageChoice") || "auto";
function resolvedLanguage() {
  return ["de", "en"].includes(languageChoice) ? languageChoice : (navigator.languages?.[0] || navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}
let lang = resolvedLanguage();
function text(en, ger) {
  return lang === "de" ? ger : en;
}
function language() {
  document.documentElement.lang = lang;
  $("lang").value = languageChoice;
  for (const [el, en] of original)
    el.textContent = lang === "de" ? de[el.dataset.t] || en : en;
  localStorage.setItem("languageChoice", languageChoice);
  run(() => invoke("set_language", { language: lang }));
}
function status(v) {
  if (typeof v === "string" && v.startsWith("{")) {
    try {
      v = JSON.parse(v);
    } catch (_) {}
  }
  if (v && typeof v === "object" && "pendingPackets" in v) {
    $("status").textContent =
      text(
        `${v.uploaded} character archives confirmed. ${v.pendingPackets} packets pending.`,
        `${v.uploaded} Charakterarchive bestätigt. ${v.pendingPackets} Pakete ausstehend.`,
      ) + (v.errors?.length ? "\n" + v.errors.join("\n") : "");
  } else {
    $("status").textContent =
      typeof v === "string" ? v : JSON.stringify(v, null, 2);
  }
}

async function run(f) {
  try {
    return await f();
  } catch (e) {
    status(String(e));
  }
}
let progressSignature = "";
const characterLabels = new Map();
function renderProgress(s) {
  const entries = Object.entries(s.progress || {});
  const signature = JSON.stringify([
    lang,
    s.progress,
    s.busy,
    s.autoUpload,
    s.finishingUpload,
    [...characterLabels],
  ]);
  const container = $("uploadProgress");
  container.hidden = entries.length === 0;
  if (signature !== progressSignature) {
    progressSignature = signature;
    container.replaceChildren();
    for (const [id, p] of entries) {
      const paused =
        !s.busy &&
        !s.autoUpload &&
        !s.finishingUpload &&
        ["ready", "waiting", "retry", "sending", "checking"].includes(p.phase);
      const phase = paused ? "paused" : p.phase;
      const labels = {
        preparing: text("Preparing archive…", "Archiv wird vorbereitet …"),
        ready: text("Next packet is ready", "Nächstes Paket ist bereit"),
        sending: text(
          `Sending packet ${p.confirmed + 1} of ${p.total}…`,
          `Paket ${p.confirmed + 1} von ${p.total} wird gesendet …`,
        ),
        checking: text(
          "Checking server confirmation…",
          "Serverbestätigung wird geprüft …",
        ),
        waiting: text(
          "Received by server · waiting for processing confirmation",
          "Beim Server eingegangen · warte auf Verarbeitungsbestätigung",
        ),
        retry: text(
          "Connection delayed · data stays saved locally",
          "Übertragung verzögert · Daten bleiben lokal gespeichert",
        ),
        blocked: text(
          "Server could not process this upload · data retained",
          "Server konnte den Upload nicht verarbeiten · Daten bleiben gespeichert",
        ),
        error: text(
          "Upload interrupted · see details below",
          "Upload unterbrochen · Details stehen unten",
        ),
        complete: text(
          "Upload complete · confirmed by server",
          "Upload abgeschlossen · vom Server bestätigt",
        ),
        unchanged: text(
          "Already synchronized · no new data",
          "Bereits synchronisiert · keine neuen Daten",
        ),
        paused: text(
          "Upload paused · click Upload to resume",
          "Upload pausiert · mit Upload fortsetzen",
        ),
      };
      const row = document.createElement("div");
      row.className = "upload-progress-row";
      row.dataset.phase = phase;
      const heading = document.createElement("strong");
      heading.textContent =
        characterLabels.get(id) ||
        text(`Character ${id.slice(0, 8)}`, `Charakter ${id.slice(0, 8)}`);
      const label = document.createElement("p");
      label.className = "progress-phase";
      label.setAttribute("role", "status");
      label.textContent = labels[phase] || phase;
      row.append(heading);
      if (typeof p.named === "boolean") {
        const privacy = document.createElement("span");
        privacy.className = "progress-privacy";
        privacy.textContent = p.named
          ? text("With character name and realm", "Mit Charaktername und Realm")
          : text("Anonymous", "Anonym");
        row.append(privacy);
      }
      row.append(label);
      if (p.total > 0) {
        const stages = [
          [
            "upload",
            text("Uploaded to server", "Zum Server hochgeladen"),
            p.received ?? p.confirmed,
          ],
          [
            "processing",
            text("Processed by server", "Vom Server verarbeitet"),
            p.confirmed,
          ],
        ];
        for (const [stage, title, value] of stages) {
          const completed = Math.max(0, Math.min(value, p.total));
          const count = document.createElement("p");
          count.className = "progress-count";
          count.textContent = `${title}: ${completed} / ${p.total} · ${Math.floor((100 * completed) / p.total)}%`;
          const bar = document.createElement("progress");
          bar.dataset.stage = stage;
          bar.max = p.total;
          bar.value = completed;
          bar.setAttribute("aria-label", title);
          const track = document.createElement("div");
          track.className = "progress-track";
          track.dataset.active = String(
            completed < p.total &&
              (stage === "upload"
                ? phase === "sending"
                : ["waiting", "checking"].includes(phase)),
          );
          track.append(bar);
          row.append(count, track);
        }
      } else if (phase === "preparing") {
        const bar = document.createElement("progress");
        bar.setAttribute("aria-label", labels.preparing);
        row.append(bar);
      }
      if (["waiting", "retry", "ready"].includes(phase) && p.nextCheck) {
        const countdown = document.createElement("small");
        countdown.className = "progress-countdown";
        countdown.dataset.deadline = p.nextCheck;
        countdown.setAttribute("aria-live", "off");
        row.append(countdown);
      }
      container.append(row);
    }
  }
  for (const el of container.querySelectorAll("[data-deadline]")) {
    const seconds = Math.max(
      0,
      Math.ceil(Number(el.dataset.deadline) - Date.now() / 1000),
    );
    el.textContent =
      seconds > 0
        ? text(
            `Next check in about ${seconds}s`,
            `Nächste Prüfung in etwa ${seconds} s`,
          )
        : text("Next check shortly…", "Nächste Prüfung folgt gleich …");
  }
}
let lastLinkedState;
let nextAccountCheck = 0;
let accountCheckRunning = false;
function renderCredential(s) {
  const linked = !!(s.accountLinked && s.hasToken);
  $("accountConnected").hidden = !linked;
  $("accountSetup").hidden = linked;
  $("manualAccess").hidden = linked;
  $("accountName").textContent =
    s.accountUsername || text("GabbaProc account", "GabbaProc-Konto");
  $("accountExpiry").textContent = s.accountExpiresAt
    ? text("Access valid until ", "Zugang gültig bis ") +
      new Date(s.accountExpiresAt * 1000).toLocaleString()
    : text(
        "No automatic expiry. Valid until disconnected or revoked.",
        "Kein automatischer Ablauf. Gültig bis zum Trennen oder Widerrufen.",
      );
  $("accountStorage").textContent = s.persistentToken
    ? text(
        "Access saved in your system keyring.",
        "Zugang im System-Schlüsselbund gespeichert.",
      )
    : text(
        "Session only: reconnect after quitting the app.",
        "Nur diese Sitzung: Nach dem Beenden erneut verbinden.",
      );
  $("disconnectAccount").disabled = !!s.busy;
  if (lastLinkedState !== linked) {
    lastLinkedState = linked;
    $("accountSetup").open = !linked;
    $("manualAccess").open = false;
  }
  if (
    s.hasToken &&
    !s.keyringLoading &&
    !accountCheckRunning &&
    Date.now() >= nextAccountCheck
  ) {
    nextAccountCheck = Date.now() + 60000;
    accountCheckRunning = true;
    invoke("refresh_account")
      .catch(() => {})
      .then(() => invoke("overview"))
      .then(renderCredential)
      .catch(() => {})
      .finally(() => {
        accountCheckRunning = false;
      });
  }
  $("connection").textContent = s.keyringLoading
    ? text("Loading access…", "Zugang wird geladen …")
    : s.hasToken
      ? linked
        ? (s.accountUsername ? s.accountUsername + " · " : "") +
          text("Connected", "Verbunden")
        : text("Upload access ready", "Upload-Zugang bereit")
      : text("No upload access", "Kein Upload-Zugang");
  $("connection").dataset.ready = String(!!s.hasToken);

  $("credential").textContent = s.keyringLoading
    ? text("Loading saved token…", "Gespeicherter Token wird geladen …")
    : s.hasToken
      ? s.persistentToken
        ? text("Saved in keyring", "Im Schlüsselbund gespeichert")
        : text("Session only", "Nur diese Sitzung")
      : text("No token", "Kein Token");
}
async function overview() {
  const s = await invoke("overview");
  renderProgress(s);
  if (s.version) $("appVersion").textContent = s.version;
  if (s.localBuild) {
    $("localBuild").hidden = false;
    $("update").disabled = true;
    $("updates").disabled = true;
    document.querySelector('[data-t="tokenHelp"]').textContent = text(
      "Use a token from the local test server. Production upload tokens do not work here.",
      "Verwende einen Token des lokalen Testservers. Upload-Tokens der öffentlichen Webseite funktionieren hier nicht.",
    );
  }
  $("auto").checked = s.autoUpload;
  $("closeToTray").checked = s.closeToTray !== false;
  $("interval").value = String(s.uploadIntervalMinutes || 15);
  $("bandwidth").value = String(s.uploadBandwidthKib || 0);
  renderCredential(s);
  return s;
}
let scanGeneration = 0;
async function scan() {
  const generation = ++scanGeneration;
  if (!$("characters").children.length)
    $("characters").textContent = text(
      "Finding characters…",
      "Charaktere werden gesucht …",
    );
  const rows = await invoke("discover");
  if (generation !== scanGeneration) return;
  for (const row of rows) {
    if (row.id && !row.error) {
      const label = [row.localName, row.realm].filter(Boolean).join(" · ");
      if (label) characterLabels.set(row.id, label);
    }
  }
  $("characters").replaceChildren();
  const groups = new Map();
  for (const row of rows) {
    const installation = row.installationPath || "";
    if (!groups.has(installation)) {
      const group = document.createElement("div");
      group.className = "installation";
      const heading = document.createElement("h3");
      heading.textContent = row.client || "Classic Era / Hardcore";
      const path = document.createElement("p");
      path.className = "source-path";
      path.textContent = installation;
      group.append(heading, path);
      $("characters").append(group);
      groups.set(installation, group);
    }
    const group = groups.get(installation);
    const box = document.createElement("div");
    box.className = "character";
    const title = document.createElement("strong");
    title.textContent = [row.localName, row.realm].filter(Boolean).join(" · ");
    const source = document.createElement("details");
    source.className = "source";
    const summary = document.createElement("summary");
    summary.textContent = text("Local file path", "Lokaler Dateipfad");
    const path = document.createElement("p");
    path.className = "source-path";
    path.textContent = row.sourcePath || "";
    source.append(summary, path);
    box.append(title, source);
    if (row.error) {
      const errors = {
        missing_snapshot: text(
          "No export snapshot yet. In this character's WoW session, use /gpt export, then /reload or log out.",
          "Noch kein Export-Snapshot. Mit diesem Charakter in WoW /gpt export und danach /reload ausführen oder ausloggen.",
        ),
        invalid_export: text(
          "Export incomplete or unsupported. Update the addon, export again and /reload.",
          "Export unvollständig oder nicht unterstützt. Addon aktualisieren, erneut exportieren und /reload ausführen.",
        ),
        unreadable_export: text(
          "File cannot be read or parsed. Export again in WoW and /reload.",
          "Datei nicht lesbar oder fehlerhaft. In WoW erneut exportieren und /reload ausführen.",
        ),
        duplicate: text(
          "Duplicate character ID. The first listed export for this character is used.",
          "Doppelte Charakter-ID. Der zuerst aufgeführte Export dieses Charakters wird verwendet.",
        ),
      };
      const error = document.createElement("p");
      error.textContent =
        errors[row.error] || text("Invalid export.", "Ungültiger Export.");
      box.append(error);
      group.append(box);
      continue;
    }
    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = row.choice.enabled;
    const named = document.createElement("input");
    named.type = "checkbox";
    named.checked = row.choice.named;
    const label = document.createElement("label");
    label.append(
      enabled,
      document.createTextNode(
        `${row.localName} · ${row.id.slice(0, 8)} · ${row.rows} ${text("measurements", "Messwerte")}`,
      ),
    );
    const label2 = document.createElement("label");
    label2.append(
      named,
      document.createTextNode(
        text(
          "Publish character name and realm",
          "Charaktername und Realm veröffentlichen",
        ),
      ),
    );
    let savedChoice = { enabled: enabled.checked, named: named.checked };
    async function choose() {
      enabled.disabled = named.disabled = true;
      try {
        await invoke("set_choice", { id: row.id, enabled: enabled.checked, named: named.checked });
        savedChoice = { enabled: enabled.checked, named: named.checked };
      } catch (error) {
        enabled.checked = savedChoice.enabled;
        named.checked = savedChoice.named;
        throw error;
      } finally {
        enabled.disabled = named.disabled = false;
      }
    }
    enabled.onchange = named.onchange = () => run(choose);
    const preview = document.createElement("button");
    preview.textContent = text("Preview", "Vorschau");
    const previewPanel = document.createElement("details");
    previewPanel.className = "character-preview";
    previewPanel.hidden = true;
    const previewTitle = document.createElement("summary");
    previewTitle.textContent = text("Upload preview", "Upload-Vorschau");
    const previewData = document.createElement("pre");
    previewPanel.append(previewTitle, previewData);
    preview.onclick = () =>
      run(async () => {
        previewData.textContent = JSON.stringify(await invoke("preview", { id: row.id }), null, 2);
        $("preview").textContent = previewData.textContent;
        previewPanel.hidden = false;
        previewPanel.open = true;
      });
    const hide = document.createElement("button");
    hide.textContent = text(
      "Hide previously published name",
      "Bisher veröffentlichten Namen ausblenden",
    );
    hide.onclick = () =>
      run(async () => {
        await invoke("hide_name", { id: row.id });
        await scan();
        status(
          text(
            "Name hidden; character uploads paused.",
            "Name ausgeblendet; Uploads dieses Charakters pausiert.",
          ),
        );
      });
    box.append(label, label2, preview, hide, previewPanel);
    group.append(box);
  }
  if (!rows.length)
    $("characters").textContent = text(
      "No exports found. Choose your WoW folder and export in the addon.",
      "Keine Exporte gefunden. WoW-Ordner wählen und im Addon exportieren.",
    );
}
function showTab(key) {
  for (const button of document.querySelectorAll("[data-tab]")) {
    const selected = button.dataset.tab === key;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(button.getAttribute("aria-controls")).hidden = !selected;
  }
  document.querySelector("main").scrollTop = 0;
}
const tabs = [...document.querySelectorAll("[data-tab]")];
for (const [index, button] of tabs.entries()) {
  button.onclick = () => showTab(button.dataset.tab);
  button.onkeydown = (event) => {
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : event.key === "ArrowLeft"
          ? (index + tabs.length - 1) % tabs.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? tabs.length - 1
              : -1;
    if (next < 0) return;
    event.preventDefault();
    showTab(tabs[next].dataset.tab);
    tabs[next].focus();
  };
}
$("lang").onchange = () => {
  languageChoice = $("lang").value;
  lang = resolvedLanguage();
  language();
  run(async () => {
    await overview();
    await scan();
  });
};
$("scan").onclick = () => run(scan);
$("folder").onclick = () =>
  run(async () => {
    const path = await window.__TAURI__.dialog.open({
      directory: true,
      multiple: false,
    });
    if (path) {
      await invoke("add_root", { path });
      await scan();
    }
  });
$("saveToken").onclick = () =>
  run(async () => {
    await invoke("set_token", { token: $("token").value.trim() });
    $("token").value = "";
    await overview();
  });
$("auto").onchange = () =>
  run(() => invoke("set_auto", { enabled: $("auto").checked }));
$("bandwidth").onchange = () =>
  run(() => invoke("set_bandwidth", { kib: Number($("bandwidth").value) }));
$("interval").onchange = () =>
  run(() => invoke("set_interval", { minutes: Number($("interval").value) }));
$("quit").onclick = () => run(() => invoke("quit_app"));
$("startup").onchange = () =>
  run(async () => {
    if ($("startup").checked) await window.__TAURI__.autostart.enable();
    else await window.__TAURI__.autostart.disable();
  });
$("upload").onclick = () =>
  run(async () => {
    const s = await overview();
    if (s.busy) return;
    status(text("Uploading…", "Upload läuft…"));
    status(await invoke("sync_now"));
    await overview();
  });
$("delete").onclick = () =>
  run(async () => {
    if (
      !confirm(
        text(
          "Permanently delete all your contributed data and revoke this token?",
          "Alle deine hochgeladenen Daten endgültig löschen und diesen Token sperren?",
        ),
      )
    )
      return;
    await invoke("delete_data");
    await overview();
    await scan();
    status(text("Deleted. Token revoked.", "Gelöscht. Token gesperrt."));
  });
let updating = false;
async function update(manual) {
  if (updating) return;
  updating = true;
  try {
    const s = await overview();
    if (s.busy || s.localBuild) return;
    const u = await window.__TAURI__.updater.check();
    if (!u) {
      if (manual) status(text("App is up to date.", "App ist aktuell."));
      return;
    }
    if (!manual && !$("updates").checked) return;
    if (
      manual &&
      !confirm(
        text(
          `Install signed update ${u.version} and restart?`,
          `Signiertes Update ${u.version} installieren und neu starten?`,
        ),
      )
    )
      return;
    status(
      text("Installing signed update…", "Signiertes Update wird installiert…"),
    );
    await u.downloadAndInstall();
    await invoke("restart_after_update", { version: u.version });
  } finally {
    updating = false;
  }
}
$("updates").checked = localStorage.getItem("autoUpdates") === "true";
$("updates").onchange = () => {
  localStorage.setItem("autoUpdates", String($("updates").checked));
  if ($("updates").checked) run(() => update(false));
};
$("update").onclick = () => run(() => update(true));
for (let minutes = 5; minutes <= 60; minutes += 5) {
  const option = document.createElement("option");
  option.value = String(minutes);
  option.textContent = `${minutes} min`;
  $("interval").append(option);
}
language();
run(async () => {
  await overview();
  await scan();
  $("startup").checked = await window.__TAURI__.autostart.isEnabled();
  if ($("startup").checked) await window.__TAURI__.autostart.enable();
  if ($("updates").checked) await update(false);
});
setInterval(
  () =>
    run(async () => {
      const s = await invoke("overview");
      renderProgress(s);
      renderCredential(s);
      if (s.status && !s.busy) status(s.status);
    }),
  1000,
);
setInterval(
  () => {
    if ($("updates").checked) run(() => update(false));
  },
  6 * 60 * 60 * 1000,
);

let pairingGeneration = 0;
$("pairStart").onclick = async () => {
  const generation = ++pairingGeneration;
  $("pairStart").disabled = true;
  $("pairStatus").textContent = text(
    "Opening account connection…",
    "Kontoverbindung wird geöffnet …",
  );
  try {
    const pair = await invoke("start_pairing");
    $("pairCancel").hidden = false;
    const message = text(
      `Device code: ${pair.userCode}. Sign in at ${pair.url} and approve this code.`,
      `Gerätecode: ${pair.userCode}. Auf ${pair.url} anmelden und diesen Code bestätigen.`,
    );
    $("pairStatus").textContent = message;
    const deadline = Date.now() + 600000;
    while (generation === pairingGeneration && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 5500));
      if (generation !== pairingGeneration) break;
      const result = await invoke("poll_pairing");
      if (result.status === "linked") {
        $("pairStatus").textContent = text(
          "Account connected. Upload selection remains unchanged.",
          "Konto verbunden. Deine Upload-Auswahl bleibt erhalten.",
        );
        nextAccountCheck = 0;
        await overview();
        return;
      }
    }
    if (generation === pairingGeneration)
      $("pairStatus").textContent = text(
        "Connection expired. Please start again.",
        "Verbindung abgelaufen. Bitte erneut starten.",
      );
  } catch (_) {
    if (generation === pairingGeneration)
      $("pairStatus").textContent = text(
        "Connection failed. Check your access and try again.",
        "Verbindung fehlgeschlagen. Bitte Zugang prüfen und erneut versuchen.",
      );
  } finally {
    if (generation === pairingGeneration) {
      $("pairStart").disabled = false;
      $("pairCancel").hidden = true;
      await invoke("cancel_pairing");
    }
  }
};
$("pairCancel").onclick = async () => {
  pairingGeneration++;
  await invoke("cancel_pairing");
  $("pairCancel").hidden = true;
  $("pairStart").disabled = false;
  $("pairStatus").textContent = text(
    "Connection cancelled.",
    "Verbindung abgebrochen.",
  );
};

$("disconnectAccount").onclick = () =>
  run(async () => {
    if (
      !confirm(
        text(
          "Disconnect this app and stop uploads? Your uploaded data stays in your account.",
          "Diese App trennen und Uploads stoppen? Hochgeladene Daten bleiben in deinem Konto.",
        ),
      )
    )
      return;
    await invoke("disconnect_account");
    nextAccountCheck = 0;
    $("pairStatus").textContent = text(
      "Disconnected. Connect again to resume.",
      "Getrennt. Zum Fortsetzen erneut verbinden.",
    );
    await overview();
  });

$("closeToTray").onchange = () => run(() => invoke("set_close_to_tray", { enabled: $("closeToTray").checked }));
for (const [id, destination] of [["sourceLink", "source"], ["websiteLink", "website"]]) {
  $(id).onclick = (event) => { event.preventDefault(); run(() => invoke("open_public_link", { destination })); };
}
