const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  nativeImage,
  session,
  shell,
} = require("electron");
const { randomBytes, randomUUID } = require("node:crypto");
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs/promises");
const net = require("node:net");
const path = require("node:path");

const { createOllamaSetup } = require("./ollama-setup.cjs");
const {
  MAX_VOICE_SAMPLE_BYTES,
  VoiceResourceStore,
  getVoiceAudioType,
  validateVoiceMetadata,
} = require("./voice-resources.cjs");

const projectRoot = path.resolve(__dirname, "..");
const toolApprovalCapability = randomBytes(32).toString("hex");
const agentWorkspaceRoot =
  process.env.MOLING_WORKSPACE_ROOT ||
  (app.isPackaged ? "" : projectRoot);
const serviceEntry = path.join(projectRoot, "Source code engine", "app.py");
const defaultModelName = "qwen2.5:3b";
const ollamaBaseUrl = process.env.OLLAMA_URL || "http://127.0.0.1:11434";
const ollamaModelName = process.env.OLLAMA_MODEL || defaultModelName;
const ollamaSetup = createOllamaSetup(ollamaBaseUrl, ollamaModelName);
const avatarMimeTypes = new Map([
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".webp", "image/webp"],
]);
const maxAvatarBytes = 8 * 1024 * 1024;
const maxAvatarPixels = 16_000_000;
const modelAssetExtensions = new Set([
  ".bmp", ".json", ".jpeg", ".jpg", ".moc3", ".motion3.json", ".mp3",
  ".pmd", ".pmx", ".png", ".tga", ".vmd", ".vrm", ".wav", ".webp",
]);
const maxModelAssetBytes = 250 * 1024 * 1024;
const maxModelBundleBytes = 500 * 1024 * 1024;
let characterAssetDir;
let voiceResourceStore;
let backendProcess;
let apiBaseUrl;
let mainWindow;
let floatingWindow;
let floatingWindowReady = false;
let notificationPollTimer;
const pendingNotifications = [];
const notificationActions = new Map();
const seenNotificationIds = new Set();

function initializeDataPaths() {
  const characterRoot = app.isPackaged
    ? path.join(app.getPath("userData"), "Character")
    : path.join(projectRoot, "Character");
  characterAssetDir = path.resolve(
    process.env.CHARACTER_ASSET_DIR || path.join(characterRoot, "assets"),
  );
  voiceResourceStore = new VoiceResourceStore(
    process.env.VOICE_RESOURCE_DIR ||
      path.join(app.getPath("userData"), "Character", "voice-resources"),
  );
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close((error) => {
        if (error) reject(error);
        else resolve(address.port);
      });
    });
  });
}

function resolvePython() {
  const executable = process.platform === "win32" ? "py" : "python3";
  const args =
    process.platform === "win32"
      ? ["-3", "-c", "import sys; print(sys.executable)"]
      : ["-c", "import sys; print(sys.executable)"];
  return execFileSync(executable, args, { encoding: "utf8" }).trim();
}

async function startBackend() {
  const port = await findFreePort();
  apiBaseUrl = `http://127.0.0.1:${port}`;
  const backendExecutable = app.isPackaged
    ? path.join(process.resourcesPath, "backend", "MolingBackend.exe")
    : resolvePython();
  if (app.isPackaged) {
    const backendStat = await fs.stat(backendExecutable).catch(() => null);
    if (!backendStat?.isFile()) {
      throw new Error("安装包缺少本地服务程序，请重新安装墨灵。");
    }
  }
  const backendArguments = app.isPackaged
    ? ["--host", "127.0.0.1", "--port", String(port)]
    : [serviceEntry, "--host", "127.0.0.1", "--port", String(port)];
  const backendEnvironment = {
    ...process.env,
    MODEL_BACKEND: process.env.MODEL_BACKEND || "ollama",
    OLLAMA_MODEL: ollamaModelName,
    OLLAMA_URL: ollamaBaseUrl,
    MOLING_TOOL_CAPABILITY: agentWorkspaceRoot ? toolApprovalCapability : "",
    WORKSPACE_ROOT: agentWorkspaceRoot || app.getPath("userData"),
  };
  if (app.isPackaged) {
    const characterRoot = path.join(app.getPath("userData"), "Character");
    backendEnvironment.CHARACTER_CARD_PATH =
      process.env.CHARACTER_CARD_PATH ||
      path.join(characterRoot, "characters", "default.json");
    backendEnvironment.CHARACTER_MEMORY_PATH =
      process.env.CHARACTER_MEMORY_PATH || path.join(characterRoot, "memory.json");
    backendEnvironment.CHARACTER_ASSET_DIR = characterAssetDir;
    backendEnvironment.CHARACTER_PRIVACY_PATH =
      process.env.CHARACTER_PRIVACY_PATH || path.join(characterRoot, "privacy.json");
    backendEnvironment.CHARACTER_AFFECT_PATH =
      process.env.CHARACTER_AFFECT_PATH || path.join(characterRoot, "affect.json");
    backendEnvironment.PIPER_VOICE_PATH =
      process.env.PIPER_VOICE_PATH ||
      path.join(
        process.resourcesPath,
        "Character",
        "assets",
        "voices",
        "zh_CN-huayan-medium.onnx",
      );
  }
  backendProcess = spawn(
    backendExecutable,
    backendArguments,
    {
      cwd: app.isPackaged ? app.getPath("userData") : projectRoot,
      windowsHide: true,
      stdio: "ignore",
      env: backendEnvironment,
    },
  );
  backendProcess.once("error", (error) => {
    console.error("Could not start the Python service:", error);
  });

  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (backendProcess.exitCode !== null) {
      throw new Error(`Python service exited with code ${backendProcess.exitCode}`);
    }
    try {
      const response = await fetch(`${apiBaseUrl}/health`, {
        signal: AbortSignal.timeout(1000),
      });
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
  }
  throw new Error("Python service did not become ready within 12 seconds");
}

