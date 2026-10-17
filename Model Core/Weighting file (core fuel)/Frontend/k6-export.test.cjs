const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontendDirectory = __dirname;
const html = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const css = fs.readFileSync(path.join(frontendDirectory, "style.css"), "utf8");
const renderer = fs.readFileSync(path.join(frontendDirectory, "renderer.js"), "utf8");
const main = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");
const preload = fs.readFileSync(path.join(frontendDirectory, "preload.cjs"), "utf8");

test("K6 export panel exists in the performance settings tab", () => {
  assert.match(html, /id="k6-timeline-input"/);
  assert.match(html, /id="k6-load-demo"/);
  assert.match(html, /id="k6-background"/);
  assert.match(html, /id="k6-side"/);
  assert.match(html, /id="k6-outdir"/);
  assert.match(html, /id="k6-export-start"/);
  assert.match(html, /id="k6-export-cancel"/);
  assert.match(html, /id="k6-export-progress"/);
  assert.match(html, /id="k6-export-bar"/);
  assert.match(html, /id="k6-export-preview"/);
  assert.match(html, /id="k6-export-status"/);
  // 透明模式说明：保留 PNG 序列素材
  assert.match(html, /transparent[\s\S]*?保留 PNG 序列素材/);
});

test("K6 export styles define progress and preview rendering", () => {
  assert.match(css, /\.k6-export-progress\s*\{[\s\S]*?\}/);
  assert.match(css, /\.k6-export-preview\s*\{[\s\S]*?\}/);
  assert.match(css, /\.k6-export-progress progress\s*\{[\s\S]*?accent-color/);
});

test("main process exposes K6 export IPC handlers with validation", () => {
  assert.match(main, /ipcMain\.handle\("companion:k6-export-start"/);
  assert.match(main, /ipcMain\.handle\("companion:k6-export-cancel"/);
  assert.match(main, /ipcMain\.handle\("companion:k6-export-status"/);
  // 默认输出目录兜底到 Character/K6 Output
  assert.match(main, /"K6 Output"/);
  // background 只允许 transparent 或 #rrggbb
  assert.match(main, /background 只允许 transparent 或 #rrggbb/);
  // 取消用 taskkill 终止子进程树
  assert.match(main, /taskkill/);
});

test("preload bridges the eight missing keys plus K6 export calls", () => {
  for (const key of [
    "memoryUsage",
    "statusMetrics",
    "getPerformanceRules",
    "savePerformanceRules",
    "classifyCue",
    "backupCreate",
    "exportMemories",
    "importMemories",
    "k6ExportStart",
    "k6ExportCancel",
    "k6ExportStatus",
  ]) {
    assert.match(preload, new RegExp(`${key}:`));
  }
  assert.match(preload, /companion:k6-export-start/);
  assert.match(preload, /companion:k6-export-cancel/);
  assert.match(preload, /companion:k6-export-status/);
});

test("renderer wires K6 export UI and ships a demo timeline", () => {
  assert.match(renderer, /const K6_DEMO_TIMELINE = \{/);
  assert.match(renderer, /fps: 10/);
  assert.match(renderer, /width: 1280/);
  assert.match(renderer, /expression: "脸红"/);
  assert.match(renderer, /expression: "心心眼"/);
  assert.match(renderer, /k6ExportStart\(/);
  assert.match(renderer, /k6ExportCancel\(/);
  assert.match(renderer, /k6ExportStatus\(/);
  assert.match(renderer, /k6LoadDemo\.addEventListener/);
  // 导出中禁用开始、启用取消
  assert.match(renderer, /k6ExportStartBtn\.disabled = active/);
  assert.match(renderer, /k6ExportCancelBtn\.disabled = !active/);
});
