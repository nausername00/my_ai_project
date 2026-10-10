"use strict";

// J3: real Electron window acceptance runner (main-process side).
// main.cjs invokes it when MOLING_E2E=1: drives real windows (main /
// floating / mini-game preview) through the real preload-to-IPC path and
// main-process policy probes, prints repeatable JSON results and sets the
// process exit code. Coverage levels are labelled explicitly: this is the
// "real window + real IPC" layer; unit/integration layers live in
// mini-game-policy.test.cjs, mini-game-drafts.test.cjs and test_api.py.

const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const E2E_TIMEOUT_MS = 10_000;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function withTimeout(promise, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error("E2E probe timeout: " + label)),
      E2E_TIMEOUT_MS,
    );
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function probeDom(window, selectors) {
  return window.webContents.executeJavaScript(
    "(() => {" +
      " const wanted = " + JSON.stringify(selectors) + ";" +
      " const found = {};" +
      " for (const sel of wanted) found[sel] = !!document.querySelector(sel);" +
      " return found;" +
      "})()",
    true,
  );
}

async function waitForWindowLoad(window, ms) {
  const delay = ms || 4000;
  if (window.webContents.isLoading()) {
    await new Promise((resolve) => window.webContents.once("did-finish-load", resolve));
  }
  await wait(delay);
}