async function callApi(route, method = "GET", body, extraHeaders = {}) {
  const staticRoutes = {
    "/health": ["GET"],
    "/v1/speech/status": ["GET"],
    "/v1/character": ["GET", "POST"],
    "/v1/characters": ["GET", "POST"],
    "/v1/characters/active": ["POST"],
    "/v1/generate": ["POST"],
    "/v1/explore/propose": ["POST"],
    "/v1/explore/run": ["POST"],
    "/v1/explore/react": ["POST"],
    "/v1/explore/save": ["POST"],
    "/v1/explore/works": ["GET"],
    "/v1/explore/work": ["POST"],
    "/v1/translate": ["POST"],
    "/v1/agent/reflect": ["POST"],
    "/v1/agent/collaborate": ["POST"],
    "/v1/agent/plan": ["POST"],
    "/v1/agent/tools": ["GET"],
    "/v1/agent/roles": ["GET"],
    "/v1/social/status": ["GET"],
    "/v1/social/partners": ["GET"],
    "/v1/social/collaborate": ["POST"],
    "/v1/agent/tool/execute": ["POST"],
    "/v1/agent/tool/verify": ["POST"],
    "/v1/memory": ["GET", "POST"],
    "/v1/memory/export": ["GET"],
    "/v1/memory/import": ["POST"],
    "/v1/privacy": ["GET", "POST"],
    "/v1/affect": ["GET", "POST"],
    "/v1/engine/list": ["GET"],
    "/v1/engine/switch": ["POST"],
    "/v1/notify": ["GET", "POST"],
  };
  const routePath = new URL(route, "http://127.0.0.1").pathname;
  const allowedMethods =
    staticRoutes[routePath] ||
    (/^\/v1\/memory\/[a-f0-9-]+$/i.test(routePath) ? ["PUT", "DELETE"] : []);
  if (!allowedMethods.includes(method)) {
    throw new Error("Unsupported API route");
  }
  const response = await fetch(`${apiBaseUrl}${route}`, {
    method,
    headers: body
      ? { "Content-Type": "application/json", ...extraHeaders }
      : extraHeaders,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(180_000),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Local service returned HTTP ${response.status}`);
  }
  return data;
}

async function transcribeAudio(audio, contentType) {
  const normalizedContentType =
    typeof contentType === "string"
      ? contentType.split(";", 1)[0].trim().toLowerCase()
      : "";
  const contentTypes = new Set([
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/wav",
    "audio/mpeg",
  ]);
  if (!(audio instanceof Uint8Array) || audio.byteLength < 1) {
    throw new Error("录音数据无效");
  }
  if (audio.byteLength > 25_000_000) {
    throw new Error("录音不能超过 25 MB");
  }
  if (!contentTypes.has(normalizedContentType)) {
    throw new Error("不支持此录音格式");
  }
  const response = await fetch(`${apiBaseUrl}/v1/transcribe`, {
    method: "POST",
    headers: { "Content-Type": normalizedContentType },
    body: Buffer.from(audio),
    signal: AbortSignal.timeout(180_000),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `本地服务返回 HTTP ${response.status}`);
  }
  return data;
}

async function synthesizeSpeech(text) {
  if (typeof text !== "string" || text.length > 2000) {
    throw new Error("语音文本无效或超过 2000 个字符");
  }
  const response = await fetch(`${apiBaseUrl}/v1/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(180_000),
  });
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.error || `本地服务返回 HTTP ${response.status}`);
  }
  const contentType = response.headers
    .get("content-type")
    ?.split(";", 1)[0]
    .trim()
    .toLowerCase();
  if (contentType !== "audio/wav") {
    throw new Error(`本地语音服务返回了不支持的音频类型：${contentType || "未知"}`);
  }
  const audio = new Uint8Array(await response.arrayBuffer());
  if (
    audio.byteLength < 44 ||
    audio[0] !== 0x52 ||
    audio[1] !== 0x49 ||
    audio[2] !== 0x46 ||
    audio[3] !== 0x46 ||
    audio[8] !== 0x57 ||
    audio[9] !== 0x41 ||
    audio[10] !== 0x56 ||
    audio[11] !== 0x45
  ) {
    throw new Error("本地语音服务返回的 WAV 数据无效");
  }
  return audio;
}

