const assert = require("node:assert/strict");
const test = require("node:test");

const { resolveSynthesisVoice } = require("./voice-playback.js");

test("resolves only an available local synthesis voice", () => {
  const voices = [{ name: "zh_CN-huayan-medium" }, { name: "en_US-lessac" }];
  assert.deepEqual(
    resolveSynthesisVoice("voice:en_US-lessac", voices),
    { voice: "en_US-lessac", unavailable: false },
  );
  assert.deepEqual(resolveSynthesisVoice("reference:sample-id", voices), {
    voice: undefined,
    unavailable: false,
  });
  assert.deepEqual(resolveSynthesisVoice("", voices), {
    voice: undefined,
    unavailable: false,
  });
});

test("falls back explicitly when a selected local synthesis voice is unavailable", () => {
  assert.deepEqual(resolveSynthesisVoice("voice:removed-voice", []), {
    voice: undefined,
    unavailable: true,
  });
  assert.deepEqual(resolveSynthesisVoice("voice:", [{ name: "other" }]), {
    voice: undefined,
    unavailable: true,
  });
});