async function runE2ESmoke({ app, mainWindow, floatingWindow }) {
  const results = [];
  const record = (scenario, pass, detail) => {
    results.push({ scenario, pass: Boolean(pass), detail: detail || "" });
  };

  // ---- 1. Main window key UI rendering ----
  try {
    await withTimeout(waitForWindowLoad(mainWindow), "main window load");
    const dom = await withTimeout(
      probeDom(mainWindow, [
        "#message-input",
        "#mini-game-plan",
        "#mini-game-preview",
        "#mini-game-draft-manage",
        "#mini-game-draft-promote",
        "#mini-game-draft-discard",
        "#emotion-tour-start",
      ]),
      "main window DOM probe",
    );
    const missing = Object.entries(dom)
      .filter(([, found]) => !found)
      .map(([sel]) => sel);
    record(
      "main-window key UI rendering",
      missing.length === 0,
      missing.length
        ? "missing: " + missing.join(", ")
        : "chat input, mini-game/draft buttons, emotion-tour button rendered",
    );
  } catch (error) {
    record("main-window key UI rendering", false, error.message);
  }

  // ---- 2. Floating window expanded-state rendering ----
  try {
    await withTimeout(waitForWindowLoad(floatingWindow), "floating window load");
    const dom = await withTimeout(
      probeDom(floatingWindow, ["#panel", "#thinking-box", "#btn-back"]),
      "floating window DOM probe",
    );
    const missing = Object.entries(dom)
      .filter(([, found]) => !found)
      .map(([sel]) => sel);
    record(
      "floating-window key elements rendering",
      missing.length === 0,
      missing.length
        ? "missing: " + missing.join(", ")
        : "#panel / #thinking-box / #btn-back rendered",
    );
  } catch (error) {
    record("floating-window key elements rendering", false, error.message);
  }

  // ---- 3. J0: mini-game preview isolation denial counts in a real window ----
  try {
    const { BrowserWindow, session } = require("electron");
    const { applyMiniGamePolicy } = require("../mini-game-policy.cjs");
    const { pathToFileURL } = require("node:url");
    const evilHtml =
      "<!doctype html><html><body><script>" +
      "window.open('https://evil.example/popup');" +
      "location.href='https://evil.example/nav';" +
      "fetch('https://evil.example/api').catch(function(){});" +
      "</script></body></html>";
    const evilPath = path.join(
      await fs.mkdtemp(path.join(os.tmpdir(), "moling-e2e-evil-")),
      "evil.html",
    );
    await fs.writeFile(evilPath, evilHtml, "utf8");
    const evilUrl = pathToFileURL(evilPath).href;
    const evilWindow = new BrowserWindow({
      show: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webviewTag: false,
        partition: "moling-e2e-preview",
      },
    });
    const previewSession = session.fromPartition("moling-e2e-preview");
    const { denials } = applyMiniGamePolicy({
      webContents: evilWindow.webContents,
      session: previewSession,
      allowedFileUrl: evilUrl,
    });
    await new Promise((resolve) => {
      evilWindow.webContents.once("did-finish-load", resolve);
      evilWindow.loadFile(evilPath);
    });
    await wait(1200);
    const total =
      denials.navigations + denials.popups + denials.requests + denials.downloads;
    const detail =
      "navigations=" + denials.navigations +
      " popups=" + denials.popups +
      " requests=" + denials.requests +
      " downloads=" + denials.downloads;
    record(
      "mini-game preview isolation: malicious page capabilities denied",
      total > 0,
      total > 0 ? detail : "no denials observed (" + detail + ")",
    );
    evilWindow.destroy();
  } catch (error) {
    record("mini-game preview isolation: malicious page capabilities denied", false, error.message);
  }

  // ---- 4. J1: draft IPC lifecycle through the real preload bridge ----
  // Note: reset needs a generated original (unit-tested in
  // mini-game-drafts.test.cjs); here we exercise the real IPC surface
  // write -> status -> read -> discard.
  try {
    const api = "window.companion";
    const write = await mainWindow.webContents.executeJavaScript(
      api + '.miniGameDraftWrite("<html><body>e2e-draft</body></html>").then(function(r){ return { saved: r && r.saved }; })',
      true,
    );
    const status = await mainWindow.webContents.executeJavaScript(
      api + ".miniGameDraftStatus().then(function(s){ return { hasWorking: s && s.hasWorking, hasOriginal: s && s.hasOriginal, projectExists: s && s.projectExists }; })",
      true,
    );
    const read = await mainWindow.webContents.executeJavaScript(
      api + ".miniGameDraftRead().then(function(r){ return { working: r && r.working }; })",
      true,
    );
    const discard = await mainWindow.webContents.executeJavaScript(
      api + ".miniGameDraftDiscard().then(function(r){ return { discarded: r && r.discarded }; })",
      true,
    );
    const afterDiscard = await mainWindow.webContents.executeJavaScript(
      api + ".miniGameDraftStatus().then(function(s){ return { hasWorking: s && s.hasWorking }; })",
      true,
    );
    const pass =
      write.saved &&
      status.hasWorking &&
      read.working === "<html><body>e2e-draft</body></html>" &&
      discard.discarded &&
      !afterDiscard.hasWorking;
    record(
      "draft IPC lifecycle (write->status->read->discard)",
      pass,
      JSON.stringify({ write, status, read, discard, afterDiscard }),
    );
  } catch (error) {
    record("draft IPC lifecycle (write->status->read->discard)", false, error.message);
  }

  // ---- 5. Coverage labelling ----
  const covered = {
    unitIntegration: [
      "mini-game-policy.test.cjs (negative policy)",
      "mini-game-drafts.test.cjs (lifecycle / create-only)",
      "test_api.py (image signature/size/decode/one-shot consent)",
      "layout.test.cjs / floating-avatar.test.cjs (static anchors)",
    ],
    realWindow: [
      "main-window key UI rendering",
      "floating-window key elements rendering",
      "mini-game preview isolation denial counts (real policy mount)",
      "draft IPC lifecycle (real preload->IPC)",
    ],
    manualChecklist: [
      "avatar appearance / portrait-mode switch visual confirmation",
      "image-analysis error message visibility and styling",
      "draft promote second-confirmation dialog",
      "floating window always-on-top / expand / collapse interaction feel",
      "packaged build (dist:win) behaviour after install",
    ],
  };
  record("coverage labelling", true, JSON.stringify(covered));

  const allPass = results.every((r) => r.pass);
  console.log("MOLING_E2E_RESULT=" + JSON.stringify(results, null, 2));
  app.exit(allPass ? 0 : 1);
  return allPass;
}

module.exports = { runE2ESmoke };