function getAvatarMimeType(fileName, bytes) {
  const extension = path.extname(fileName).toLowerCase();
  const mimeType = avatarMimeTypes.get(extension);
  const isPng =
    extension === ".png" &&
    bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const isJpeg =
    [".jpg", ".jpeg"].includes(extension) &&
    bytes[0] === 0xff &&
    bytes[1] === 0xd8 &&
    bytes[2] === 0xff;
  const isWebp =
    extension === ".webp" &&
    bytes.toString("ascii", 0, 4) === "RIFF" &&
    bytes.toString("ascii", 8, 12) === "WEBP";
  if (!mimeType || !(isPng || isJpeg || isWebp)) {
    throw new Error("立绘必须是有效的 PNG、JPEG 或 WebP 图片");
  }
  const { width, height } = nativeImage.createFromBuffer(bytes).getSize();
  if (!width || !height || width * height > maxAvatarPixels) {
    throw new Error("立绘尺寸无效或超过 1600 万像素");
  }
  return mimeType;
}

async function chooseAvatar() {
  const result = await dialog.showOpenDialog(
    BrowserWindow.getFocusedWindow() || undefined,
    {
      properties: ["openFile"],
      filters: [{ name: "角色立绘", extensions: ["png", "jpg", "jpeg", "webp"] }],
    },
  );
  if (result.canceled || !result.filePaths[0]) return null;

  const source = await fs.readFile(result.filePaths[0]);
  if (source.byteLength === 0 || source.byteLength > maxAvatarBytes) {
    throw new Error("立绘文件必须大于 0 且不超过 8 MB");
  }
  const extension = path.extname(result.filePaths[0]).toLowerCase();
  const mimeType = getAvatarMimeType(result.filePaths[0], source);
  const fileName = `avatar-${randomUUID()}${extension}`;
  await fs.mkdir(characterAssetDir, { recursive: true });
  await fs.writeFile(path.join(characterAssetDir, fileName), source, { flag: "wx" });
  return {
    name: fileName,
    dataUrl: `data:${mimeType};base64,${source.toString("base64")}`,
  };
}

async function importModelAssets() {
  const result = await dialog.showOpenDialog(
    BrowserWindow.getFocusedWindow() || undefined,
    {
      properties: ["openFile", "multiSelections"],
      filters: [{
        name: "角色模型与资源",
        extensions: [
          "vrm", "pmx", "pmd", "moc3", "json", "vmd", "png", "jpg",
          "jpeg", "webp", "bmp", "tga", "wav", "mp3",
        ],
      }],
    },
  );
  if (result.canceled || result.filePaths.length === 0) return [];
  let bundleBytes = 0;
  const imported = [];
  const bundleId = randomUUID();
  const targetDirectory = path.join(characterAssetDir, "models", bundleId);
  await fs.mkdir(targetDirectory, { recursive: true });
  const usedNames = new Set();
  for (const sourcePath of result.filePaths) {
    const extension = path.extname(sourcePath).toLowerCase();
    if (!modelAssetExtensions.has(extension)) {
      throw new Error(`不支持导入此角色资源格式：${extension || "未知格式"}`);
    }
    const stat = await fs.stat(sourcePath);
    if (!stat.isFile() || stat.size < 1 || stat.size > maxModelAssetBytes) {
      throw new Error(`${path.basename(sourcePath)} 必须为有效文件且不超过 250 MB`);
    }
    bundleBytes += stat.size;
    if (bundleBytes > maxModelBundleBytes) {
      throw new Error("一次导入的角色资源不能超过 500 MB");
    }
    const source = await fs.readFile(sourcePath);
    let fileName = path.basename(sourcePath);
    let suffix = 1;
    while (usedNames.has(fileName.toLowerCase())) {
      const parsed = path.parse(path.basename(sourcePath));
      fileName = `${parsed.name}-${suffix}${parsed.ext}`;
      suffix += 1;
    }
    usedNames.add(fileName.toLowerCase());
    await fs.writeFile(path.join(targetDirectory, fileName), source, { flag: "wx" });
    imported.push({
      name: path.posix.join("models", bundleId, fileName),
      originalName: path.basename(sourcePath),
      bytes: stat.size,
    });
  }
  return imported;
}

async function chooseVoiceReference() {
  const result = await dialog.showOpenDialog(
    BrowserWindow.getFocusedWindow() || undefined,
    {
      properties: ["openFile"],
      filters: [{ name: "声音参考样本", extensions: ["wav", "mp3"] }],
    },
  );
  if (result.canceled || !result.filePaths[0]) return null;
  const originalName = path.basename(result.filePaths[0]);
  const extension = path.extname(originalName).toLowerCase();
  const stat = await fs.stat(result.filePaths[0]);
  if (!stat.isFile() || stat.size < 1 || stat.size > MAX_VOICE_SAMPLE_BYTES) {
    throw new Error("声音样本必须为有效文件且不超过 25 MB");
  }
  const bytes = await fs.readFile(result.filePaths[0]);
  const contentType = getVoiceAudioType(extension, bytes);
  return {
    originalName,
    contentType,
    bytes: new Uint8Array(bytes),
  };
}

