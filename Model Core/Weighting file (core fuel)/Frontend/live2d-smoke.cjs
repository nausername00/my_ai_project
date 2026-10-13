// Live2D 运行时真实窗口冒烟验证（K3）：
// 启动独立 Electron 窗口加载 live2d-smoke.html，等待渲染页报告结果，截图存档并退出。
// 用法：node live2d-smoke.cjs
"use strict";

const { app, BrowserWindow } = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");
const {
  registerMolingScheme,
  registerMolingProtocol,
} = require("./live2d-protocol.cjs");

const projectRoot = path.resolve(__dirname, "..");
const outDir = path.join(__dirname, "..", "Testing & Evaluation", "tests", "k3_smoke_artifacts");

registerMolingScheme();

app.whenReady().then(async () => {
  try {
    await registerMolingProtocol(app, projectRoot, __dirname);
    const win = new BrowserWindow({
      width: 360,
      height: 480,
      show: false,
      backgroundColor: "#111318",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: process.env.MOLING_SMOKE_NO_SANDBOX !== "1",
      },
    });
    await win.loadURL("moling://local/live2d-smoke.html");
    win.webContents.on("console-message", (event, level, message, line, sourceId) => {
      console.log(`[renderer-console:${level}] ${message}`);
    });
    const result = await waitForSmokeResult(win, 30000);
    // 请求类型对照诊断
    const probe = await win.webContents.executeJavaScript(`(async () => {
      const url = "moling://local/model/狐仙花嫁/狐仙花嫁/狐仙花嫁.model3.json";
      const out = {};
      try { const r = await fetch(url); out.fetch = r.status; } catch (e) { out.fetch = "ERR:" + e.message; }
      try {
        out.img = await new Promise((res) => {
          const img = new Image();
          img.onload = () => res("ok:" + img.naturalWidth);
          img.onerror = () => res("ERR");
          img.src = url;
        });
      } catch (e) { out.img = "ERR:" + e.message; }
      try {
        out.xhr = await new Promise((res) => {
          const x = new XMLHttpRequest();
          x.onload = () => res("ok:" + x.status);
          x.onerror = () => res("ERR");
          x.open("GET", url);
          x.send();
        });
      } catch (e) { out.xhr = "ERR:" + e.message; }
      return JSON.stringify(out);
    })()`);
    // 主进程 net.fetch 对照
    let mainFetch = "n/a";
    try {
      const { net } = require("electron");
      const { pathToFileURL } = require("node:url");
      const { registerModelProtocol } = require("./live2d-protocol.cjs");
      const target = path.join(
        projectRoot,
        "Character",
        "狐仙花嫁",
        "狐仙花嫁",
        "狐仙花嫁.model3.json",
      );
      const r = await net.fetch(pathToFileURL(target).toString());
      mainFetch = "ok:" + r.status;
    } catch (e) {
      mainFetch = "ERR:" + e.message;
    }
    await fs.mkdir(outDir, { recursive: true });
    const image = await win.capturePage();
    const shotPath = path.join(outDir, "k3_live2d_smoke.png");
    await fs.writeFile(shotPath, image.toPNG());
    console.log(
      JSON.stringify({
        ok: result.ok,
        message: result.message,
        probe,
        mainFetch,
        screenshot: shotPath,
      }),
    );
    app.exit(result.ok ? 0 : 1);
  } catch (error) {
    console.log(
      JSON.stringify({ ok: false, message: "runner error: " + error.message }),
    );
    app.exit(1);
  }
});

function waitForSmokeResult(win, timeoutMs) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(async () => {
      try {
        const title = win.getTitle();
        if (title === "SMOKE_OK" || title === "SMOKE_FAIL") {
          clearInterval(timer);
          const detail = await win.webContents.executeJavaScript(
            "window.smokeResult || null",
          );
          resolve({ ok: title === "SMOKE_OK", message: detail?.message || title });
          return;
        }
        if (Date.now() - startedAt > timeoutMs) {
          clearInterval(timer);
          reject(new Error("超时未得到渲染结果"));
        }
      } catch {
        /* 继续等待 */
      }
    }, 400);
  });
}
