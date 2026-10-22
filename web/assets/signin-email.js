"use strict";
(() => {
  const el = id => document.getElementById(id);
  const tr = (en, de) => document.documentElement.lang === "de" ? de : en;
  function updateTitle() {
    const signup = new URLSearchParams(location.search).get("mode") === "signup";
    document.title = "GabbaProc · " + (signup ? tr("Create account with email", "Konto mit E-Mail erstellen") : tr("Email sign-in", "Mit E-Mail anmelden"));
  }
  updateTitle();
  new MutationObserver(updateTitle).observe(document.documentElement, {attributes: true, attributeFilter: ["lang"]});
  let challenge = null;
  if (new URLSearchParams(location.search).get("mode") === "signup") {
    const heading = document.querySelector("h1");
    heading.dataset.en = "Create an account with email"; heading.dataset.de = "Konto mit E-Mail erstellen";
    heading.textContent = tr(heading.dataset.en, heading.dataset.de);
  }
  const linking = new URLSearchParams(location.search).get("link") === "1";
  function status(en, de) {
    const node = el("email-status");
    node.dataset.en = en; node.dataset.de = de;
    node.textContent = tr(en, de);
  }
  async function request(path, body) {
    const response = await fetch("/api/auth/email/" + path, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      const error = new Error("Email sign-in failed"); error.status = response.status; throw error;
    }
    return response.json();
  }
  async function action(button, work) {
    button.disabled = true;
    try { await work(); }
    catch (error) {
      if (error.status === 429)
        status("Too many attempts. Please try again later.", "Zu viele Versuche. Bitte später erneut versuchen.");
      else
        status("Could not complete sign-in. Check your entry or request a new code.", "Anmeldung fehlgeschlagen. Bitte Eingabe prüfen oder einen neuen Code anfordern.");
    } finally { button.disabled = false; }
  }
  const hash = new URLSearchParams(location.hash.slice(1));
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  if (/^[A-Za-z0-9_-]{43}$/.test(hash.get("emailChallenge") || "") && /^[0-9]{8}$/.test(hash.get("emailCode") || "")) {
    challenge = hash.get("emailChallenge");
    el("email-verify").hidden = false;
    el("login-code").value = hash.get("emailCode");
    const email = hash.get("emailAddress") || "";
    if (email.length <= 254) {
      el("login-email").value = email;
      if (!el("login-email").checkValidity()) el("login-email").value = "";
    }
    status("Code filled in. Confirm it below in the browser where you requested it.", "Code eingefügt. Bitte in dem Browser bestätigen, in dem du ihn angefordert hast.");
  }
  el("email-login").onsubmit = event => {
    event.preventDefault();
    action(event.submitter, async () => {
      const result = await request("request", {email: el("login-email").value.trim(), link: linking});
      challenge = result.challenge;
      el("email-verify").hidden = false; el("login-code").value = ""; el("login-code").focus();
      status("Code sent. Check your inbox and spam folder.", "Code versendet. Bitte Posteingang und Spamordner prüfen.");
    });
  };
  el("email-verify").onsubmit = event => {
    event.preventDefault();
    action(event.submitter, async () => {
      await request("verify", {challenge, code: el("login-code").value.trim()});
      location.replace("/account.html");
    });
  };
})();
