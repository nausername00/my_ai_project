const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

// 墨灵移动端 PWA 打磨（2026-10-17）：语音输入 / 通知 / 续聊持久化。
// 静态断言：结构存在 + 关键逻辑在源码中出现 + 安全上下文降级约定。

const mobileDirectory = path.join(__dirname, "mobile");
const html = fs.readFileSync(path.join(mobileDirectory, "index.html"), "utf8");
const css = fs.readFileSync(path.join(mobileDirectory, "style.css"), "utf8");
const app = fs.readFileSync(path.join(mobileDirectory, "app.js"), "utf8");
const sw = fs.readFileSync(path.join(mobileDirectory, "sw.js"), "utf8");
const manifest = fs.readFileSync(path.join(mobileDirectory, "manifest.json"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "main.cjs"), "utf8");
const pkg = fs.readFileSync(path.join(__dirname, "package.json"), "utf8");
const api = fs.readFileSync(
  path.join(__dirname, "..", "Source code engine", "api.py"),
  "utf8",
);

test("mobile page defines voice input, notification toggle and clear-session controls", () => {
  assert.match(html, /id="micBtn"/);
  assert.match(html, /id="notifyToggle"/);
  assert.match(html, /id="clearBtn"/);
  // 通知开关带安全上下文说明（HTTP 局域网不可用）
  assert.match(html, /需 HTTPS\/本机/);
});

test("mobile styles cover mic listening state, toggle and danger button", () => {
  assert.match(css, /\.mic\.listening\s*\{/);
  assert.match(css, /@keyframes mic-pulse/);
  assert.match(css, /\.toggle\[aria-checked="true"\]/);
  assert.match(css, /\.danger\s*\{/);
  // hidden 必须压过 .settings 的 display:flex（否则设置面板默认展开）
  assert.match(css, /\.settings\[hidden\]\s*\{\s*display:\s*none;\s*\}/);
});

test("app.js wires voice recognition with graceful degradation", () => {
  // 语音识别使用 Web Speech（webkit 前缀兼容），且仅安全上下文可用
  assert.match(app, /SpeechRecognition/);
  assert.match(app, /webkitSpeechRecognition/);
  assert.match(app, /recognition\.lang = "zh-CN"/);
  assert.match(app, /canSpeak/);
  assert.match(app, /语音输入需要 HTTPS 或本机访问/);
  assert.match(app, /麦克风权限被拒绝/);
});

test("app.js supports configurable server address for the native shell (Capacitor)", () => {
  // App 内页面从 capacitor:// 加载，同源相对地址连不到电脑 → 必须可配置服务器地址
  assert.match(html, /id="serverInput"/);
  assert.match(html, /id="serverSave"/);
  assert.match(app, /moling_mobile_server/);
  assert.match(app, /function resolveApi\(\)/);
  assert.match(app, /localStorage\.getItem\(SERVER_KEY\)/);
  assert.match(app, /serverSave\.addEventListener/);
  assert.match(app, /API = resolveApi\(\);/);
});

test("app.js wires notifications behind a user switch and secure context", () => {
  assert.match(app, /"Notification" in window/);
  assert.match(app, /Notification\.requestPermission/);
  assert.match(app, /moling_mobile_notify/);
  // 后台收到回复才通知；断线/重连变化也通知
  assert.match(app, /document\.hidden && notifyOn/);
  assert.match(app, /sendNotification\(ok \? "连接恢复" : "连接断开"/);
  assert.match(app, /new Notification\(title, \{ body, tag: "moling-mobile" \}\)/);
});

test("app.js persists and restores chat history for seamless continuation", () => {
  assert.match(app, /moling_mobile_history/);
  assert.match(app, /HISTORY_LIMIT = 40/);
  assert.match(app, /persistHistory\(\)/);
  assert.match(app, /loadHistory\(\)/);
  // 恢复历史后不再重复显示欢迎语（无历史才显示）
  assert.match(app, /if \(history\.length === 0\)/);
  // 发送时仍只带最近 10 条上下文给后端
  assert.match(app, /history: history\.slice\(-10\)/);
  // 清空会话按钮清本机记录
  assert.match(app, /localStorage\.removeItem\(HISTORY_KEY\)/);
});

test("service worker cache bumped after mobile polish", () => {
  assert.match(sw, /moling-mobile-v2/);
  // 缓存清单包含全部静态资源
  for (const asset of ["index.html", "style.css", "app.js", "manifest.json", "icon.svg"]) {
    assert.match(sw, new RegExp(asset.replace(".", "\\.")));
  }
});

test("installed build keeps the mobile PWA reachable (regression guard)", () => {
  // 后端：MOLING_MOBILE_ROOT 环境变量可覆盖移动页静态根
  assert.match(api, /MOLING_MOBILE_ROOT/);
  assert.match(api, /os\.environ\.get\("MOLING_MOBILE_ROOT"/);
  // Electron：spawn 后端时注入移动页根（打包版 resources/mobile，开发版 Frontend/mobile）
  assert.match(main, /MOLING_MOBILE_ROOT:/);
  assert.match(main, /process\.resourcesPath, "mobile"/);
  assert.match(main, /app\.getAppPath\(\), "mobile"/);
  // 打包：extraResources 把 mobile 目录带进 resources
  assert.match(pkg, /"from": "mobile",\s*\n\s*"to": "mobile"/);
});

test("manifest keeps standalone PWA shell with icon", () => {
  assert.match(manifest, /"display": "standalone"/);
  assert.match(manifest, /"start_url": "\/v1\/mobile\/index\.html"/);
  assert.match(manifest, /icon\.svg/);
});
