"use strict";
const $ = (id) => document.getElementById(id);
let savedLanguage;
try {
  savedLanguage = localStorage.getItem("language");
} catch (_) {}
let language = ["de", "en"].includes(savedLanguage)
  ? savedLanguage
  : navigator.language.startsWith("de")
    ? "de"
    : "en";
let dataset = null,
  visible = [],
  loadError = false;
const t = (en, de) => (language === "de" ? de : en);
const effectName = (row) => row.names?.[language] || row.name;
const number = (n, digits = 0) =>
  new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(n);
const areaName = (a) =>
  ({ world: "Open World", party: t("Dungeon", "Dungeon"), raid: "Raid" })[a] ||
  a;
const params = new URLSearchParams(location.search);
if ($("search")) $("search").value = params.get("q") || "";
if ($("area") && ["all", "world", "party", "raid"].includes(params.get("area")))
  $("area").value = params.get("area");
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function translate() {
  document.documentElement.lang = language;
  for (const e of document.querySelectorAll("[data-en][data-de]"))
    e.textContent = e.dataset[language];
  for (const button of $("language").querySelectorAll("[data-language]"))
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.language === language),
    );
  document.querySelector(".skip").textContent = t(
    "Skip to content",
    "Zum Inhalt",
  );
  render();
}
function status(message) {
  if ($("status")) $("status").textContent = message;
}
function render() {
  if (!dataset) {
    status(
      loadError
        ? t(
            "Data unavailable. Please try again.",
            "Daten nicht verfügbar. Bitte erneut versuchen.",
          )
        : t("Loading measurements…", "Messwerte werden geladen…"),
    );
    return;
  }
  const rows = dataset.rows;
  if ($("contributors")) {
    $("contributors").textContent = number(dataset.meta.contributors || 0);
    $("collections").textContent = number(dataset.meta.collections || 0);
    $("effects").textContent = number(new Set(rows.map((r) => r.spellId)).size);
    $("updated").textContent = dataset.meta.updated
      ? new Date(dataset.meta.updated * 1000).toLocaleString(language)
      : "—";
  }
  if ($("rows")) {
    const q = $("search").value.toLocaleLowerCase(),
      area = $("area").value;
    const minimum = Math.max(0, Number($("minimum").value) || 0);
    visible = rows.filter(
      (r) =>
        (effectName(r).toLocaleLowerCase().includes(q) ||
          String(r.spellId).includes(q)) &&
        (area === "all" || r.group === area) &&
        r.seconds / 60 >= minimum,
    );
    const sort = $("sort").value;
    visible.sort((a, b) =>
      sort === "name"
        ? effectName(a).localeCompare(effectName(b), language) ||
          a.group.localeCompare(b.group)
        : (b[sort] ?? -1) - (a[sort] ?? -1) || a.spellId - b.spellId,
    );
    $("rows").replaceChildren();
    for (const r of visible) {
      const tr = element("tr"),
        title = element("td"),
        link = element("a", effectName(r));
      link.href = "/compare.html?effect=" + encodeURIComponent(r.spellId);
      title.append(link, element("small", "#" + r.spellId));
      tr.append(title);
      for (const value of [
        areaName(r.group),
        number(r.procs),
        number(r.seconds / 60, 1),
        r.ppm === null ? "—" : number(r.ppm, 3),
        number(r.contributors),
      ])
        tr.append(element("td", value));
      $("rows").append(tr);
    }
    if (!visible.length) {
      const row = element("tr"),
        cell = element(
          "td",
          t(
            "No measurements for these filters.",
            "Keine Messwerte für diese Filter.",
          ),
          "empty-cell",
        );
      cell.colSpan = 6;
      row.append(cell);
      $("rows").append(row);
    }
    status(
      loadError
        ? t(
            "Refresh failed; showing previously loaded data.",
            "Aktualisierung fehlgeschlagen; zuletzt geladene Daten werden angezeigt.",
          )
        : t(
            `${visible.length} effect / area combinations`,
            `${visible.length} Kombinationen aus Effekt und Gebiet`,
          ),
    );
    $("csv").disabled = !visible.length;
    $("names").replaceChildren();
    for (const contributor of dataset.contributors)
      $("names").append(
        element("span", contributor.name + " · " + contributor.realm),
      );
    if (!dataset.contributors.length)
      $("names").textContent = t(
        "No public character names yet.",
        "Noch keine öffentlichen Charakternamen.",
      );
  }
  if ($("effect-select")) renderComparison();
}
function renderComparison() {
  const select = $("effect-select"),
    selected = select.value === "—" ? params.get("effect") : select.value;
  const effects = [
    ...new Map(
      dataset.rows.map((r) => [String(r.spellId), effectName(r)]),
    ).entries(),
  ].sort((a, b) => a[1].localeCompare(b[1], language));
  select.replaceChildren();
  for (const [id, name] of effects) {
    const o = element("option", name + " · #" + id);
    o.value = id;
    select.append(o);
  }
  if (effects.some(([id]) => id === selected)) select.value = selected;
  $("comparison").replaceChildren();
  if (!effects.length) {
    status(t("No observed effects yet.", "Noch keine Effekte erfasst."));
    return;
  }
  const data = dataset.rows.filter((r) => String(r.spellId) === select.value),
    maximum = Math.max(1, ...data.map((r) => r.ppm || 0));
  for (const area of ["world", "party", "raid"]) {
    const r = data.find((r) => r.group === area),
      card = element("section", undefined, "area-card");
    card.append(
      element("h2", areaName(area)),
      element("div", r?.ppm != null ? number(r.ppm, 3) : "—", "big"),
      element("p", t("procs / combat minute", "Procs / Kampfminute")),
    );
    const bar = element("progress");
    bar.max = maximum;
    bar.value = r?.ppm || 0;
    bar.setAttribute("aria-label", areaName(area));
    card.append(bar);
    const dl = element("dl");
    for (const [label, value] of [
      [t("Combat procs", "Kampf-Procs"), r ? number(r.combatProcs) : "—"],
      [
        t("Combat minutes", "Kampfminuten"),
        r ? number(r.seconds / 60, 1) : "—",
      ],
      [t("Contributors", "Beitragende"), r ? number(r.contributors) : "—"],
    ]) {
      const pair = element("div");
      pair.append(element("dt", label), element("dd", value));
      dl.append(pair);
    }
    card.append(dl);
    if (!r)
      card.append(
        element(
          "p",
          t(
            "No measurements in this area.",
            "Keine Messwerte in diesem Gebiet.",
          ),
        ),
      );
    $("comparison").append(card);
  }
  status(
    loadError
      ? t(
          "Refresh failed; previous data shown.",
          "Aktualisierung fehlgeschlagen; bisherige Daten angezeigt.",
        )
      : t(
          "Observed rates; not a proc chance per hit.",
          "Beobachtete Raten; keine Proc-Chance pro Treffer.",
        ),
  );
}
async function refresh() {
  $("refresh").disabled = true;
  try {
    const response = await fetch("/api/stats");
    if (!response.ok) throw Error();
    const data = await response.json();
    if (
      !Array.isArray(data.rows) ||
      !Array.isArray(data.contributors) ||
      !data.meta
    )
      throw Error();
    dataset = data;
    loadError = false;
  } catch {
    loadError = true;
  } finally {
    $("refresh").disabled = false;
    render();
  }
}
$("language").onclick = (event) => {
  const button = event.target.closest("button[data-language]");
  if (!button || !$("language").contains(button)) return;
  language = button.dataset.language;
  try {
    localStorage.setItem("language", language);
  } catch (_) {}
  translate();
};
for (const id of ["search", "area", "minimum", "sort"])
  if ($(id))
    $(id).addEventListener("input", () => {
      render();
      const q = new URLSearchParams();
      if ($("search").value) q.set("q", $("search").value);
      if ($("area").value !== "all") q.set("area", $("area").value);
      history.replaceState(
        null,
        "",
        location.pathname + (q.size ? "?" + q : ""),
      );
    });
