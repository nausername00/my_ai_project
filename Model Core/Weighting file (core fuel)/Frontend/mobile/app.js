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

// ---------- 状态与消息 ----------
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
  try {
    const { status, body } = await api("/generate", {
      prompt: text,
      history: history.slice(-10),
    });
    if (status === 200 && typeof body.text === "string") {
      reply.textContent = body.text;
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
