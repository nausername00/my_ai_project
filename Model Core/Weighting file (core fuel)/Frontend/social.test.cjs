const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

test("social bridge exposes local status, partner catalog and collaboration calls", async () => {
  const preloadPath = path.join(__dirname, "preload.cjs");
  const preloadSource = fs.readFileSync(preloadPath, "utf8");
  const calls = [];
  let exposedApi;
  const context = {
    require: () => ({
      contextBridge: {
        exposeInMainWorld(name, api) {
          assert.equal(name, "companion");
          exposedApi = api;
        },
      },
      ipcRenderer: {
        invoke(...args) {
          calls.push(args);
          return Promise.resolve({ ok: true });
        },
        on() {},
        removeListener() {},
      },
    }),
  };

  vm.runInNewContext(preloadSource, context);

  await exposedApi.getSocialStatus();
  await exposedApi.listSocialPartners();
  const roles = [
    { key: "architecture", enabled: true, instruction: "Keep this local prompt" },
  ];
  await exposedApi.collaborateSocial("Review the plan", roles);

  assert.deepEqual(calls.slice(-3), [
    ["companion:social-status"],
    ["companion:list-social-partners"],
    ["companion:collaborate-social", "Review the plan", roles],
  ]);
});
