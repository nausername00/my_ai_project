"use strict";

// 墨灵移动端轻量陪伴页：本地局域网直连后端 /v1/generate。
// 页面本身无数据；调用需遵循后端认证（非本机访问需 MOLING_API_TOKEN）。
// Service Worker 仅在 HTTPS 下注册（HTTP 局域网自动降级为无离线缓存）。

const chatLog = document.getElementById("chatLog");
const composer = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const statusDot = document.getElementById("statusDot");
const modelLabel = document.getElementById("modelLabel");
const settingsBtn = document.getElementById("settingsBtn");
const settingsPanel = document.getElementById("settingsPanel");
const tokenInput = document.getElementById("tokenInput");
const tokenSave = document.getElementById("tokenSave");

const API = `${location.origin}/v1`;
let history = [];

// 非本机访问必须携带 MOLING_API_TOKEN（Authorization: Bearer <token>）。
let apiToken = "";
try {
  apiToken = localStorage.getItem("moling_mobile_token") || "";
} catch { /* 隐私模式等场景降级为每次输入 */ }

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  return headers;
}

settingsBtn.addEventListener("click", () => {
  settingsPanel.hidden = !settingsPanel.hidden;
  if (!settingsPanel.hidden) tokenInput.focus();
});

tokenSave.addEventListener("click", () => {
  apiToken = tokenInput.value.trim();
  try {
    if (apiToken) localStorage.setItem("moling_mobile_token", apiToken);
    else localStorage.removeItem("moling_mobile_token");
  } catch { /* 忽略存储失败 */ }
  settingsPanel.hidden = true;
  refreshStatus();
});

function addBubble(text, who) {
  const el = document.createElement("div");
  el.className = `bubble ${who}`;
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}

function setStatus(ok, label) {
  statusDot.classList.toggle("on", ok);
  modelLabel.textContent = label;
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
  try {
    const { status, body } = await api("/generate", {
      prompt: text,
      history: history.slice(-10),
    });
    if (status === 200 && typeof body.text === "string") {
      reply.textContent = body.text;
      history.push(["user", text], ["assistant", body.text]);
      if (history.length > 40) history = history.slice(-40);
      setStatus(true, body.model || modelLabel.textContent);
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

// PWA：仅 HTTPS 下注册离线缓存
if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

tokenInput.value = apiToken;
refreshStatus();
setInterval(refreshStatus, 30000);
input.focus();