async function registerVoiceReference(metadata, sample) {
  const validatedMetadata = validateVoiceMetadata(
    metadata?.name,
    metadata?.language,
  );
  if (
    !sample ||
    typeof sample.originalName !== "string" ||
    !(sample.bytes instanceof Uint8Array)
  ) {
    throw new Error("请先选择有效的声音样本");
  }
  return voiceResourceStore.register({
    ...validatedMetadata,
    originalName: sample.originalName,
    bytes: sample.bytes,
  });
}

async function deleteVoiceReference(id) {
  const listing = await callApi("/v1/characters");
  const inUse = listing.characters
    .filter((item) => item.character.voice === `reference:${id}`)
    .map((item) => item.character.nickname);
  if (inUse.length) {
    throw new Error(
      `此参考声线仍被以下角色卡关联：${inUse.join("、")}。请先为这些角色选择其他声线并保存。`,
    );
  }
  return voiceResourceStore.remove(id);
}

async function readAvatar(fileName) {
  if (
    typeof fileName !== "string" ||
    fileName.length > 100 ||
    path.basename(fileName) !== fileName ||
    fileName.includes("/") ||
    fileName.includes("\\")
  ) {
    throw new Error("立绘文件名无效");
  }
  const bytes = await fs.readFile(path.join(characterAssetDir, fileName));
  if (bytes.byteLength === 0 || bytes.byteLength > maxAvatarBytes) {
    throw new Error("立绘文件为空或超过 8 MB");
  }
  const mimeType = getAvatarMimeType(fileName, bytes);
  return `data:${mimeType};base64,${bytes.toString("base64")}`;
}

async function readModelPreview(assetName) {
  if (
    typeof assetName !== "string" ||
    assetName.length > 240 ||
    !/^models\/[0-9a-f-]{36}\/[^/\\]+$/i.test(assetName)
  ) {
    throw new Error("角色模型资源路径无效");
  }
  const fileName = path.basename(assetName);
  const extension = path.extname(fileName).toLowerCase();
  if (!avatarMimeTypes.has(extension)) {
    throw new Error("只有 PNG、JPEG 和 WebP 资源可用作静态预览");
  }
  const assetPath = path.resolve(characterAssetDir, ...assetName.split("/"));
  const modelRoot = path.resolve(characterAssetDir, "models");
  if (!assetPath.startsWith(`${modelRoot}${path.sep}`)) {
    throw new Error("角色模型资源路径无效");
  }
  const bytes = await fs.readFile(assetPath);
  if (bytes.byteLength === 0 || bytes.byteLength > maxAvatarBytes) {
    throw new Error("预览图片为空或超过 8 MB");
  }
  const mimeType = getAvatarMimeType(fileName, bytes);
  return `data:${mimeType};base64,${bytes.toString("base64")}`;
}

