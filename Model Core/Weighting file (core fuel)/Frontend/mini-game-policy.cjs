"use strict";

// 生成 HTML 小游戏预览的强制隔离策略（J0）。
//
// 背景：Electron 的 sandbox + contextIsolation 只隔离渲染进程与 Node，
// 并不等于"离线"或"不可达网络"。这里由主进程对预览窗口挂载可测试的
// 策略，逐项拦截：导航、弹窗、下载、网络请求、外部协议与权限请求。
// 原则：只允许加载指定的本地预览文件，其余一律拒绝。

function isBlockedUrl(url, allowedFileUrl) {
  if (typeof url !== "string" || url.length === 0) return true;
  if (url === allowedFileUrl) return false;
  let allowedPath = null;
  try {
    allowedPath = decodeURIComponent(new URL(allowedFileUrl).pathname);
  } catch {
    return true;
  }
  try {
    const u = new URL(url);
    if (u.protocol === "file:") {
      try {
        const path = decodeURIComponent(u.pathname);
        // 允许同文件不同查询/哈希；其余 file: 一律拒绝。
        return path !== allowedPath;
      } catch {
        return true;
      }
    }
    // 非 file: 协议（http/https/ws/wss/data/blob/javascript 等）全部拒绝。
    return true;
  } catch {
    // URL 解析失败视为不可信。
    return true;
  }
}

function applyMiniGamePolicy({ webContents, session, allowedFileUrl }) {
  if (!webContents || typeof webContents.on !== "function") {
    throw new TypeError("webContents with .on() is required");
  }
  if (typeof allowedFileUrl !== "string" || allowedFileUrl.length === 0) {
    throw new TypeError("allowedFileUrl is required");
  }
  const denials = {
    navigations: 0,
    popups: 0,
    downloads: 0,
    requests: 0,
    permissions: 0,
  };

  // 弹窗（window.open / target=_blank / showModalDialog 等）一律拒绝。
  if (typeof webContents.setWindowOpenHandler === "function") {
    webContents.setWindowOpenHandler(() => {
      denials.popups += 1;
      return { action: "deny" };
    });
  }

  // 页面导航：只允许留在指定的预览文件上；任何离开（含新 URL、hash 外导航）都阻止。
  if (typeof webContents.on === "function") {
    webContents.on("will-navigate", (event, url) => {
      if (isBlockedUrl(url, allowedFileUrl)) {
        denials.navigations += 1;
        event.preventDefault();
      }
    });

    // 下载一律拒绝。
    webContents.on("will-download", (event) => {
      denials.downloads += 1;
      event.preventDefault();
    });
  }

  if (session && typeof session === "object") {
    // 权限请求（摄像头/麦克风/通知/定位/媒体等）全部拒绝。
    if (typeof session.setPermissionRequestHandler === "function") {
      session.setPermissionRequestHandler((_wc, _permission, callback) => {
        denials.permissions += 1;
        callback(false);
      });
    }
    if (typeof session.setPermissionCheckHandler === "function") {
      session.setPermissionCheckHandler(() => false);
    }

    // 网络请求拦截：仅放行指向预览文件的 file: 请求；其余（含任何
    // http/https/ws 等）在发出前取消。
    const webRequest = session.webRequest;
    if (webRequest && typeof webRequest.onBeforeRequest === "function") {
      webRequest.onBeforeRequest((details, callback) => {
        const url = details && details.url;
        if (isBlockedUrl(url, allowedFileUrl)) {
          denials.requests += 1;
          callback({ cancel: true });
          return;
        }
        callback({});
      });
    }
  }

  return { denials, isBlockedUrl };
}

module.exports = { applyMiniGamePolicy, isBlockedUrl };
