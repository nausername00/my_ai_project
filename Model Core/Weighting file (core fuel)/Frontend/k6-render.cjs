// K6 演出渲染驱动（主进程）：加载 K6 舞台 -> 时间线渲染 -> 透明 PNG 序列 -> ffmpeg 合成视频
// 用法: electron k6-render.cjs --timeline <json> --out <目录> --bg "#rrggbb"|transparent [--side left|right]
const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { registerMolingScheme, registerMolingProtocol } = require("./live2d-protocol.cjs");
const ffmpeg = require("ffmpeg-static");

const OUT_LOG = path.join(__dirname, "k6_render_out.txt");
const log = (s) => {
  try { fs.appendFileSync(OUT_LOG, s + "\n"); } catch {}
};

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) {
    if (argv[i].startsWith("--")) args[argv[i].slice(2)] = argv[i + 1];
  }
  return args;
}
const opts = parseArgs(process.argv);
const timelinePath = opts.timeline;
const outDir = opts.out;
const bg = opts.bg === "transparent" ? null : (opts.bg || "#111318");
const side = opts.side || "right";
const PROJ_ROOT = "D:\\Coding\\code program\\test\\This is mine\\my_ai_project\\Model Core\\Weighting file (core fuel)";

log("[k6-start] " + new Date().toISOString() + " bg=" + String(bg) + " side=" + side);
setTimeout(() => { log("[k6-timeout]"); app.exit(2); }, 180000);

if (!timelinePath || !outDir || !fs.existsSync(timelinePath)) {
  log("[arg-err] need --timeline <json> --out <dir>");
  app.exit(3);
}
const timeline = JSON.parse(fs.readFileSync(timelinePath, "utf8"));
const fps = timeline.fps || 10;
const framesDir = path.join(outDir, "frames");
fs.mkdirSync(framesDir, { recursive: true });
log("[frames-dir] " + framesDir);

app.commandLine.appendSwitch("disable-gpu-shader-disk-cache");
registerMolingScheme();

app.whenReady().then(async () => {
  try {
    await registerMolingProtocol(app, PROJ_ROOT, __dirname);
  } catch (e) {
    log("[proto-err] " + e.message);
    app.exit(4);
    return;
  }
  const win = new BrowserWindow({
    width: timeline.width || 1280,
    height: timeline.height || 720,
    show: false,
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, "k6-preload.cjs"),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      offscreen: false,
    },
  });
  win.webContents.on("console-message", (_e, level, message) => {
    if (level >= 3 || /k6|Live2D|PIXI|error/i.test(String(message))) {
      log("[console:" + level + "] " + String(message).slice(0, 300));
    }
  });
  win.webContents.on("did-fail-load", (_e, code, desc) => log("[fail-load] " + code + " " + desc));
  try {
    await win.loadURL("moling://local/k6-stage.html");
    log("[stage-loaded]");
  } catch (e) {
    log("[load-err] " + e.message);
    app.exit(5);
    return;
  }
  await new Promise((r) => setTimeout(r, 2000));
  ipcMain.handle("k6:save-frame", (e, payload) => {
    const buf = Buffer.from(payload.dataURL.split(",")[1], "base64");
    fs.writeFileSync(path.join(framesDir, payload.name), buf);
    return { ok: true };
  });
  ipcMain.handle("k6:progress", () => ({ ok: true }));
  ipcMain.handle("k6:error", (e, msg) => log("[render-error] " + msg));
  try {
    const info = await win.webContents.executeJavaScript(
      `window.runRender(${JSON.stringify(timeline)}, {
        side: ${JSON.stringify(side)},
        background: ${JSON.stringify(bg)},
      })`,
      true,
    );
    log("[render-done] " + JSON.stringify(info));
  } catch (e) {
    log("[render-err] " + e.message);
    app.exit(6);
    return;
  }
  // 合成视频（仅非透明版；透明版保留 PNG 序列作为透明素材）
  if (bg) {
    const mp4 = path.join(outDir, "video.mp4");
    const args = [
      "-y",
      "-framerate", String(fps),
      "-i", path.join(framesDir, "frame_%05d.png"),
      "-c:v", "libx264", "-pix_fmt", "yuv420p",
      "-movflags", "+faststart",
      mp4,
    ];
    try {
      execFileSync(ffmpeg, args, { stdio: ["ignore", "pipe", "pipe"] });
      log("[ffmpeg-ok] " + mp4);
    } catch (e) {
      log("[ffmpeg-err] " + String(e.stderr || e.message).slice(0, 800));
      app.exit(7);
      return;
    }
  } else {
    log("[transparent-mode] 保留透明 PNG 序列，不合成视频");
  }
  log("[k6-done]");
  app.exit(0);
});
app.on("window-all-closed", () => {});
