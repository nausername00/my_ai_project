"use strict";

// 墨灵移动端轻量陪伴页：本地局域网直连后端 /v1/generate。
// 页面本身无数据；调用需遵循后端认证（非本机访问需 MOLING_API_TOKEN）。
// Service Worker 仅在 HTTPS 下注册（HTTP 局域网自动降级为无离线缓存）。
//
// 功能打磨（2026-10-17）：语音输入（Web Speech，仅安全上下文可用）、
// 新回复系统通知（Notification，仅安全上下文可用）、续聊（history 持久化到 localStorage）。

const chatLog = document.getElementById("chatLog");
const composer = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const statusDot = document.getElementById("statusDot");
const modelLabel = document.getElementById("modelLabel");
const settingsBtn = document.getElementById("settingsBtn");
const settingsPanel = document.getElementById("settingsPanel");
const tokenInput = document.getElementById("tokenInput");
const tokenSave = document.getElementById("tokenSave");
const serverInput = document.getElementById("serverInput");
const serverSave = document.getElementById("serverSave");
const notifyToggle = document.getElementById("notifyToggle");
const clearBtn = document.getElementById("clearBtn");

const SERVER_KEY = "moling_mobile_server";
const TOKEN_KEY = "moling_mobile_token";
const HISTORY_KEY = "moling_mobile_history";

// 第三梯队 C：手机端 Live2D 角色。模型在电脑端 Character 目录，
// 通过后端只读端点 /v1/model/asset 按需加载（桌面壳用 moling://，手机 WebView 无此协议）。
const MODEL_PATH = "狐仙花嫁/狐仙花嫁/狐仙花嫁.model3.json";
const MODEL_DIR = MODEL_PATH.slice(0, MODEL_PATH.lastIndexOf("/"));

// 把 Character 目录内的相对路径转成后端模型资源绝对 URL。
function modelAssetUrl(relative) {
  const base = API.replace(/\/v1$/, "");
  return `${base}/v1/model/asset?path=${encodeURIComponent(relative.replace(/^\/+/, ""))}`;
}

// API 基地址：优先用设置里保存的服务器地址（App 内必填），否则自动同源（浏览器打开本页）。
function resolveApi() {
  const saved = localStorage.getItem(SERVER_KEY);
  const base = (saved || location.origin).replace(/\/+$/, "");
  return `${base}/v1`;
}
let API = resolveApi();
const HISTORY_LIMIT = 40;

// 安全上下文：Notification / Web Speech / SW 离线缓存仅在 HTTPS 或本机（localhost）可用。
const secureCtx = window.isSecureContext === true;
const canNotify = secureCtx && "Notification" in window;
const canSpeak = secureCtx && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

let history = [];
let online = false;

// 非本机访问必须携带 MOLING_API_TOKEN（Authorization: Bearer <token>）。
let apiToken = "";
try {
  apiToken = localStorage.getItem("moling_mobile_token") || "";
} catch { /* 隐私模式等场景降级为每次输入 */ }

// 通知开关（默认关，尊重用户）
let notifyOn = false;
try {
  notifyOn = localStorage.getItem("moling_mobile_notify") === "1";
} catch { /* 忽略存储失败 */ }

function persistHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-HISTORY_LIMIT)));
  } catch { /* 存储满/隐私模式：仅内存会话 */ }
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((pair) => Array.isArray(pair) && pair.length === 2)) {
      history = parsed.slice(-HISTORY_LIMIT);
    }
  } catch { /* 解析失败按空会话处理 */ }
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  return headers;
}

function addBubble(text, who) {
  const el = document.createElement("div");
  el.className = `bubble ${who}`;
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}

function setStatus(ok, label) {
  const wasOnline = online;
  online = ok;
  statusDot.classList.toggle("on", ok);
  modelLabel.textContent = label;
  // 断线/重连变化时发一条系统通知（后台时才有意义，且开关开启时）。
  if (ok !== wasOnline && notifyOn && document.hidden) {
    sendNotification(ok ? "连接恢复" : "连接断开", ok ? "墨灵已重新连接。" : "暂时连不上墨灵，稍后再试。");
  }
}

function sendNotification(title, body) {
  if (!canNotify || Notification.permission !== "granted") return;
  try {
    const n = new Notification(title, { body, tag: "moling-mobile" });
    if (typeof n.close === "function") setTimeout(() => n.close(), 6000);
  } catch { /* 通知创建失败静默 */ }
}

