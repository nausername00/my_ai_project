"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const { applyMiniGamePolicy, isBlockedUrl } = require("./mini-game-policy.cjs");

const ALLOWED = "file:///D:/preview/moling-mini-game.html";

function fakeWebContents() {
  const handlers = {};
  const wc = {
    windowOpenHandler: null,
    on(event, fn) {
      (handlers[event] ||= []).push(fn);
    },
    emit(event, ...args) {
      for (const fn of handlers[event] || []) fn(...args);
    },
    setWindowOpenHandler(fn) {
      this.windowOpenHandler = fn;
    },
  };
  return wc;
}

function fakeSession() {
  const handlers = {};
  return {
    permissionRequestHandler: null,
    permissionCheckHandler: null,
    requestHandlers: [],
    setPermissionRequestHandler(fn) {
      this.permissionRequestHandler = fn;
    },
    setPermissionCheckHandler(fn) {
      this.permissionCheckHandler = fn;
    },
    webRequest: {
      onBeforeRequest(fn) {
        this.requestHandlers.push(fn);
      },
      requestHandlers: [],
    },
    emitPermissionRequest(...args) {
      return this.permissionRequestHandler(...args);
    },
    emitPermissionCheck(...args) {
      return this.permissionCheckHandler(...args);
    },
    emitRequest(details) {
      let result;
      this.webRequest.requestHandlers.forEach((fn) => {
        fn(details, (decision) => {
          result = decision;
        });
      });
      return result;
    },
  };
}

test("isBlockedUrl blocks every non-allowed scheme and path", () => {
  // 允许的目标文件本身
  assert.equal(isBlockedUrl(ALLOWED, ALLOWED), false);
  // 同一文件带查询 / 哈希仍放行（本地资源语义）
  assert.equal(isBlockedUrl(`${ALLOWED}?v=1`, ALLOWED), false);
  assert.equal(isBlockedUrl(`${ALLOWED}#top`, ALLOWED), false);

  // 网络协议全部拦截
  assert.equal(isBlockedUrl("http://example.com/x", ALLOWED), true);
  assert.equal(isBlockedUrl("https://example.com/x", ALLOWED), true);
  assert.equal(isBlockedUrl("ws://example.com", ALLOWED), true);
  assert.equal(isBlockedUrl("wss://example.com", ALLOWED), true);

  // 其它本地文件与目录一律拦截
  assert.equal(isBlockedUrl("file:///D:/preview/other.html", ALLOWED), true);
  assert.equal(isBlockedUrl("file:///C:/Windows/win.ini", ALLOWED), true);
  // 大小写/解码差异也拦截（路径不同）
  assert.equal(
    isBlockedUrl("file:///D:/preview/moling-mini-game.html%2F..%2F..%2Fetc", ALLOWED),
    true,
  );

  // 数据 / blob / javascript 等一律拦截
  assert.equal(isBlockedUrl("data:text/html,<script>1</script>", ALLOWED), true);
  assert.equal(isBlockedUrl("blob:file:///guid", ALLOWED), true);
  assert.equal(isBlockedUrl("javascript:alert(1)", ALLOWED), true);

  // 空与无法解析的输入拦截
  assert.equal(isBlockedUrl("", ALLOWED), true);
  assert.equal(isBlockedUrl("not a url", ALLOWED), true);
  assert.equal(isBlockedUrl(null, ALLOWED), true);
});

test("applyMiniGamePolicy denies popups, navigation, downloads, permissions and network", () => {
  const wc = fakeWebContents();
  const ses = fakeSession();
  const { denials } = applyMiniGamePolicy({
    webContents: wc,
    session: ses,
    allowedFileUrl: ALLOWED,
  });

  // 弹窗：一律 deny
  assert.equal(typeof wc.windowOpenHandler, "function");
  assert.equal(wc.windowOpenHandler({ url: "https://evil.example" }).action, "deny");
  assert.equal(denials.popups, 1);

  // 导航：非允许地址 preventDefault，允许地址放行
  let prevented = 0;
  const fakeEvent = { preventDefault() { prevented += 1; } };
  wc.emit("will-navigate", fakeEvent, "https://evil.example");
  assert.equal(prevented, 1);
  assert.equal(denials.navigations, 1);
  wc.emit("will-navigate", fakeEvent, ALLOWED);
  assert.equal(prevented, 1, "允许的导航不应被阻止");
  assert.equal(denials.navigations, 1);

  // 下载：一律 preventDefault
  let downloadPrevented = 0;
  const downloadEvent = { preventDefault() { downloadPrevented += 1; } };
  wc.emit("will-download", downloadEvent, { url: "https://evil.example/x.exe" });
  assert.equal(downloadPrevented, 1);
  assert.equal(denials.downloads, 1);

  // 权限请求：一律拒绝
  assert.equal(typeof ses.permissionRequestHandler, "function");
  let permissionGranted = null;
  ses.emitPermissionRequest({}, "media", (granted) => {
    permissionGranted = granted;
  });
  assert.equal(permissionGranted, false);
  assert.equal(denials.permissions, 1);
  assert.equal(typeof ses.permissionCheckHandler, "function");
  assert.equal(ses.emitPermissionCheck({}, "notifications"), false);

  // 网络请求：非允许请求 cancel，允许请求放行
  assert.equal(ses.emitRequest({ url: "https://evil.example/x.js" }).cancel, true);
  assert.equal(denials.requests, 1);
  assert.equal(ses.emitRequest({ url: ALLOWED }).cancel, undefined);
  assert.equal(denials.requests, 1, "允许的本地文件请求不应计入拦截");
});

test("applyMiniGamePolicy requires a webContents and an allowed url", () => {
  assert.throws(() => applyMiniGamePolicy({ session: {} }), TypeError);
  assert.throws(
    () => applyMiniGamePolicy({ webContents: fakeWebContents() }),
    TypeError,
  );
});

test("applyMiniGamePolicy tolerates a missing session", () => {
  const wc = fakeWebContents();
  const { denials } = applyMiniGamePolicy({ webContents: wc, allowedFileUrl: ALLOWED });
  assert.equal(typeof wc.windowOpenHandler, "function");
  assert.equal(denials.permissions, 0);
});