function registerIpcHandlers() {
  ipcMain.handle("companion:health", () => callApi("/health"));
  ipcMain.handle("companion:model-status", () => ollamaSetup.getModelStatus());
  ipcMain.handle("companion:pull-model", async () => {
    const confirmation = await dialog.showMessageBox(
      BrowserWindow.getFocusedWindow() || undefined,
      {
        type: "warning",
        buttons: ["下载模型", "取消"],
        defaultId: 1,
        cancelId: 1,
        title: "下载墨灵本地模型",
        message: `是否从 Ollama 下载 ${ollamaModelName} 到本机？`,
        detail:
          "模型文件可能较大，会写入 Ollama 管理的本地模型目录。下载只会在你确认后开始。",
      },
    );
    if (confirmation.response !== 0) return { canceled: true };
    const status = await ollamaSetup.pullModel((progress) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("companion:model-progress", progress);
      }
    });
    return { canceled: false, ...status };
  });
  ipcMain.handle("companion:open-ollama-download", () =>
    shell.openExternal("https://ollama.com/download/windows"),
  );
  ipcMain.handle("companion:speech-status", () => callApi("/v1/speech/status"));
  ipcMain.handle("companion:transcribe", (_event, audio, contentType) =>
    transcribeAudio(audio, contentType),
  );
  ipcMain.handle("companion:synthesize", (_event, text) =>
    synthesizeSpeech(text),
  );
  ipcMain.handle("companion:get-character", () => callApi("/v1/character"));
  ipcMain.handle("companion:list-characters", () => callApi("/v1/characters"));
  ipcMain.handle("companion:create-character", (_event, card) =>
    callApi("/v1/characters", "POST", card),
  );
  ipcMain.handle("companion:select-character", async (_event, characterId) => {
    const result = await callApi("/v1/characters/active", "POST", {
      id: characterId,
    });
    pushCharacterToFloating();
    return result;
  });
  ipcMain.handle("companion:save-character", async (_event, card) => {
    const result = await callApi("/v1/character", "POST", card);
    pushCharacterToFloating();
    return result;
  });
  ipcMain.handle("companion:choose-avatar", chooseAvatar);
  ipcMain.handle("companion:get-avatar", (_event, fileName) => readAvatar(fileName));
  ipcMain.handle("companion:import-model-assets", importModelAssets);
  ipcMain.handle("companion:get-model-preview", (_event, assetName) =>
    readModelPreview(assetName),
  );
  ipcMain.handle("companion:list-voice-resources", () =>
    voiceResourceStore.list(),
  );
  ipcMain.handle("companion:choose-voice-reference", chooseVoiceReference);
  ipcMain.handle(
    "companion:register-voice-reference",
    (_event, metadata, sample) => registerVoiceReference(metadata, sample),
  );
  ipcMain.handle("companion:get-voice-reference", (_event, id) =>
    voiceResourceStore.readSample(id),
  );
  ipcMain.handle("companion:delete-voice-reference", (_event, id) =>
    deleteVoiceReference(id),
  );
  ipcMain.handle("companion:generate", (_event, prompt, history) =>
    callApi("/v1/generate", "POST", { prompt, max_tokens: 128, history }),
  );
  ipcMain.handle("companion:discover-file", async () => {
    const picked = await dialog.showOpenDialog({
      title: "分享一个文件给墨灵",
      buttonLabel: "分享",
      properties: ["openFile"],
      filters: [
        {
          name: "文本与代码",
          extensions: ["txt", "md", "json", "py", "js", "ts", "html", "css", "csv", "log", "xml", "yaml", "yml"],
        },
        { name: "图片", extensions: ["png", "jpg", "jpeg", "webp", "gif", "bmp"] },
        { name: "所有文件", extensions: ["*"] },
      ],
    });
    if (picked.canceled || !picked.filePaths.length) {
      return { canceled: true };
    }
    const filePath = picked.filePaths[0];
    const name = path.basename(filePath);
    const ext = path.extname(filePath).toLowerCase();
    const imageExts = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]);
    const codeExts = new Set([".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".xml", ".sql"]);
    const stats = await fs.stat(filePath);
    let kind = "other";
    let excerpt = "";
    if (imageExts.has(ext)) {
      kind = "image";
    } else {
      kind = codeExts.has(ext) ? "code" : ["txt", "md", "csv", "log"].includes(ext) ? "text" : "other";
      if (stats.size <= 256 * 1024) {
        try {
          excerpt = (await fs.readFile(filePath, "utf-8")).slice(0, 2000);
        } catch {
          excerpt = "";
        }
      }
    }
    const response = await callApi("/v1/discover/file", "POST", {
      name,
      kind,
      excerpt,
      approved: true,
    });
    return { canceled: false, name, kind, size: stats.size, ...response };
  });
  ipcMain.handle("companion:discover-context", async () => {
    const win =
      BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
    if (!win) return { canceled: true };
    let pageText = "";
    try {
      pageText = await win.webContents.executeJavaScript(
        `(() => { const t = document.title || ""; const b = (document.body && document.body.innerText || "").slice(0, 2000); return (t + "\\n" + b).trim(); })()`,
      );
    } catch {
      pageText = "";
    }
    const response = await callApi("/v1/discover/context", "POST", {
      kind: "webpage",
      context: pageText || "（未能读取到可见文本）",
      approved: true,
    });
    return { canceled: false, ...response };
  });
  ipcMain.handle("companion:partners-status", () =>
    callApi("/v1/partners/status"),
  );
  ipcMain.handle("companion:partners-evaluate", (_event, scope) =>
    callApi("/v1/partners/evaluate", "POST", { scope }),
  );
  ipcMain.handle("companion:explore-run", (_event, payload) =>
    callApi("/v1/explore/run", "POST", payload),
  );
  ipcMain.handle("companion:explore-react", (_event, payload) =>
    callApi("/v1/explore/react", "POST", payload),
  );
  ipcMain.handle("companion:explore-save", (_event, payload) =>
    callApi("/v1/explore/save", "POST", payload),
  );
  ipcMain.handle("companion:explore-works", () => callApi("/v1/explore/works"));
  ipcMain.handle("companion:explore-work", (_event, payload) =>
    callApi("/v1/explore/work", "POST", payload),
  );
  ipcMain.handle("companion:translate", (_event, request) =>
    callApi("/v1/translate", "POST", request),
  );
  ipcMain.handle("companion:reflect-agent", (_event, characterId, history) =>
    callApi("/v1/agent/reflect", "POST", {
      character_id: characterId,
      history,
    }),
  );
  ipcMain.handle("companion:collaborate-agents", (_event, task, roles) =>
    callApi("/v1/agent/collaborate", "POST", { task, roles }),
  );
  ipcMain.handle("companion:list-agent-roles", () =>
    callApi("/v1/agent/roles"),
  );
  ipcMain.handle("companion:create-brain-plan", (_event, task, context) =>
    callApi("/v1/agent/plan", "POST", { task, context }),
  );
  ipcMain.handle("companion:list-agent-tools", () => callApi("/v1/agent/tools"));
  ipcMain.handle(
    "companion:execute-agent-tool",
    async (event, tool, arguments_) => {
      const toolLabels = {
        list_project_files: "读取项目文件清单",
        read_project_file: "读取项目文本文件",
        create_project_file: "在项目中创建新文本文件",
      };
      if (!Object.hasOwn(toolLabels, tool)) {
        throw new Error("该工具不在已批准的计划执行白名单中。");
      }
      if (!agentWorkspaceRoot) {
        throw new Error(
          "已安装版本尚未配置项目工作区；请设置 MOLING_WORKSPACE_ROOT 后再使用项目工具。",
        );
      }
      const isCreate = tool === "create_project_file";
      const allowedKeys = isCreate ? ["path", "content"] : ["path"];
      if (
        !arguments_ ||
        typeof arguments_ !== "object" ||
        Array.isArray(arguments_) ||
        Object.keys(arguments_).some((key) => !allowedKeys.includes(key)) ||
        (arguments_.path !== undefined &&
          (typeof arguments_.path !== "string" || arguments_.path.length > 500)) ||
        (tool === "read_project_file" &&
          (typeof arguments_.path !== "string" || !arguments_.path.trim())) ||
        (isCreate &&
          (typeof arguments_.path !== "string" ||
            !arguments_.path.trim() ||
            arguments_.path
              .replace(/\\/g, "/")
              .split("/")
              .some(
                (part) =>
                  !part ||
                  part === "." ||
                  part === ".." ||
                  part.includes(":") ||
                  /[. ]$/.test(part) ||
                  /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part),
              ) ||
            typeof arguments_.content !== "string" ||
            !arguments_.content.trim() ||
            arguments_.content.length > 4000))
      ) {
        throw new Error("工具参数无效或超出长度限制。");
      }
      const workspaceRoot = path.resolve(agentWorkspaceRoot);
      const requestedTarget = isCreate
        ? path.resolve(workspaceRoot, arguments_.path)
        : "";
      const targetRelativePath = isCreate
        ? path.relative(workspaceRoot, requestedTarget)
        : "";
      if (
        isCreate &&
        (!targetRelativePath ||
          targetRelativePath === ".." ||
          targetRelativePath.startsWith(`..${path.sep}`) ||
          path.isAbsolute(targetRelativePath))
      ) {
        throw new Error("新文件路径必须位于已配置项目工作区内。");
      }
      const approvalTitle = isCreate
        ? "批准本次创建新文件？"
        : "批准本次只读工具调用？";
      const approvalMessage = isCreate
        ? "将仅在目标不存在时创建 UTF-8 文本文件；不会覆盖或删除文件。"
        : toolLabels[tool];
      const approvalDetail = isCreate
        ? `完整路径：${requestedTarget}\n\n` +
          `以下为将写入的完整内容：\n--- 内容开始 ---\n${arguments_.content}\n--- 内容结束 ---`
        : `项目目录：${agentWorkspaceRoot}\n参数：${JSON.stringify(arguments_).slice(0, 1000)}\n` +
          "本次只读取项目内文本或文件清单，不会写入、删除、联网或联系他人。";
      const approval = await dialog.showMessageBox(
        BrowserWindow.fromWebContents(event.sender),
        {
          type: "question",
          buttons: ["本次允许", "拒绝"],
          defaultId: 1,
          cancelId: 1,
          title: approvalTitle,
          message: isCreate ? approvalMessage : toolLabels[tool],
          detail: approvalDetail,
          noLink: true,
        },
      );
      if (approval.response !== 0) {
        return { approved: false, observation: null };
      }
      const result = await callApi(
        "/v1/agent/tool/execute",
        "POST",
        { tool, arguments: arguments_ },
        { "X-Moling-Tool-Capability": toolApprovalCapability },
      );
      return { approved: true, ...result };
    },
  );
  ipcMain.handle("companion:verify-agent-tool", (_event, request) =>
    callApi("/v1/agent/tool/verify", "POST", request),
  );
  ipcMain.handle("companion:list-memories", () => callApi("/v1/memory"));
  ipcMain.handle("companion:add-memory", (_event, memory) =>
    callApi("/v1/memory", "POST", memory),
  );
  ipcMain.handle("companion:update-memory", (_event, memoryId, memory) =>
    callApi(`/v1/memory/${memoryId}`, "PUT", memory),
  );
  ipcMain.handle("companion:delete-memory", (_event, memoryId) =>
    callApi(`/v1/memory/${memoryId}`, "DELETE"),
  );
  ipcMain.handle("companion:get-privacy", () => callApi("/v1/privacy"));
  ipcMain.handle("companion:set-privacy", (_event, settings) =>
    callApi("/v1/privacy", "POST", settings),
  );
  ipcMain.handle("companion:get-affect", () => callApi("/v1/affect"));
  ipcMain.handle("companion:set-affect", async (_event, mood) => {
    const result = await callApi("/v1/affect", "POST", { mood });
    pushCharacterToFloating();
    return result;
  });
  ipcMain.handle("companion:export-memories", async () => {
    const result = await dialog.showSaveDialog(BrowserWindow.getFocusedWindow() || undefined, {
      defaultPath: "coco-memories.json",
      filters: [{ name: "JSON", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePath) return { canceled: true };
    const backup = await callApi("/v1/memory/export");
    await fs.writeFile(
      result.filePath,
      `${JSON.stringify(backup, null, 2)}\n`,
      { encoding: "utf8" },
    );
    return {
      canceled: false,
      fileName: path.basename(result.filePath),
      count: backup.memories.length,
    };
  });
  ipcMain.handle("companion:import-memories", async () => {
    const result = await dialog.showOpenDialog(BrowserWindow.getFocusedWindow() || undefined, {
      properties: ["openFile"],
      filters: [{ name: "JSON", extensions: ["json"] }],
    });
    if (result.canceled || !result.filePaths[0]) return { canceled: true };
    const file = await fs.readFile(result.filePaths[0]);
    if (file.byteLength > 1_048_576) {
      throw new Error("记忆备份文件不能超过 1 MB");
    }
    let backup;
    try {
      backup = JSON.parse(file.toString("utf8"));
    } catch (error) {
      throw new Error(`记忆备份不是有效 JSON：${error.message}`);
    }
    const imported = await callApi("/v1/memory/import", "POST", backup);
    return { canceled: false, ...imported };
  });
  ipcMain.handle("companion:notify", (event, notification) => {
    assertWindowSender(event, mainWindow, "Only the main window can create notifications");
    return pushNotification(notification);
  });
  ipcMain.handle("companion:list-social-partners", () =>
    callApi("/v1/social/partners"),
  );
  ipcMain.handle("companion:social-status", () =>
    callApi("/v1/social/status"),
  );
  ipcMain.handle("companion:collaborate-social", (_event, task, roles) =>
    callApi("/v1/social/collaborate", "POST", {
      task,
      roles,
    }),
  );
  ipcMain.handle("companion:list-engines", () => callApi("/v1/engine/list"));
  ipcMain.handle("companion:switch-engine", (_event, backend_id, overrides) =>
    callApi("/v1/engine/switch", "POST", { backend_id, overrides }),
  );
  ipcMain.handle("companion:floating-show", () => {
    if (floatingWindow && !floatingWindow.isDestroyed()) {
      floatingWindow.show();
      return { shown: true };
    }
    createFloatingWindow();
    return { shown: true, restarted: true };
  });
  ipcMain.handle("companion:floating-hide", (event) => {
    assertWindowSender(event, floatingWindow, "Only the floating window can hide itself");
    if (floatingWindow && !floatingWindow.isDestroyed()) {
      floatingWindow.hide();
      return { hidden: true };
    }
    return { hidden: false, reason: "no-window" };
  });
  ipcMain.handle("companion:floating-toggle", () => {
    if (floatingWindow && !floatingWindow.isDestroyed()) {
      if (floatingWindow.isVisible()) {
        floatingWindow.hide();
        return { shown: false };
      }
      floatingWindow.show();
      pushCharacterToFloating();
      return { shown: true };
    }
    createFloatingWindow();
    return { shown: true, restarted: true };
  });
  ipcMain.handle("companion:floating-move", (_event, x, y) => {
    if (floatingWindow && !floatingWindow.isDestroyed() && Number.isFinite(x) && Number.isFinite(y)) {
      floatingWindow.setPosition(Math.round(x), Math.round(y));
      const pos = floatingWindow.getPosition();
      return { moved: true, x: pos[0], y: pos[1] };
    }
    return { moved: false };
  });
  ipcMain.handle("companion:notify-action", (event, notificationId, actionIndex) => {
    assertWindowSender(event, floatingWindow, "Only the floating window can select notification actions");
    const actions = notificationActions.get(notificationId);
    if (!Array.isArray(actions) || !Number.isInteger(actionIndex) || !actions[actionIndex]) {
      throw new Error("Notification action is no longer available");
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("companion:notification-action", {
        notificationId,
        actionIndex,
        action: actions[actionIndex],
      });
      mainWindow.show();
      mainWindow.focus();
    }
    return { accepted: true };
  });
  ipcMain.handle("companion:main-window-show", (event) => {
    assertWindowSender(event, floatingWindow, "Only the floating window can show the main window");
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
      return { shown: true };
    }
    return { shown: false, reason: "no-window" };
  });
}

function assertWindowSender(event, targetWindow, message) {
  if (!targetWindow || targetWindow.isDestroyed() || event.sender !== targetWindow.webContents) {
    throw new Error(message);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1060,
    height: 760,
    minWidth: 820,
    minHeight: 620,
    show: false,
    backgroundColor: "#111318",
    title: "墨小灵 · Moling",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, "index.html"));
}