// ---------- 设置面板 ----------
settingsBtn.addEventListener("click", () => {
  settingsPanel.hidden = !settingsPanel.hidden;
  if (!settingsPanel.hidden) tokenInput.focus();
});

tokenSave.addEventListener("click", () => {
  apiToken = tokenInput.value.trim();
  try {
    if (apiToken) localStorage.setItem(TOKEN_KEY, apiToken);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* 忽略存储失败 */ }
  settingsPanel.hidden = true;
  refreshStatus();
});

serverSave.addEventListener("click", () => {
  const raw = serverInput.value.trim();
  try {
    if (raw) localStorage.setItem(SERVER_KEY, raw.replace(/\/+$/, ""));
    else localStorage.removeItem(SERVER_KEY);
  } catch { /* 忽略存储失败 */ }
  API = resolveApi();
  settingsPanel.hidden = true;
  refreshStatus();
});

// ---------- 连接自检 ----------
// 把"Failed to fetch"变成可操作的分层诊断：网络不通 / 后端未开 / 防火墙 / 地址或 token 问题。
async function testConnection() {
  const result = document.getElementById("testConnResult");
  const btn = document.getElementById("testConnBtn");
  if (!result || !btn) return;
  result.textContent = "正在探测…";
  result.className = "diag";
  btn.disabled = true;
  const base = API.replace(/\/v1$/, "");
  try {
    const res = await fetch(`${base}/health`, {
      headers: authHeaders(),
      signal: AbortSignal.timeout(6000),
    });
    if (res.ok) {
      result.textContent = "✅ 后端已连通。若仍无法对话：检查 API Token 是否填对（设置右上角 ⚙）。";
      result.className = "diag ok";
    } else if (res.status === 401 || res.status === 403) {
      result.textContent = `⚠️ 后端可达但返回 ${res.status}：非本机访问必须填写正确的 API Token（电脑 mobile_token.txt）。`;
      result.className = "diag warn";
    } else {
      result.textContent = `⚠️ 后端可达但返回 HTTP ${res.status}。`;
      result.className = "diag warn";
    }
  } catch (error) {
    const msg = String(error && error.message || error);
    if (/abort|timeout/i.test(msg)) {
      result.textContent = "❌ 连接超时：确认电脑后端已用「启动手机端.bat」启动（它才会监听 0.0.0.0 供手机访问）。";
    } else {
      result.textContent = "❌ 无法连接（Failed to fetch）。依次排查：①手机与电脑连同一 WiFi；②电脑已用「启动手机端.bat」启动；③Windows 防火墙放行 8000 入站（首次启动弹窗点允许）；④服务器地址填电脑局域网 IP（如 http://192.168.1.5:8000）。";
    }
    result.className = "diag err";
  } finally {
    btn.disabled = false;
  }
}
const testConnBtn = document.getElementById("testConnBtn");
testConnBtn?.addEventListener("click", testConnection);

// ---------- 通知开关 ----------
function applyNotifyUI() {
  notifyToggle.textContent = notifyOn ? "开" : "关";
  notifyToggle.setAttribute("aria-checked", String(notifyOn));
  if (!canNotify) {
    notifyToggle.disabled = true;
    notifyToggle.title = "通知需 HTTPS 或本机访问（HTTP 局域网不可用）";
  }
}
notifyToggle.addEventListener("click", async () => {
  if (!canNotify) return;
  if (Notification.permission === "default") {
    try {
      await Notification.requestPermission();
    } catch { /* 忽略 */ }
  }
  if (Notification.permission === "granted") {
    notifyOn = !notifyOn;
    try {
      localStorage.setItem("moling_mobile_notify", notifyOn ? "1" : "0");
    } catch { /* 忽略 */ }
    applyNotifyUI();
    if (notifyOn) sendNotification("通知已开启", "墨灵回复时会在后台提醒你。");
  } else {
    sendBtn.title = "通知权限被拒绝，请在浏览器站点设置中允许";
  }
});

// ---------- 清空会话 ----------
clearBtn.addEventListener("click", () => {
  history = [];
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch { /* 忽略 */ }
  chatLog.replaceChildren();
  addBubble("嗨～我是墨灵，想聊点什么？", "bot");
  input.focus();
});

