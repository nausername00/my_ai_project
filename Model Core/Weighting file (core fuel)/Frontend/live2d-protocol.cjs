// moling:// 同源协议共享模块：服务 Frontend 页面资源与 Character 模型资源。
// Chromium 的 CORS 只允许 chrome/data/http/https 等 scheme 跨源，自定义 scheme 必须同源才能 fetch，
// 因此主窗口页面改为由本协议加载（moling://local/index.html），模型走 moling://local/model/<rel>。
// 被 main.cjs 与 live2d-smoke.cjs 复用。
"use strict";

const path = require("node:path");
const { pathToFileURL } = require("node:url");

function resolveCharacterRoot(app, projectRoot) {
  return app.isPackaged
    ? path.join(app.getPath("userData"), "Character")
    : path.join(projectRoot, "Character");
}

function resolveFrontendRoot(__dirname) {
  return path.resolve(__dirname);
}

// 必须在 app ready 之前调用（特权 scheme 注册）。
function registerMolingScheme() {
  const { protocol } = require("electron");
  protocol.registerSchemesAsPrivileged([
    {
      scheme: "moling",
      privileges: {
        standard: true,
        secure: true,
        supportFetchAPI: true,
        stream: true,
        corsEnabled: true,
        bypassCSP: false,
      },
    },
  ]);
}

const mimeByExt = {
  ".json": "application/json",
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".cjs": "application/javascript; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".moc3": "application/octet-stream",
  ".motion3.json": "application/json",
  ".exp3.json": "application/json",
  ".physics3.json": "application/json",
  ".cdi3.json": "application/json",
  ".model3.json": "application/json",
};

// 在 app ready 之后调用：注册协议处理器。frontendRoot 传 __dirname。
async function registerMolingProtocol(app, projectRoot, frontendRoot) {
  const { protocol, net } = require("electron");
  const charRoot = path.resolve(resolveCharacterRoot(app, projectRoot));
  const feRoot = path.resolve(resolveFrontendRoot(frontendRoot));
  const debugLog =
    process.env.MOLING_PROTO_DEBUG &&
    path.join(frontendRoot, "k3_proto_debug.log");
  const appendLog = (line) => {
    if (debugLog) {
      require("node:fs").appendFileSync(
        debugLog,
        `[${new Date().toISOString()}] ${line}\n`,
      );
    }
  };

  // 映射 URL 到本地文件：/model/<rel> -> Character 根；其余 -> Frontend 根。
  // 返回 { root, rel } 或 null（非法）。
  function mapRequest(url) {
    if (url.host !== "local") return null;
    const rawPath = decodeURIComponent(url.pathname.replace(/^\//, ""));
    if (rawPath === "model" || rawPath.startsWith("model/")) {
      const rel = rawPath.slice("model".length).replace(/^\//, "");
      return { root: charRoot, rel };
    }
    return { root: feRoot, rel: rawPath };
  }

  protocol.handle("moling", async (request) => {
    try {
      const url = new URL(request.url);
      const mapped = mapRequest(url);
      if (!mapped) {
        appendLog(`bad url ${request.url}`);
        return new Response("not found", { status: 404 });
      }
      const target = path.resolve(mapped.root, mapped.rel);
      if (
        target !== mapped.root &&
        !target.startsWith(mapped.root + path.sep)
      ) {
        appendLog(`traversal blocked ${request.url} -> ${target}`);
        return new Response("forbidden", { status: 403 });
      }
      const fileUrl = pathToFileURL(target).toString();
      let resp;
      try {
        resp = await net.fetch(fileUrl);
      } catch (fetchError) {
        appendLog(`net.fetch threw for ${request.url}: ${fetchError.message}`);
        return new Response("not found", { status: 404 });
      }
      if (!resp.ok) {
        appendLog(`net.fetch !ok ${request.url} status=${resp.status}`);
        return new Response("not found", { status: 404 });
      }
      const data = await resp.arrayBuffer();
      const ext = path.extname(target).toLowerCase();
      const contentType =
        mimeByExt[ext] || "application/octet-stream";
      appendLog(`OK ${request.url} -> ${fileUrl} bytes=${data.byteLength} type=${contentType}`);
      return new Response(data, {
        status: 200,
        headers: {
          "Content-Type": contentType,
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "no-cache",
          "Content-Length": String(data.byteLength),
        },
      });
    } catch (error) {
      appendLog(`protocol error ${request.url}: ${error.message}`);
      console.error("moling protocol error:", error);
      return new Response("internal error", { status: 500 });
    }
  });
}

module.exports = {
  resolveCharacterRoot,
  registerMolingScheme,
  registerMolingProtocol,
};
