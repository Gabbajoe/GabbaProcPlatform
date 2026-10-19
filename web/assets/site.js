"use strict";
const de = {
  observatory: "COMMUNITY-BEOBACHTUNGEN",
  explore: "Daten ansehen",
  contribute: "Mitmachen",
  transparency: "Transparenz",
  era: "CLASSIC ERA / HARDCORE · OFFENE COMMUNITY-DATEN",
  hero: "Jeder Proc.<br>Ein Teil des Gesamtbilds.",
  intro:
    "Sammle Beobachtungen. Vergleiche Open World, Dungeons und Raids. Hilf mit, eine gemeinsam prüfbare Datenbasis aufzubauen.",
  join: "Eigene Beobachtungen beitragen ↗",
  disclaimer:
    "Community-Beobachtungen – keine verifizierten Kampflogs oder Beweise für unterschiedliche Proc-Chancen.",
  contributors: "Beitragende",
  collections: "Messreihen",
  effects: "Beobachtete Effekte",
  updated: "Zuletzt empfangen",
  dataset: "DIE DATENBASIS",
  compare: "Beobachtungen vergleichen",
  refresh: "Aktualisieren",
  search: "Effektname oder Zauber-ID",
  area: "Gebiet",
  all: "Alle Gebiete",
  dungeons: "Dungeons",
  raids: "Raids",
  minimum: "Mindestens Kampfminuten",
  csv: "Sichtbare Daten als CSV",
  effect: "Effekt",
  procs: "Procs gesamt",
  combat: "Kampfminuten",
  rate: "Procs / Kampfminute",
  weighted:
    "Raten = gesamte Kampf-Procs ÷ gesamte Kampfzeit. Kämpfe ohne Proc zählen mit. Zeit kann sich zwischen Effekten überschneiden; sie ist keine eindeutige Spielzeit.",
  interpretTitle: "Ein höherer Balken ist eine Beobachtung, kein Beweis.",
  interpret:
    "Angriffstempo, Ziele, Ausrüstung und Fähigkeiten beeinflussen die Raten. Diese Version zählt keine auslöseberechtigten Treffer, berechnet keine Proc-Wahrscheinlichkeit und keine Konfidenzintervalle. Extreme Raten werden zurückgehalten; plausible erfundene Zahlen sind nicht zuverlässig erkennbar.",
  joinTitle: "Dein nächster Proc kann helfen.",
  install: "Addon installieren",
  installText:
    "GabbaProcTracker erfasst deine eigenen Effekte. Die Companion-App liest nur den gespeicherten Export nach Reload oder Logout.",
  addon: "Zum Addon ↗",
  companion: "Companion verbinden",
  companionText:
    "WoW automatisch finden, Charaktere auswählen und Uploads aktivieren. App-Pakete und signierte Updates liegen auf GitHub.",
  app: "Companion herunterladen ↗",
  choice: "Du bestimmst, was du teilst",
  choiceText:
    "Ohne Namen ist die Voreinstellung. Charaktername und Realm werden nur auf Wunsch übertragen. Uploads sind optional und pausierbar.",
  details: "Genaue Datenregeln ansehen ↓",
  pilot: "Bei der ersten Datensammlung mitmachen",
  pilotText:
    "Die erste Version nutzt einmalige Einladungen vom Betreiber, um Missbrauch zu begrenzen. Gib deine Einladung ein, um einen Upload-Token zu erhalten. Den Token in die Companion-App eintragen und niemals öffentlich teilen.",
  invitation: "Einladung",
  activate: "Einladung aktivieren",
  token: "Dein Upload-Token – nur einmal angezeigt",
  copy: "Token kopieren",
  open: "OFFENER QUELLCODE. BEWUSSTE ENTSCHEIDUNGEN.",
  transparentTitle: "Wisse genau, was deinen Rechner verlässt.",
  sent: "Was übertragen wird",
  sentText:
    "Effekt-IDs, Gebietsgruppen, Zähler, Kampfzeiten, gespeicherte Kampfsegmente, Exportzeit und dauerhafte Charakter-/Messreihen-Kennungen. Name und Realm nur im Namensmodus. Keine Account-Ordnernamen, lokalen Pfade, Chats, Inventare oder vollständigen SavedVariables-Dateien.",
  anonymous: "Ohne Namen ≠ unzuordenbar",
  anonymousText:
    "Dauerhafte Kennungen machen die Daten pseudonym. IP-Adressen werden für die Verbindung und Missbrauchsbegrenzung verarbeitet. Namentliche Beiträge können einen Charakter zuordnen lassen. Das Entfernen eines Namens löscht keine bereits heruntergeladenen Kopien.",
  trust: "Wie Daten geprüft werden",
  trustText:
    "Lua wird als Datenformat gelesen, niemals ausgeführt. Der Server prüft Größen, bekannte Effekte, Zähler, Zuordnung und doppelte Exporte. Öffentliche Statistiken enthalten angenommene Community-Beiträge, keine unabhängig bestätigten Spielereignisse. Auffällige Daten werden zurückgehalten.",
  storage: "Speicherung, Löschung und Grenzen",
  storageText:
    "Gespeichert werden der neueste Gesamtstand und bis zu 301 übermittelte Segmente je Messreihe. Die öffentliche API zeigt keine Charakter-UUIDs, Geräte-Tokens oder detaillierten Zeitstempel. Mit gültigem Gerätezugang lassen sich gespeicherte Namen entfernen oder eigene Beiträge löschen und der Zugang widerrufen. Gerätewechsel: Betreiber kontaktieren. Verlaufslücken sind möglich. Auf dem Server liegen Tokens nur gehasht. Die App bevorzugt den System-Schlüsselspeicher und speichert Tokens nicht heimlich als Klartextdatei.",
  source: "Quellcode von Website & App ↗",
  feedback: "Fragen & Fehler melden ↗",
  named: "Beitragende, die ihren Namen freigegeben haben",
  legal: "Betreiber / Impressum",
};
const originals = new Map(
  [...document.querySelectorAll("[data-i]")].map((e) => [e, e.innerHTML]),
);
let language =
  localStorage.getItem("language") ||
  (navigator.language.startsWith("de") ? "de" : "en");