// ---------- 语音输入（Web Speech，仅安全上下文） ----------
let recognition = null;
let speaking = false;

function setMicState(active) {
  micBtn.classList.toggle("listening", active);
  micBtn.setAttribute("aria-label", active ? "停止语音输入" : "语音输入");
}

function toggleSpeech() {
  if (!canSpeak) {
    addBubble("语音输入需要 HTTPS 或本机访问（当前 HTTP 局域网不可用）。", "bot");
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!recognition) {
    recognition = new SR();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((r) => r[0].transcript)
        .join("");
      if (transcript) {
        input.value = transcript;
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        addBubble("麦克风权限被拒绝，请在浏览器设置中允许后重试。", "bot");
      } else if (event.error !== "aborted") {
        addBubble(`语音识别出错：${event.error}`, "bot");
      }
      setMicState(false);
    };
  }
  if (speaking) {
    recognition.stop();
  } else {
    try {
      recognition.start();
      speaking = true;
      setMicState(true);
    } catch { /* 连续快速点击时的重复 start 异常，忽略 */ }
  }
  // onend 里统一复位 speaking，这里避免重复 start 后误判。
  recognition.onend = () => {
    speaking = false;
    setMicState(false);
  };
}
micBtn.addEventListener("click", toggleSpeech);
setMicState(false);

// ---------- Live2D 角色（第三梯队 C） ----------
let live2d = null;          // { app, model, stage, fallback, talking }
let live2dFailed = false;
let blinkTimer = null;
let mouthTimer = null;

function fitLive2D(model, stage) {
  const cw = stage.clientWidth || 300;
  const ch = stage.clientHeight || 200;
  const bw = model.width || cw;
  const bh = model.height || ch;
  const scale = Math.min(cw / (bw || 1), ch / (bh || 1)) * 0.96;
  model.scale.set(scale);
  model.anchor.set(0.5, 0.5);
  model.x = cw / 2;
  model.y = ch / 2;
}

// 自动眨眼：随机间隔闭上 90-160ms（不打断说话等状态）。
function startBlink() {
  stopBlink();
  const loop = () => {
    blinkTimer = setTimeout(() => {
      const model = live2d && live2d.model;
      if (!model || (live2d && live2d.talking)) {
        blinkTimer = setTimeout(loop, 300);
        return;
      }
      const core = model.internalModel && model.internalModel.coreModel;
      if (core) {
        core.setParameterValueById("ParamEyeLOpen", 0);
        core.setParameterValueById("ParamEyeROpen", 0);
        setTimeout(() => {
          core.setParameterValueById("ParamEyeLOpen", 1);
          core.setParameterValueById("ParamEyeROpen", 1);
        }, 90 + Math.random() * 70);
      }
      blinkTimer = setTimeout(loop, 1800 + Math.random() * 2400);
    }, 1800 + Math.random() * 2400);
  };
  loop();
}

function stopBlink() {
  if (blinkTimer) clearTimeout(blinkTimer);
  blinkTimer = null;
}

// 说话口型：按预估时长周期开合嘴部（近似 K5；真麦/真声留待后续深化）。
function startTalking(ms) {
  const model = live2d && live2d.model;
  if (!model) return;
  stopTalking();
  live2d.talking = true;
  const core = model.internalModel && model.internalModel.coreModel;
  const step = () => {
    if (!core || !live2d || !live2d.talking) return;
    core.setParameterValueById("ParamMouthOpenY", Math.random());
    mouthTimer = setTimeout(step, 120 + Math.random() * 140);
  };
  step();
  setTimeout(() => stopTalking(), ms || 2000);
}

function stopTalking() {
  if (mouthTimer) clearTimeout(mouthTimer);
  mouthTimer = null;
  if (live2d && live2d.talking) {
    live2d.talking = false;
    const core = live2d.model && live2d.model.internalModel && live2d.model.internalModel.coreModel;
    if (core) core.setParameterValueById("ParamMouthOpenY", 0);
  }
}

