const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const frontendDirectory = __dirname;
const preloadSource = fs.readFileSync(
  path.join(frontendDirectory, "floating-preload.cjs"),
  "utf8",
);
const floatingPage = fs.readFileSync(
  path.join(frontendDirectory, "floating.html"),
  "utf8",
);

test("packaged app includes the floating page and its isolated preload", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(frontendDirectory, "package.json"), "utf8"),
  );

  assert.ok(packageJson.build.files.includes("floating.html"));
  assert.ok(packageJson.build.files.includes("floating-preload.cjs"));
});

test("floating page script parses and uses the isolated preload bridge", () => {
  const inlineScript = floatingPage.match(/<script>([\s\S]*?)<\/script>/);

  assert.ok(inlineScript);
  assert.doesNotThrow(() => new vm.Script(inlineScript[1]));
  assert.match(inlineScript[1], /window\.floating\.onNotification/);
  assert.doesNotMatch(inlineScript[1], /require\(["']electron["']\)/);
});

test("floating preload exposes only its notification and window controls", () => {
  const handlers = new Map();
  const calls = [];
  let exposedName;
  let exposedApi;
  const ipcRenderer = {
    on(channel, listener) {
      handlers.set(channel, listener);
    },
    removeListener(channel, listener) {
      if (handlers.get(channel) === listener) handlers.delete(channel);
    },
    invoke(...args) {
      calls.push(args);
      return Promise.resolve({ accepted: true });
    },
  };
  const context = {
    require: () => ({
      contextBridge: {
        exposeInMainWorld(name, api) {
          exposedName = name;
          exposedApi = api;
        },
      },
      ipcRenderer,
    }),
  };

  vm.runInNewContext(preloadSource, context);

  assert.equal(exposedName, "floating");
  assert.deepEqual(Object.keys(exposedApi), [
    "onNotification",
    "sendNotificationAction",
    "showMainWindow",
    "hideFloating",
  ]);

  const received = [];
  const unsubscribe = exposedApi.onNotification((notification) => {
    received.push(notification);
  });
  const notification = { id: "n-1" };
  handlers.get("companion:notification")({}, notification);
  unsubscribe();
  assert.deepEqual(received, [notification]);
  assert.equal(handlers.has("companion:notification"), false);

  exposedApi.sendNotificationAction("n-1", 0);
  exposedApi.showMainWindow();
  exposedApi.hideFloating();
  assert.deepEqual(calls, [
    ["companion:notify-action", "n-1", 0],
    ["companion:main-window-show"],
    ["companion:floating-hide"],
  ]);
});