let dataset = { rows: [], contributors: [], meta: {} };
let visible = [];
const $ = (id) => document.getElementById(id);
const t = (en, d) => (language === "de" ? d : en);
function translate() {
  document.documentElement.lang = language;
  for (const [e, original] of originals) {
    const v = language === "de" ? de[e.dataset.i] : null;
    if (e.dataset.i === "hero") e.innerHTML = v || original;
    else
      e.textContent =
        v ||
        new DOMParser().parseFromString(original, "text/html").body.textContent;
  }
  $("language").textContent = language === "de" ? "EN" : "DE";
  render();
}
function number(n, d = 0) {
  return new Intl.NumberFormat(language, { maximumFractionDigits: d }).format(
    n,
  );
}
function render() {
  const m = dataset.meta;
  $("contributors").textContent = number(m.contributors || 0);
  $("collections").textContent = number(m.collections || 0);
  $("effects").textContent = number(
    new Set(dataset.rows.map((r) => r.spellId)).size,
  );
  $("updated").textContent = m.updated
    ? new Date(m.updated * 1000).toLocaleString(language)
    : "—";
  const q = $("search").value.toLowerCase(),
    area = $("area").value,
    min = Math.max(0, Number($("minimum").value) || 0);
  visible = dataset.rows.filter(
    (r) =>
      (r.name.toLowerCase().includes(q) || String(r.spellId).includes(q)) &&
      (area === "all" || r.group === area) &&
      r.seconds / 60 >= min,
  );
  $("rows").replaceChildren();
  const max = Math.max(1, ...visible.map((r) => r.ppm || 0));
  for (const r of visible) {
    const tr = document.createElement("tr");
    const cells = [
      r.name,
      r.group === "world"
        ? "Open World"
        : r.group === "party"
          ? "Dungeon"
          : "Raid",
      number(r.procs),
      number(r.seconds / 60, 1),
      r.ppm === null ? "—" : number(r.ppm, 3),
      number(r.contributors),
    ];
    cells.forEach((v, i) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (i === 0) {
        const small = document.createElement("small");
        small.textContent = "#" + r.spellId;
        td.append(small);
      }
      if (i === 4) {
        const bar = document.createElement("div");
        bar.className = "bar";
        bar.style.width = (130 * (r.ppm || 0)) / max + "px";
        td.append(bar);
      }
      tr.append(td);
    });
    $("rows").append(tr);
  }
  $("names").replaceChildren();
  for (const contributor of dataset.contributors) {
    const e = document.createElement("span");
    e.textContent = contributor.name + " · " + contributor.realm;
    $("names").append(e);
  }
  if (!dataset.contributors.length)
    $("names").textContent = t(
      "No named contributions yet.",
      "Noch keine namentlichen Beiträge.",
    );
  $("status").textContent = visible.length
    ? t(
        `${visible.length} observations by effect and area.`,
        `${visible.length} Beobachtungen nach Effekt und Gebiet.`,
      )
    : t(
        "No observations yet for these filters. Real contributions will appear here; no demo numbers are mixed in.",
        "Noch keine Beobachtungen für diese Filter. Hier erscheinen echte Beiträge – keine Demo-Zahlen.",
      );
}
async function refresh() {
  $("refresh").disabled = true;
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) throw Error();
    dataset = await r.json();
    render();
  } catch {
    $("status").textContent = t(
      "Could not load data. Please try again.",
      "Daten konnten nicht geladen werden. Bitte erneut versuchen.",
    );
  } finally {
    $("refresh").disabled = false;
  }
}
$("language").onclick = () => {
  language = language === "de" ? "en" : "de";
  localStorage.setItem("language", language);
  translate();
};
for (const id of ["search", "area", "minimum"])
  $(id).addEventListener("input", render);
