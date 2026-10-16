const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontendDirectory = __dirname;
const html = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const renderer = fs.readFileSync(path.join(frontendDirectory, "renderer.js"), "utf8");
const main = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");
const preload = fs.readFileSync(path.join(frontendDirectory, "preload.cjs"), "utf8");

test("ocr UI: 输入区有识文字按钮", () => {
  assert.match(
    html,
    /id="ocr-button"[^>]*title="选择一张图片，识别其中的文字"/,
  );
});

test("ocr renderer: 绑定按钮、调用 ocrAnalyze、渲染字段表与文本块", () => {
  assert.match(renderer, /const ocrButton = document\.getElementById\("ocr-button"\)/);
  assert.match(renderer, /async function handleOcrImage\(\)/);
  assert.match(renderer, /window\.companion\.ocrAnalyze\(\)/);
  assert.match(renderer, /ocrButton\.addEventListener\("click", handleOcrImage\)/);
  assert.match(renderer, /ocr-fields-table/);
  assert.match(renderer, /ocr-text-block/);
  assert.match(renderer, /ocrButton\.disabled = false/);
});

test("ocr main.cjs: 注册 ocr-analyze IPC 并走 /v1/ocr/analyze", () => {
  assert.match(
    main,
    /ipcMain\.handle\("companion:ocr-analyze", chooseAndOcrImage\)/,
  );
  assert.match(main, /async function chooseAndOcrImage\(\)/);
  assert.match(
    main,
    /callApi\("\/v1\/ocr\/analyze", "POST", \{\s*image_base64: bytes\.toString\("base64"\),\s*content_type: contentType,\s*\}/,
  );
  assert.match(main, /"X-Moling-Vision-Consent": `\$\{consentPayload\}\.\$\{consent\}`/);
});

test("ocr preload: 暴露 ocrAnalyze", () => {
  assert.match(
    preload,
    /ocrAnalyze: \(\) => ipcRenderer\.invoke\("companion:ocr-analyze"\)/,
  );
});

test("ocr CSS: 结果卡片样式存在", () => {
  const css = fs.readFileSync(path.join(frontendDirectory, "style.css"), "utf8");
  assert.match(css, /\.ocr-analysis-result\s*\{/);
  assert.match(css, /\.ocr-fields-table\s*\{/);
  assert.match(css, /\.ocr-text-block\s*\{/);
  assert.match(css, /\.ocr-meta\s*\{/);
});
