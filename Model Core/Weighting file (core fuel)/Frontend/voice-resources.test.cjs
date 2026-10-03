const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { VoiceResourceStore } = require("./voice-resources.cjs");

function wavSample() {
  const bytes = Buffer.alloc(16);
  bytes.write("RIFF", 0, "ascii");
  bytes.write("WAVE", 8, "ascii");
  return bytes;
}

function mp3Sample() {
  const bytes = Buffer.alloc(12);
  bytes.write("ID3", 0, "ascii");
  return bytes;
}

test("registers, lists, and plays back a reference sample without source paths", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "moling-voices-"));
  try {
    const store = new VoiceResourceStore(directory);
    const registered = await store.register({
      name: "English sample",
      language: "en-US",
      originalName: "reference.wav",
      bytes: wavSample(),
    });

    assert.equal(registered.name, "English sample");
    assert.equal(registered.language, "en-US");
    assert.equal(registered.contentType, "audio/wav");
    assert.equal("sourcePath" in registered, false);
    assert.deepEqual(await store.list(), [registered]);
    const sample = await store.readSample(registered.id);
    assert.equal(sample.contentType, "audio/wav");
    assert.deepEqual(sample.bytes, wavSample());
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("accepts MP3 samples and removes both their catalog entry and audio file", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "moling-voices-"));
  try {
    const store = new VoiceResourceStore(directory);
    const registered = await store.register({
      name: "Sample",
      language: "auto",
      originalName: "sample.mp3",
      bytes: mp3Sample(),
    });

    await store.remove(registered.id);
    assert.deepEqual(await store.list(), []);
    await assert.rejects(store.readSample(registered.id), /找不到/);
    await assert.rejects(
      fs.access(path.join(directory, "voice-references", registered.file)),
    );
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("rejects unsupported languages, extensions, and mismatched audio content", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "moling-voices-"));
  try {
    const store = new VoiceResourceStore(directory);
    await assert.rejects(
      store.register({
        name: "Sample",
        language: "unknown",
        originalName: "sample.wav",
        bytes: wavSample(),
      }),
      /语言/,
    );
    await assert.rejects(
      store.register({
        name: "Sample",
        language: "auto",
        originalName: "sample.txt",
        bytes: wavSample(),
      }),
      /WAV 或 MP3/,
    );
    await assert.rejects(
      store.register({
        name: "Sample",
        language: "auto",
        originalName: "sample.mp3",
        bytes: wavSample(),
      }),
      /不匹配/,
    );
    assert.deepEqual(await store.list(), []);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("serializes concurrent registrations without losing catalog entries", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "moling-voices-"));
  try {
    const store = new VoiceResourceStore(directory);
    await Promise.all(
      ["First", "Second"].map((name) =>
        store.register({
          name,
          language: "zh-CN",
          originalName: `${name}.wav`,
          bytes: wavSample(),
        }),
      ),
    );
    assert.deepEqual(
      (await store.list()).map((resource) => resource.name).sort(),
      ["First", "Second"],
    );
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});
