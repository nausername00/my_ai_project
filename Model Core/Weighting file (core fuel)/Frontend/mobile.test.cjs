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

test("mobile page offers a connection self-test with layered diagnosis", () => {
  // 连接自检：按钮 + 结果区 + 按失败类型给分层排查提示
  assert.match(html, /id="testConnBtn"/);
  assert.match(html, /id="testConnResult"/);
  assert.match(app, /async function testConnection\(\)/);
  assert.match(app, /testConnBtn\?\.addEventListener\("click", testConnection\)/);
  // 探测后端 /health（不依赖 v1 前缀）
  assert.match(app, /fetch\(`\$\{base\}\/health`/);
  // 401/403 → token 提示；超时 → 启动方式提示；Failed to fetch → 分层排查清单
  assert.match(app, /401 \|\| res\.status === 403/);
  assert.match(app, /mobile_token\.txt/);
  assert.match(app, /启动手机端\.bat/);
  assert.match(app, /Windows 防火墙放行 8000/);
  // 诊断样式存在
  assert.match(css, /\.diag\.ok/);
  assert.match(css, /\.diag\.warn/);
  assert.match(css, /\.diag\.err/);
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

test("mobile page embeds a Live2D avatar stage (third tier C)", () => {
  // 舞台骨架：角色区 + Live2D 容器 + 文字降级
  assert.match(html, /id="avatarStage"/);
  assert.match(html, /id="live2d-stage"[^>]*hidden/);
  assert.match(html, /id="avatarFallback"/);
  // 运行时从本地 vendor 引入（打包进 App，离线可显示形象；模型走后端按需加载）
  assert.match(html, /vendor\/live2dcubismcore\.min\.js/);
  assert.match(html, /vendor\/live2d-runtime\.js/);
  assert.match(css, /\.avatar-stage\s*\{/);
  assert.match(css, /\.avatar-stage \.live2d-stage\s*\{/);
  assert.match(css, /\.avatar-fallback\[hidden\]\s*\{\s*display:\s*none;\s*\}/);
  // app.js：模型路径 + 后端资产 URL + 加载/眨眼/口型/降级
  assert.match(app, /MODEL_PATH = "狐仙花嫁\/狐仙花嫁\/狐仙花嫁\.model3\.json"/);
  assert.match(app, /\/v1\/model\/asset\?path=/);
  assert.match(app, /async function loadLive2D\(\)/);
  assert.match(app, /runtime\.Live2DModel\.from/);
  assert.match(app, /FileReferences/);
  assert.match(app, /function startTalking\(/);
  assert.match(app, /function stopTalking\(/);
  assert.match(app, /ParamEyeLOpen/);
  assert.match(app, /ParamMouthOpenY/);
  assert.match(app, /startTalking\(Math\.min\(8000/);
  assert.match(app, /loadLive2D\(\);/);
  // 后端：手机端模型只读端点（白名单 + 防穿越）
  assert.match(api, /def _serve_model_asset\(self, relative: str\)/);
  assert.match(api, /_MODEL_ROOT/);
  assert.match(api, /if relative\.startswith\(/);
  assert.match(api, /or "\.\." in relative\.split\("\/"\):/);
  assert.match(api, /path == "\/v1\/model\/asset"/);
});

test("mobile app launcher: shell only, frontend loads from PC (in-app update)", () => {
  const mobileAppDir = path.join(__dirname, "..", "..", "..", "MobileApp");
  const launcher = fs.readFileSync(path.join(mobileAppDir, "launcher", "index.html"), "utf8");
  const mobileApp = fs.readFileSync(path.join(mobileAppDir, "mobile_app", "index.html"), "utf8");
  const config = fs.readFileSync(path.join(mobileAppDir, "capacitor.config.json"), "utf8");
  const androidManifest = fs.readFileSync(
    path.join(mobileAppDir, "android", "app", "src", "main", "AndroidManifest.xml"),
    "utf8",
  );
  // 离线壳：webDir 指向 mobile_app（完整手机前端打入 APK，断网可打开，内更新走电脑端拉取）
  assert.match(config, /"webDir"\s*:\s*"mobile_app"/);
  // 历史在线引导页保留为备用入口（填地址跳转）
  assert.match(launcher, /id="server"/);
  assert.match(launcher, /\/v1\/mobile\//);
  // 离线壳内置完整前端：对话 + Live2D 舞台 + App 内服务器地址设置
  assert.match(mobileApp, /avatarStage/);
  assert.match(mobileApp, /live2d-stage/);
  assert.match(mobileApp, /serverInput/);
  assert.match(mobileApp, /电脑局域网 IP/);
  // 服务器地址记忆（App 内 localStorage 持久化 + 服务地址输入绑定）
  const mobileAppJs = fs.readFileSync(path.join(mobileAppDir, "mobile_app", "app.js"), "utf8");
  assert.match(mobileAppJs, /localStorage\.getItem\(SERVER_KEY\)/);
  assert.match(mobileAppJs, /serverInput\.value\.trim\(\)/);
  // 整页加载局域网 http 页面需允许 cleartext（Android 9+ 默认禁止）
  assert.match(androidManifest, /usesCleartextTraffic="true"/);
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

// ---------- B 手机入侵 + 语音接收（2026-10-21） ----------
test("mobile stage is tappable for headpat with local reward counting", () => {
  // 舞台改为 button 语义，点击=摸头；气泡容器与标题提示存在
  assert.match(html, /id="avatarStage" role="button"/);
  assert.match(html, /点击摸摸头/);
  assert.match(html, /id="stageBubble"/);
  assert.match(app, /moling_mobile_headpat_count/);
  // 摸头奖励：本机计数，每 5 次触发奖励台词（与桌面悬浮窗一致）
  assert.match(app, /function headpatFeedback\(\)/);
  assert.match(app, /被你摸了/);
  assert.match(app, /今天也最喜欢你/);
  // 舞台点击与键盘（无障碍）都能触发
  assert.match(app, /avatarStageEl\.addEventListener\("click", handleHeadpat\)/);
  assert.match(app, /event\.key === "Enter" \|\| event\.key === " "/);
  // 气泡样式：定位 + 箭头 + 显隐过渡
  assert.match(css, /\.avatar-stage \.stage-bubble/);
  assert.match(css, /\.stage-bubble::before/);
  assert.match(css, /\.stage-bubble\.show/);
});

test("mobile mood links to Live2D expression and stage halo", () => {
  // 情绪→表情映射与桌面端一致（心心眼/星星眼/脸红/流泪）
  assert.match(app, /MOOD_EXPRESSION_MAP = \{/);
  assert.match(app, /happy: "心心眼"/);
  assert.match(app, /surprised: "星星眼"/);
  assert.match(app, /shy: "脸红"/);
  assert.match(app, /worried: "流泪"/);
  // 通过 expressionManager 按 Name 匹配切表情；失败静默回退
  assert.match(app, /const defs = \(em && em\.definitions\) \|\| \[\]/);
  assert.match(app, /em\.setExpression\(idx\)/);
  // 舞台光晕情绪类
  assert.match(css, /\.avatar-stage\.mood-happy/);
  assert.match(css, /\.avatar-stage\.mood-warm/);
  assert.match(css, /\.avatar-stage\.mood-curious/);
  assert.match(css, /\.avatar-stage\.mood-shy/);
  assert.match(css, /\.avatar-stage:active \.live2d-stage/);
});

test("mobile wake-word listening: toggle, custom word, respond then send", () => {
  // 设置面板：唤醒开关 + 自定义唤醒词输入（默认「墨灵墨灵」）
  assert.match(html, /id="wakeToggle"/);
  assert.match(html, /id="wakeWord"/);
  assert.match(html, /value="墨灵墨灵"/);
  // 状态持久化 + 初始化恢复
  assert.match(app, /moling_mobile_wake_on/);
  assert.match(app, /moling_mobile_wake_word/);
  assert.match(app, /DEFAULT_WAKE_WORD = "墨灵墨灵"/);
  assert.match(app, /wakeOn = localStorage\.getItem\(WAKE_KEY\) === "1"/);
  // 唤醒循环：等唤醒词 → 回应 → 等指令 → 发送；持续监听自动续接
  assert.match(app, /wakePhase = "idle"/);
  assert.match(app, /transcript\.includes\(wakeWord\) \|\| transcript\.includes\("墨灵"\)/);
  assert.match(app, /墨灵在的哟/);
  assert.match(app, /sendMessage\(transcript\)/);
  assert.match(app, /rec\.continuous = true/);
  assert.match(app, /if \(wakeOn && !wakeStopped\)/);
  // 安全上下文限制：HTTP 局域网降级提示（与语音输入一致）
  assert.match(app, /语音接收需要 HTTPS 或本机访问/);
  assert.match(app, /wakeToggle\.disabled = !canSpeak/);
  assert.match(app, /麦克风权限被拒绝/);
  // 发送逻辑抽出 sendMessage 供输入框与唤醒共用
  assert.match(app, /async function sendMessage\(text\)/);
  assert.match(app, /composer\.addEventListener\("submit"/);
});