if ($("effect-select"))
  $("effect-select").onchange = () => {
    renderComparison();
    history.replaceState(
      null,
      "",
      "?effect=" + encodeURIComponent($("effect-select").value),
    );
  };
if ($("refresh")) $("refresh").onclick = refresh;
if ($("csv"))
  $("csv").onclick = () => {
    const quote = (v) =>
      '"' +
      String(v ?? "")
        .replace(/^\s*[=+@-]/, "'$&")
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
        effectName(r),
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
    const a = element("a");
    a.href = url;
    a.download = "gabbaproc-observations.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
if ($("enroll"))
  $("enroll").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      const response = await fetch("/api/enroll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite: $("invite").value }),
      });
      if (!response.ok) throw Error();
      const data = await response.json();
      $("token").value = data.token;
      $("token-box").hidden = false;
      $("invite").value = "";
      $("enroll-status").textContent = t(
        "Token created. Store it in the companion.",
        "Token erstellt. In der Companion-App speichern.",
      );
    } catch {
      $("enroll-status").textContent = t(
        "Invitation unavailable or expired. Please try again later.",
        "Einladung nicht verfügbar oder abgelaufen. Bitte später erneut versuchen.",
      );
    } finally {
      button.disabled = false;
    }
  };
if ($("copy-token"))
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
if ($("refresh")) refresh();

// Account display is private browser state, never part of the public dataset.
let headerAccount = null;
const accountLink = document.createElement("a");
accountLink.id = "header-account";
accountLink.href = "/account.html";
$("language").before(accountLink);
function renderHeaderAccount() {
  accountLink.textContent =
    headerAccount?.username ||
    (headerAccount ? t("My account", "Mein Konto") : t("Sign in", "Anmelden"));
  accountLink.classList.toggle("signed-in", !!headerAccount);
}
window.addEventListener("gabbaproc-account", (event) => {
  headerAccount = event.detail;
  window.gabbaprocAccount = headerAccount;
  window.gabbaprocAccountReady = true;
  renderHeaderAccount();
});
new MutationObserver(renderHeaderAccount).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ["lang"],
});
renderHeaderAccount();
if (!$("account-login"))
  fetch("/api/account")
    .then((r) => (r.ok ? r.json() : null))
    .then((account) => {
      window.dispatchEvent(new CustomEvent("gabbaproc-account", { detail: account }));
    })
    .catch(() => {});
