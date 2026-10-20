const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const frontendDirectory = __dirname;
const floatingHtml = fs.readFileSync(path.join(frontendDirectory, "floating.html"), "utf8");
const mainSource = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");

function extractBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(start, -1, `missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `missing source marker: ${endMarker}`);
  return source.slice(start, end);
}

function createElement() {
  return {
    hidden: false,
    textContent: "",
    src: "",
    alt: "",
    dataset: {},
    style: {
      setProperty(name, value) {
        this[name] = value;
      },
    },
    removeAttribute(name) {
      if (name === "src") this.src = "";
    },
  };
}

test("floating avatar applies the active portrait and falls back after decode failure", () => {
  const elements = new Map(
    ["avatar-image", "avatar-text", "avatar-wrap", "nickname", "status-text", "mood-dot", "thinking-box"].map(
      (id) => [id, createElement()],
    ),
  );
  const sandbox = {
    document: { getElementById: (id) => elements.get(id) },
    avatarEl: elements.get("avatar-wrap"),
  };
  const applyCharacterSource = extractBetween(
    floatingHtml,
    "function applyCharacter(character) {",
    "window.floating.onNotification(handleNotification);",
  );
  vm.runInNewContext(
    `let characterUpdateVersion = 0; ${applyCharacterSource}; globalThis.applyCharacter = applyCharacter;`,
    sandbox,
  );
  const applyCharacter = sandbox.applyCharacter;
  const image = elements.get("avatar-image");
  const text = elements.get("avatar-text");
  const status = elements.get("status-text");
  const avatar = elements.get("avatar-wrap");

  applyCharacter({
    nickname: "墨灵",
    avatarDataUrl: "data:image/png;base64,portrait",
    moodKey: "happy",
    moodLabel: "开心",
  });
  assert.equal(image.src, "data:image/png;base64,portrait");
  assert.equal(image.hidden, false);
  assert.equal(text.hidden, true);
  assert.equal(image.alt, "墨灵角色立绘");
  assert.equal(status.textContent, "模拟状态 · 开心");
  assert.equal(avatar.style["--mood-halo"], "#ffd166");

  const staleErrorHandler = image.onerror;
  applyCharacter({ nickname: "新角色", avatarDataUrl: null, moodKey: "calm" });
  staleErrorHandler();
  assert.equal(image.hidden, true);
  assert.equal(image.src, "");
  assert.equal(text.hidden, false);
  assert.equal(text.textContent, "新");

  applyCharacter({
    nickname: "新角色",
    avatarDataUrl: "data:image/png;base64,broken",
    moodKey: "calm",
  });
  image.onerror();
  assert.equal(image.hidden, true);
  assert.equal(image.src, "");
  assert.equal(text.hidden, false);
  assert.match(status.textContent, /角色立绘无法显示/);
});

test("floating avatar retries the base portrait before its text fallback", () => {
  const elements = new Map(
    ["avatar-image", "avatar-text", "avatar-wrap", "nickname", "status-text", "mood-dot", "thinking-box"].map(
      (id) => [id, createElement()],
    ),
  );
  const sandbox = {
    document: { getElementById: (id) => elements.get(id) },
    avatarEl: elements.get("avatar-wrap"),
  };
  const applyCharacterSource = extractBetween(
    floatingHtml,
    "function applyCharacter(character) {",
    "window.floating.onNotification(handleNotification);",
  );
  vm.runInNewContext(
    `let characterUpdateVersion = 0; ${applyCharacterSource}; globalThis.applyCharacter = applyCharacter;`,
    sandbox,
  );
  const image = elements.get("avatar-image");
  const text = elements.get("avatar-text");
  const status = elements.get("status-text");

  sandbox.applyCharacter({
    nickname: "墨灵",
    avatarDataUrl: "data:image/png;base64,emotion",
    avatarFallbackDataUrl: "data:image/png;base64,base",
    moodLabel: "好奇",
  });
  image.onerror();
  assert.equal(image.src, "data:image/png;base64,base");
  assert.equal(image.hidden, false);
  image.onerror();
  assert.equal(image.hidden, true);
  assert.equal(text.hidden, false);
  assert.match(status.textContent, /立绘无法显示/);
});

test("late floating character requests cannot overwrite the latest selected character", async () => {
  const pendingCharacters = [];
  const sent = [];
  const sandbox = {
    floatingWindowReady: true,
    floatingCharacterUpdateVersion: 0,
    floatingAvatarDisplayMode: "follow",
    floatingWindow: {
      isDestroyed: () => false,
      webContents: {
        send: (_channel, character) => sent.push(character),
      },
    },
    callApi: (route) => {
      if (route === "/v1/character") {
        return new Promise((resolve) => pendingCharacters.push(resolve));
      }
      if (route === "/v1/affect") {
        return Promise.resolve({ mood: "happy", label: "开心" });
      }
      throw new Error(`unexpected API route: ${route}`);
    },
    readAvatar: async (fileName) => `data:image/png;base64,${fileName}`,
    MolingAvatarDisplay: require("./avatar-display.js"),
    getAvatarCandidates: require("./avatar-display.js").getAvatarCandidates,
  };
  const updateSource = extractBetween(
    mainSource,
    "async function pushCharacterToFloating() {",
    "function createFloatingWindow() {",
  );
  vm.runInNewContext(
    `${updateSource}; globalThis.pushCharacterToFloating = pushCharacterToFloating;`,
    sandbox,
  );

  const olderRequest = sandbox.pushCharacterToFloating();
  const latestRequest = sandbox.pushCharacterToFloating();
  pendingCharacters[1]({
    character: {
      nickname: "最新角色",
      avatar: "latest.png",
      emotion_avatars: { happy: "latest-happy.png" },
    },
  });

  await latestRequest;
  pendingCharacters[0]({
    character: { nickname: "旧角色", avatar: "old.png", emotion_avatars: {} },
  });
  await olderRequest;

  assert.equal(sent.length, 1);
  assert.equal(sent[0].nickname, "最新角色");
  assert.equal(
    sent[0].avatarDataUrl,
    "data:image/png;base64,latest-happy.png",
  );
  assert.equal(sent[0].moodKey, "happy");
});

test("floating avatar loading falls back to base art when mood art cannot be read", async () => {
  const sent = [];
  const sandbox = {
    floatingWindowReady: true,
    floatingCharacterUpdateVersion: 0,
    floatingAvatarDisplayMode: "follow",
    floatingWindow: {
      isDestroyed: () => false,
      webContents: {
        send: (_channel, character) => sent.push(character),
      },
    },
    callApi: (route) => {
      if (route === "/v1/character") {
        return Promise.resolve({
          character: {
            nickname: "墨灵",
            avatar: "base.png",
            emotion_avatars: { curious: "emotion.png" },
          },
        });
      }
      if (route === "/v1/affect") {
        return Promise.resolve({ mood: "curious", label: "好奇" });
      }
      throw new Error(`unexpected API route: ${route}`);
    },
    readAvatar: async (fileName) => {
      if (fileName === "emotion.png") {
        throw new Error("missing emotion portrait");
      }
      return `data:image/png;base64,${fileName}`;
    },
    MolingAvatarDisplay: require("./avatar-display.js"),
    getAvatarCandidates: require("./avatar-display.js").getAvatarCandidates,
  };
  const updateSource = extractBetween(
    mainSource,
    "async function pushCharacterToFloating() {",
    "function createFloatingWindow() {",
  );
  vm.runInNewContext(
    `${updateSource}; globalThis.pushCharacterToFloating = pushCharacterToFloating;`,
    sandbox,
  );
  await sandbox.pushCharacterToFloating();

  assert.equal(sent.length, 1);
  assert.equal(sent[0].avatarDataUrl, "data:image/png;base64,base.png");
  assert.equal(sent[0].avatarFallbackDataUrl, null);
});