$("refresh").onclick = refresh;
$("csv").onclick = () => {
  const quote = (v) =>
    '"' +
    String(v ?? "")
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const lines = [
    [
      "spellId",
      "effect",
      "group",
      "procs",
      "combatProcs",
      "combatSeconds",
      "procsPerMinute",
      "contributors",
    ],
    ...visible.map((r) => [
      r.spellId,
      r.name,
      r.group,
      r.procs,
      r.combatProcs,
      r.seconds,
      r.ppm,
      r.contributors,
    ]),
  ];
  const url = URL.createObjectURL(
    new Blob([lines.map((row) => row.map(quote).join(";")).join("\r\n")], {
      type: "text/csv;charset=utf-8",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "gabbaproc-observations.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("enroll").onsubmit = async (e) => {
  e.preventDefault();
  const button = e.submitter;
  button.disabled = true;
  try {
    const r = await fetch("/api/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite: $("invite").value }),
    });
    if (!r.ok) throw Error();
    const data = await r.json();
    $("token").value = data.token;
    $("token-box").hidden = false;
    $("invite").value = "";
    $("enroll-status").textContent = t(
      "Token created. Store it in the companion now.",
      "Token erstellt. Jetzt in der Companion-App speichern.",
    );
  } catch {
    $("enroll-status").textContent = t(
      "Invitation invalid, expired or temporarily rate-limited.",
      "Einladung ungültig, abgelaufen oder vorübergehend zu viele Versuche.",
    );
  } finally {
    button.disabled = false;
  }
};
$("copy-token").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("token").value);
    $("enroll-status").textContent = t(
      "Copied. Keep this token private.",
      "Kopiert. Diesen Token vertraulich behandeln.",
    );
  } catch {
    $("token").select();
  }
};
translate();
refresh();
