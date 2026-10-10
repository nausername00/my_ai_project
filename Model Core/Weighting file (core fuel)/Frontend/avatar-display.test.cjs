const assert = require("node:assert/strict");
const test = require("node:test");

const {
  MODES,
  getAvatarCandidates,
  normalizeMode,
} = require("./avatar-display.js");

const card = {
  baseAvatar: "base.png",
  emotionAvatars: { happy: "happy.png", worried: "broken.png" },
};

test("follow mode prioritizes emotion art and then falls back to base art", () => {
  assert.deepEqual(
    getAvatarCandidates({ ...card, mood: "happy", mode: MODES.FOLLOW }),
    ["happy.png", "base.png"],
  );
  assert.deepEqual(
    getAvatarCandidates({ ...card, mood: "calm", mode: MODES.FOLLOW }),
    ["base.png"],
  );
});

test("fixed mode only selects base art regardless of simulated mood", () => {
  assert.deepEqual(
    getAvatarCandidates({ ...card, mood: "happy", mode: MODES.BASE }),
    ["base.png"],
  );
  assert.deepEqual(
    getAvatarCandidates({
      ...card,
      baseAvatar: null,
      mood: "happy",
      mode: MODES.BASE,
    }),
    [],
  );
});

test("candidate order is unique and unknown preferences safely use follow mode", () => {
  assert.deepEqual(
    getAvatarCandidates({
      baseAvatar: "same.png",
      emotionAvatars: { happy: "same.png" },
      mood: "happy",
      mode: "unknown",
    }),
    ["same.png"],
  );
  assert.equal(normalizeMode("unknown"), MODES.FOLLOW);
});
