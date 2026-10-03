const assert = require("node:assert/strict");
const test = require("node:test");

const { createOllamaSetup } = require("./ollama-setup.cjs");

test("reports whether Ollama and the requested model are available", async () => {
  const setup = createOllamaSetup(
    "http://127.0.0.1:11434/",
    "qwen2.5:0.5b",
    async (url) => {
      assert.equal(url, "http://127.0.0.1:11434/api/tags");
      return Response.json({ models: [{ name: "qwen2.5:0.5b" }] });
    },
  );

  assert.deepEqual(await setup.getModelStatus(), {
    serviceAvailable: true,
    modelAvailable: true,
    modelName: "qwen2.5:0.5b",
    message: "模型已就绪",
  });
});

test("reports an unreachable Ollama service without hiding the error", async () => {
  const setup = createOllamaSetup(
    "http://127.0.0.1:11434",
    "qwen2.5:0.5b",
    async () => {
      throw new Error("connection refused");
    },
  );

  const status = await setup.getModelStatus();
  assert.equal(status.serviceAvailable, false);
  assert.match(status.message, /connection refused/);
});

test("downloads a model only when called and reports streaming progress", async () => {
  const requests = [];
  const progress = [];
  const setup = createOllamaSetup(
    "http://127.0.0.1:11434",
    "qwen2.5:0.5b",
    async (url, options = {}) => {
      requests.push({ url, options });
      if (url.endsWith("/api/pull")) {
        return new Response(
          [
            JSON.stringify({ status: "pulling", completed: 30, total: 100 }),
            JSON.stringify({ status: "success" }),
            "",
          ].join("\n"),
          { status: 200 },
        );
      }
      return Response.json({ models: [{ name: "qwen2.5:0.5b" }] });
    },
  );

  assert.equal(requests.length, 0);
  const status = await setup.pullModel((item) => progress.push(item));

  assert.equal(status.modelAvailable, true);
  assert.equal(requests[0].url, "http://127.0.0.1:11434/api/pull");
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    name: "qwen2.5:0.5b",
    stream: true,
  });
  assert.equal(progress[0].completed, 30);
  assert.equal(progress[0].total, 100);
});

test("surfaces model pull errors", async () => {
  const setup = createOllamaSetup(
    "http://127.0.0.1:11434",
    "qwen2.5:0.5b",
    async () =>
      new Response(JSON.stringify({ error: "model registry unavailable" }), {
        status: 500,
      }),
  );

  await assert.rejects(setup.pullModel(), /model registry unavailable/);
});