// 预取 model3.json，把子资源相对路径改写为后端绝对 asset URL，再以 Blob 加载。
async function loadLive2D() {
  const stage = document.getElementById("live2d-stage");
  const fallback = document.getElementById("avatarFallback");
  if (!stage || live2d || live2dFailed) return;
  const runtime = window.MOLING_LIVE2D;
  if (!runtime || !runtime.Live2DModel) {
    live2dFailed = true;
    return;
  }
  try {
    const modelUrl = modelAssetUrl(MODEL_PATH);
    const res = await fetch(modelUrl, { headers: authHeaders() });
    if (!res.ok) throw new Error(`model3 ${res.status}`);
    const raw = await res.json();
    // 改写 FileReferences（Moc/Textures/Motions/Expressions）为绝对 URL
    const refs = raw.FileReferences || {};
    const abs = (rel) => {
      if (!rel || typeof rel !== "string") return rel;
      return modelAssetUrl(`${MODEL_DIR}/${rel.replace(/^\/+/, "")}`);
    };
    if (refs.Moc) refs.Moc = abs(refs.Moc);
    if (Array.isArray(refs.Textures)) refs.Textures = refs.Textures.map(abs);
    if (Array.isArray(refs.Motions)) {
      for (const group of refs.Motions) {
        if (!Array.isArray(group)) continue;
        for (const m of group) if (m && typeof m.File === "string") m.File = abs(m.File);
      }
    }
    if (Array.isArray(refs.Expressions)) {
      for (const e of refs.Expressions) if (e && typeof e.File === "string") e.File = abs(e.File);
    }
    const blob = new Blob([JSON.stringify(raw)], { type: "application/json" });
    const model = await runtime.Live2DModel.from(URL.createObjectURL(blob));
    model.autoUpdate = true;
    stage.hidden = false;
    fallback.hidden = true;
    stage.replaceChildren();
    stage.appendChild(model.canvas || model.view || model);
    live2d = { model, stage, fallback, talking: false };
    fitLive2D(model, stage);
    startBlink();
    window.addEventListener("resize", () => fitLive2D(model, stage));
  } catch (error) {
    live2dFailed = true;
    stage.hidden = true;
    fallback.hidden = false;
    console.warn("手机端 Live2D 加载失败（自动降级为文字形象）：", error);
  }
}


async function api(path, payload) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return { status: res.status, body: await res.json().catch(() => ({})) };
}

async function refreshStatus() {
  try {
    const res = await fetch(`${API}/status/metrics`, {
      headers: authHeaders(),
    });
    const body = await res.json();
    const model = body.model || body.engine?.model || "未知模型";
    setStatus(true, String(model));
  } catch {
    setStatus(false, "离线");
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  input.style.height = "auto";
  addBubble(text, "user");
  const reply = addBubble("…", "bot");
  sendBtn.disabled = true;
  stopTalking();
  try {
    const { status, body } = await api("/generate", {
      prompt: text,
      history: history.slice(-10),
    });
    if (status === 200 && typeof body.text === "string") {
      reply.textContent = body.text;
      // 回复时让 Live2D 角色开口说话（时长按回复长度估算）
      startTalking(Math.min(8000, 800 + body.text.length * 40));
      history.push(["user", text], ["assistant", body.text]);
      persistHistory();
      setStatus(true, body.model || modelLabel.textContent);
      // 后台收到回复 → 系统通知（开关开启时）。
      if (document.hidden && notifyOn) {
        const brief = body.text.length > 60 ? `${body.text.slice(0, 60)}…` : body.text;
        sendNotification("墨灵回复了", brief);
      }
    } else if (status === 401) {
      reply.textContent = "未授权：点击右上角 ⚙ 填入 API Token 后重试。";
      settingsPanel.hidden = false;
      tokenInput.focus();
    } else {
      reply.textContent = body.error || `请求失败（HTTP ${status}）`;
    }
  } catch (error) {
    reply.textContent = `连接失败：${error.message}`;
    setStatus(false, "离线");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
});

// ---------- 初始化 ----------
serverInput.value = localStorage.getItem(SERVER_KEY) || "";
// 第三梯队 C：尝试加载 Live2D 角色（失败自动降级为文字形象，不阻塞聊天）
loadLive2D();
// 续聊：恢复本机保存的会话（最近 40 条），无记录则显示欢迎语。
loadHistory();
if (history.length === 0) {
  addBubble("嗨～我是墨灵，想聊点什么？", "bot");
} else {
  for (const [who, text] of history) {
    addBubble(text, who === "user" ? "user" : "bot");
  }
}

// PWA：仅 HTTPS 下注册离线缓存
if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

tokenInput.value = apiToken;
applyNotifyUI();
refreshStatus();
setInterval(refreshStatus, 30000);
input.focus();