async function pushCharacterToFloating() {
  if (!floatingWindow || floatingWindow.isDestroyed()) return;
  try {
    const { character } = await callApi("/v1/character");
    let avatarDataUrl = null;
    if (character?.avatar) {
      try {
        avatarDataUrl = await readAvatar(character.avatar);
      } catch {
        avatarDataUrl = null;
      }
    }
    let moodLabel = "";
    try {
      const affect = await callApi("/v1/affect");
      moodLabel = affect?.label || affect?.mood || "";
    } catch {
      moodLabel = "";
    }
    floatingWindow.webContents.send("companion:character-updated", {
      nickname: character?.nickname || "墨灵",
      avatarDataUrl,
      moodLabel,
    });
  } catch {
    // 后端未就绪时静默跳过，浮窗保持初始状态
  }
}

function createFloatingWindow() {
  floatingWindowReady = false;
  floatingWindow = new BrowserWindow({
    width: 360,
    height: 220,
    x: 40,
    y: 40,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    show: false,
    focusable: true,
    webPreferences: {
      preload: path.join(__dirname, "floating-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  floatingWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  floatingWindow.setAlwaysOnTop(true, "screen-saver");
  floatingWindow.loadFile(path.join(__dirname, "floating.html"));
  floatingWindow.once("ready-to-show", () => {
    floatingWindowReady = true;
    floatingWindow.showInactive();
    pushCharacterToFloating();
    while (pendingNotifications.length) {
      const note = pendingNotifications.shift();
      if (floatingWindow && !floatingWindow.isDestroyed()) {
        floatingWindow.webContents.send("companion:notification", note);
      }
    }
  });
  floatingWindow.on("closed", () => {
    floatingWindow = null;
    floatingWindowReady = false;
  });
}

function pushNotification(notification) {
  const actions = Array.isArray(notification?.actions)
    ? notification.actions
        .filter(
          (action) =>
            action &&
            typeof action.label === "string" &&
            action.label.trim().length > 0 &&
            action.label.length <= 80,
        )
        .slice(0, 4)
        .map((action) => ({ label: action.label.trim() }))
    : [];
  const safeNote = {
    id:
      typeof notification?.id === "string" &&
      notification.id.length > 0 &&
      notification.id.length <= 128
        ? notification.id
        : randomUUID(),
    title:
      typeof notification?.title === "string"
        ? notification.title.slice(0, 120)
        : "墨小灵",
    message:
      typeof notification?.message === "string"
        ? notification.message.slice(0, 4000)
        : "",
    level: notification?.level === "info" || notification?.level === "warn" || notification?.level === "error" || notification?.level === "success" ? notification.level : "info",
    actions,
    expires_at: Number.isFinite(notification?.expires_at) ? notification.expires_at : Date.now() + 8000,
    created_at: Date.now(),
  };
  notificationActions.set(safeNote.id, actions);
  while (notificationActions.size > 200) {
    notificationActions.delete(notificationActions.keys().next().value);
  }
  if (
    floatingWindow &&
    !floatingWindow.isDestroyed() &&
    floatingWindowReady
  ) {
    floatingWindow.webContents.send("companion:notification", safeNote);
  } else {
    pendingNotifications.push(safeNote);
    if (pendingNotifications.length > 100) pendingNotifications.shift();
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("companion:notification", safeNote);
  }
  return safeNote;
}

async function syncBackendNotifications() {
  const result = await callApi("/v1/notify?limit=100");
  for (const notification of result.notifications) {
    if (seenNotificationIds.has(notification.id)) continue;
    seenNotificationIds.add(notification.id);
    pushNotification(notification);
  }
  while (seenNotificationIds.size > 500) {
    seenNotificationIds.delete(seenNotificationIds.values().next().value);
  }
}

app.whenReady().then(async () => {
  try {
    initializeDataPaths();
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback, details) => {
      const allowed =
        Boolean(mainWindow) &&
        webContents === mainWindow.webContents &&
        details.isMainFrame &&
        permission === "media" &&
        details.mediaTypes?.includes("audio") &&
        !details.mediaTypes?.includes("video");
      callback(allowed);
    });
    await startBackend();
    registerIpcHandlers();
    createWindow();
    createFloatingWindow();
    notificationPollTimer = setInterval(() => {
      syncBackendNotifications().catch((error) => {
        console.error("Could not sync local notifications:", error);
      });
    }, 1000);
    notificationPollTimer.unref();
  } catch (error) {
    console.error("Desktop companion startup failed:", error);
    dialog.showErrorBox(
      "墨小灵无法启动",
      `本地服务启动失败：${error.message}\n\n请确认 Python 3 和 Ollama 已安装并正常运行。`,
    );
    app.quit();
  }
});

app.on("before-quit", () => {
  if (notificationPollTimer) clearInterval(notificationPollTimer);
  if (backendProcess && backendProcess.exitCode === null) backendProcess.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
