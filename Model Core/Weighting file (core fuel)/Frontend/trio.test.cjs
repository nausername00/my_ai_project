const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontendDirectory = __dirname;
const html = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const renderer = fs.readFileSync(path.join(frontendDirectory, "renderer.js"), "utf8");
const main = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");
const preload = fs.readFileSync(path.join(frontendDirectory, "preload.cjs"), "utf8");

test("trio UI: 输入区有三角按钮，且面板包含角色区/输入/轮数/运行/结果", () => {
  assert.match(html, /id="trio-button"[^>]*title="三角协作：火破局 · 冰守界 · 衡裁决"/);
  assert.match(html, /class="trio-panel" id="trio-panel"[^>]*hidden/);
  assert.match(html, /id="trio-roles"/);
  assert.match(html, /id="trio-message"/);
  assert.match(html, /id="trio-rounds"/);
  assert.match(html, /id="trio-run"/);
  assert.match(html, /id="trio-result"[^>]*hidden/);
  assert.match(html, /id="trio-close"/);
});

test("trio renderer: 绑定面板开关、角色加载与运行，且运行前校验非空", () => {
  assert.match(renderer, /const trioButton = document\.getElementById\("trio-button"\)/);
  assert.match(renderer, /async function loadTrioRoles\(\)/);
  assert.match(renderer, /window\.companion\.trioRoles\(\)/);
  assert.match(renderer, /window\.companion\.trioRun\(message, rounds\)/);
  assert.match(renderer, /trioRunBtn\.addEventListener\("click"/);
  assert.match(renderer, /if \(!message\)/);
  assert.match(renderer, /trioRunBtn\.disabled = true/);
});

test("trio renderer 完善: 结构化渲染 + Enter/Esc + 回填聊天", () => {
  assert.match(renderer, /function renderTrioResult\(result\)/);
  assert.match(renderer, /function verdictLabel\(verdict\)/);
  assert.match(renderer, /trioResult\.replaceChildren\(\)/);
  assert.match(renderer, /card\.className = `trio-round trio-round-\$\{String\(round\.role \|\| ""\)\.toLowerCase\(\)\}`/);
  assert.match(renderer, /badge\.className = `trio-verdict trio-verdict-\$\{String\(round\.verdict\)\.toLowerCase\(\)\}`/);
  assert.match(renderer, /调和·衡 裁决/);
  assert.match(renderer, /把结论带回聊天/);
  assert.match(renderer, /input\.value = decision\.final/);
  assert.match(renderer, /event\.key === "Enter" && !event\.shiftKey/);
  assert.match(renderer, /event\.key === "Escape"\) toggleTrioPanel\(false\)/);
});

test("trio main.cjs: 注册 roles 与 run 两个 IPC 通道，run 校验 max_rounds 入参映射", () => {
  assert.match(
    main,
    /ipcMain\.handle\("companion:trio-roles", \(\) => callApi\("\/v1\/avatars\/trio-roles"\)\)/,
  );
  assert.match(
    main,
    /ipcMain\.handle\(\s*"companion:trio-run",\s*\(_event, message, maxRounds\)\s*=>\s*callApi\("\/v1\/avatars\/trio",\s*"POST",\s*\{\s*message,\s*max_rounds: maxRounds\s*\}\)/,
  );
});

test("trio preload: 向渲染进程暴露 trioRoles / trioRun", () => {
  assert.match(preload, /trioRoles: \(\) => ipcRenderer\.invoke\("companion:trio-roles"\)/);
  assert.match(
    preload,
    /trioRun: \(message, maxRounds\) =>\s+ipcRenderer\.invoke\("companion:trio-run", message, maxRounds\)/,
  );
});

test("trio CSS: 面板与角色芯片样式存在", () => {
  const css = fs.readFileSync(path.join(frontendDirectory, "style.css"), "utf8");
  assert.match(css, /\.trio-panel\s*\{/);
  assert.match(css, /\.trio-panel\[hidden\]\s*\{\s*display:\s*none;\s*\}/);
  assert.match(css, /\.trio-role-chip\s*\{/);
  assert.match(css, /\.trio-role-fire\s*\{/);
  assert.match(css, /\.trio-role-ice\s*\{/);
  assert.match(css, /\.trio-role-balance\s*\{/);
  assert.match(css, /\.trio-round\s*\{/);
  assert.match(css, /\.trio-round-fire\s*\{/);
  assert.match(css, /\.trio-round-ice\s*\{/);
  assert.match(css, /\.trio-round-balance\s*\{/);
  assert.match(css, /\.trio-verdict-accept\s*\{/);
  assert.match(css, /\.trio-fill\s*\{/);
});
