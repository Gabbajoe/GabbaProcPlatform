"use strict";
(() => {
  let account = null,
    available = [];
  const signup = new URLSearchParams(location.search).get("mode") === "signup";
  const el = (id) => document.getElementById(id);
  const tr = (en, de) => (document.documentElement.lang === "de" ? de : en);
  const status = (en, de) => {
    el("account-status").textContent = tr(en, de);
  };
  document.title = "GabbaProc · " + (signup ? tr("Create account", "Konto erstellen") : tr("Sign in", "Anmelden"));
  const pairingKey = "gabbaproc.pendingPairing";
  let pairingShown = false;
  function pendingPairing() {
    try {
      const pending = JSON.parse(localStorage.getItem(pairingKey));
      if (
        pending &&
        /^[A-F0-9]{10}$/.test(pending.code) &&
        pending.expires > Date.now() &&
        pending.expires <= Date.now() + 600000
      )
        return pending;
      localStorage.removeItem(pairingKey);
    } catch (_) {
      /* Manual code entry remains available if storage is blocked. */
    }
    return null;
  }
  const emailLink = new URLSearchParams(location.hash.slice(1));
  if (emailLink.has("deviceCode")) {
    const code = (emailLink.get("deviceCode") || "").toUpperCase();
    if (/^[A-F0-9]{10}$/.test(code)) {
      try {
        localStorage.setItem(
          pairingKey,
          JSON.stringify({ code, expires: Date.now() + 600000 }),
        );
      } catch (_) {}
      el("pair-code").value = code;
    }
    history.replaceState(null, "", location.pathname + location.search);
  }
  async function request(path, method = "GET", body, headers = {}) {
    const r = await fetch("/api" + path, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    if (!r.ok) {
      const error = new Error(
        r.status === 429 ? "rate" : r.status === 401 ? "session" : "request",
      );
      error.status = r.status;
      throw error;
    }
    return r.json();
  }
  async function action(button, fn) {
    button.disabled = true;
    try {
      await fn();
    } catch (e) {
      if (e.message === "rate")
        status(
          "Too many attempts. Please try again later.",
          "Zu viele Versuche. Bitte später erneut versuchen.",
        );
      else if (e.message === "session")
        status("Please sign in again.", "Bitte erneut anmelden.");
      else
        status(
          "Could not complete this action. Check your entry and try again.",
          "Aktion fehlgeschlagen. Bitte Eingabe prüfen und erneut versuchen.",
        );
    } finally {
      button.disabled = false;
    }
  }
  function render() {
    document.title = "GabbaProc · " + (account ? tr("My account", "Mein Konto") : signup ? tr("Create account", "Konto erstellen") : tr("Sign in", "Anmelden"));
    el("signed-account").hidden = !account;
    el("main").classList.toggle("signin-layout", !account);
    document.body.classList.toggle("auth-page", !account);
    el("account-description").hidden = !account;
    const login = el("account-login");
    if (account) {
      if (login.parentElement !== el("account-method-slot"))
        el("account-method-slot").append(login);
      login.classList.add("embedded-login");
      login.querySelector("h2").hidden = true;
      for (const p of login.querySelectorAll(":scope > p")) p.hidden = true;
    }
    el("provider-buttons").replaceChildren();
    for (const provider of available.filter(
      (p) => !account?.identities.some((i) => i.provider === p),
    )) {
      const button = document.createElement("button");
      button.dataset.provider = provider;
      const name = ({ github: "GitHub", discord: "Discord", battlenet: "Battle.net" })[provider] || provider;
      button.textContent = account
        ? tr("Link " + name, name + " verknüpfen")
        : signup ? tr("Sign up with " + name, "Mit " + name + " registrieren") : tr("Sign in with " + name, "Mit " + name + " anmelden");
      button.onclick = () =>
        action(button, async () => {
          const r = await request("/auth/" + provider + "/start", "POST", {
            link: !!account,
          });
          location.assign(r.url);
        });
      el("provider-buttons").append(button);
    }
    const emailButton = el("email-signin-link");
    emailButton.href = account ? "/signin-email.html?link=1" : "/signin-email.html";
    emailButton.dataset.en = account ? "Link email" : "Sign in with email";
    emailButton.dataset.de = account ? "E-Mail verknüpfen" : "Mit E-Mail anmelden";
    emailButton.textContent = tr(emailButton.dataset.en, emailButton.dataset.de);
    const heading = el("account-heading");
    heading.dataset.en = account ? "My account" : "Sign in";
    heading.dataset.de = account ? "Mein Konto" : "Anmelden";
    heading.textContent = tr(heading.dataset.en, heading.dataset.de);
    if (!account && signup) {
      heading.dataset.en = "Create a GabbaProc account"; heading.dataset.de = "GabbaProc-Konto erstellen";
      heading.textContent = tr(heading.dataset.en, heading.dataset.de);
      emailButton.href = "/signin-email.html?mode=signup";
      emailButton.dataset.en = "Sign up with email"; emailButton.dataset.de = "Mit E-Mail registrieren";
      emailButton.textContent = tr(emailButton.dataset.en, emailButton.dataset.de);
    }
    const loginTitle = login.querySelector("h2");
    loginTitle.dataset.en = signup ? "Create your account" : "Welcome to GabbaProc";
    loginTitle.dataset.de = signup ? "Erstelle dein Konto" : "Willkommen bei GabbaProc";
    loginTitle.textContent = tr(loginTitle.dataset.en, loginTitle.dataset.de);
    el("signup-toggle").hidden = !!account;
    const switchLink = el("signup-link");
    switchLink.href = signup ? "/account.html" : "/account.html?mode=signup";
    el("signup-prompt").textContent = signup ? tr("Already have an account?", "Schon ein Konto?") : tr("New here?", "Noch kein Konto?");
    switchLink.textContent = signup ? tr("Sign in", "Anmelden") : tr("Create an account", "Konto erstellen");
    if (!account) return;
    const pending = pendingPairing();
    el("account-name").textContent =
      account.username ||
      tr("Choose your username", "Wähle deinen Benutzernamen");
    el("account-expiry").textContent = account.sessionExpiresAt
      ? tr("Signed in until ", "Angemeldet bis ") +
        new Date(account.sessionExpiresAt * 1000).toLocaleString(
          document.documentElement.lang,
        )
      : "";
    if (!el("account-username").value)
      el("account-username").value = account.username || "";
    window.dispatchEvent(
      new CustomEvent("gabbaproc-account", { detail: account }),
    );
    if (pending && !pairingShown) {
      el("pair-settings").open = true;
      pairingShown = true;
      el("pair-code").value = pending.code;
      el("pair-approve").scrollIntoView({ block: "center" });
    }
    el("account-identities").replaceChildren();
    for (const identity of account.identities) {
      const row = document.createElement("p");
      row.className = "identity-row";
      const label = document.createElement("span");
      label.className = "identity-provider";
      label.textContent =
        { email: "E-Mail", github: "GitHub", discord: "Discord", battlenet: "Battle.net" }[
          identity.provider
        ] || identity.provider;
      const value = document.createElement("span");
      value.textContent = identity.display;
      row.append(label, value);
      el("account-identities").append(row);
    }
    el("account-devices").replaceChildren();
    if (!account.devices.length) {
      el("account-devices").textContent = tr(
        "No companion connected yet.",
        "Noch keine Companion-App verbunden.",
      );
      el("pair-settings").open = true;
    }
    for (const device of account.devices) {
      const row = document.createElement("div");
      row.className = "device-row";
      const label = document.createElement("span");
      label.textContent =
        tr("Companion · ", "Companion · ") +
        device.id.slice(0, 8) +
        " · " +
        new Date(device.created * 1000).toLocaleDateString() +
        " ";
      row.append(label);
      if (device.revoked) {
        row.append(document.createTextNode(tr("Revoked", "Widerrufen")));
      } else {
        const button = document.createElement("button");
        button.textContent = tr("Revoke", "Widerrufen");
        button.onclick = () =>
          action(button, async () => {
            await request("/account/devices/" + device.id, "DELETE");
            await refresh();
          });
        row.append(button);
      }
      el("account-devices").append(row);
    }
  }
  async function refresh() {
    try {
      account = await request("/account");
    } catch (e) {
      if (e.status === 401 || e.status === 503) account = null;
      else throw e;
    }
    render();
  }
  el("account-profile").onsubmit = (event) => {
    event.preventDefault();
    action(event.submitter, async () => {
      try {
        await request("/account/profile", "PUT", {
          username: el("account-username").value.trim(),
        });
      } catch (error) {
        if (error.status === 409) {
          status(
            "This username is already taken.",
            "Dieser Benutzername ist bereits vergeben.",
          );
          return;
        }
        throw error;
      }
      await refresh();
      status("Username saved.", "Benutzername gespeichert.");
    });
  };
  el("account-logout").onclick = (event) =>
    action(event.target, async () => {
      await request("/auth/logout", "POST");
      location.assign("/account.html");
    });
  el("claim-device").onsubmit = (event) => {
    event.preventDefault();
    action(event.submitter, async () => {
      await request("/account/claim-device", "POST", undefined, {
        Authorization: "Bearer " + el("claim-token").value.trim(),
      });
      el("claim-token").value = "";
      await refresh();
      status("Existing device linked.", "Bestehender Gerätezugang verknüpft.");
    });
  };
  el("pair-approve").onsubmit = (event) => {
    event.preventDefault();
    action(event.submitter, async () => {
      const approvedCode = el("pair-code").value.trim().toUpperCase();
      await request("/device-link/approve", "POST", { userCode: approvedCode });
      if (pendingPairing()?.code === approvedCode) {
        try {
          localStorage.removeItem(pairingKey);
        } catch (_) {}
      }
      el("pair-code").value = "";
      el("pair-settings").open = false;
      await refresh();
      status(
        "Approved. The companion will finish connecting.",
        "Bestätigt. Die Companion-App schließt die Verbindung ab.",
      );
    });
  };
  el("account-new-device").onclick = (event) =>
    action(event.target, async () => {
      const r = await request("/account/devices", "POST");
      el("account-device-token").value = r.token;
      el("account-device-token").hidden = false;
      el("account-copy-token").hidden = false;
      await refresh();
      status(
        "Copy this token into the companion. It is shown only now.",
        "Diesen Token in die Companion-App kopieren. Er wird nur jetzt ausgegeben.",
      );
    });
  el("account-copy-token").onclick = (event) =>
    action(event.target, async () => {
      await navigator.clipboard.writeText(el("account-device-token").value);
      status("Token copied.", "Token kopiert.");
    });
  el("account-delete").onclick = (event) => {
    if (
      !confirm(
        tr(
          "Permanently delete this account and all contributions from linked devices?",
          "Dieses Konto und alle Beiträge verknüpfter Geräte endgültig löschen?",
        ),
      )
    )
      return;
    action(event.target, async () => {
      await request("/account", "DELETE");
      location.assign("/account.html");
    });
  };
  new MutationObserver(render).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["lang"],
  });
  (async () => {
    const config = await request("/auth/options");
    available = config.providers;
    el("email-signin-link").hidden = !config.email;
    await refresh();
    if (!available.length && !config.email)
      status(
        "Sign-in is currently unavailable. Please try again later.",
        "Anmeldung derzeit nicht verfügbar. Bitte später erneut versuchen.",
      );
    if (new URLSearchParams(location.search).get("auth") === "failed")
      status(
        "Sign-in failed or was cancelled. Please try again.",
        "Anmeldung fehlgeschlagen oder abgebrochen. Bitte erneut versuchen.",
      );
  })().catch(() =>
    status(
      "Account service unavailable. Please try again later.",
      "Kontodienst nicht erreichbar. Bitte später erneut versuchen.",
    ),
  );
})();
