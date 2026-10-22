// 墨灵生活状态机 · 纯逻辑测试
"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const os = require("node:os");
const path = require("node:path");
const fs = require("node:fs");

const {
  classifyBattery,
  pickBedtime,
  decideFreeActivity,
  nextLifeState,
  LifeStateStore,
} = require("./life-state.cjs");

test("classifyBattery：无电池(台式机)=stable", () => {
  assert.equal(classifyBattery({ hasBattery: false, percent: 5, charging: false }), "stable");
});

test("classifyBattery：充电中=charging", () => {
  assert.equal(classifyBattery({ hasBattery: true, percent: 18, charging: true }), "charging");
});

test("classifyBattery：<=20% 放电=low", () => {
  assert.equal(classifyBattery({ hasBattery: true, percent: 20, charging: false }), "low");
  assert.equal(classifyBattery({ hasBattery: true, percent: 5, charging: false }), "low");
});

test("classifyBattery：>20% 放电=stable", () => {
  assert.equal(classifyBattery({ hasBattery: true, percent: 21, charging: false }), "stable");
  assert.equal(classifyBattery({ hasBattery: true, percent: 100, charging: false }), "stable");
});

test("pickBedtime：只返回 bed/pod/door", () => {
  for (let i = 0; i < 50; i += 1) {
    assert.ok(["bed", "pod", "door"].includes(pickBedtime()));
  }
});

test("decideFreeActivity：只返回 sleep/read/stare", () => {
  for (let i = 0; i < 50; i += 1) {
    assert.ok(["sleep", "read", "stare"].includes(decideFreeActivity()));
  }
});

test("nextLifeState：suspend → sleeping", () => {
  assert.equal(nextLifeState("active", "suspend"), "sleeping");
  assert.equal(nextLifeState("free", "suspend"), "sleeping");
});

test("nextLifeState：resume → waking → finish → active", () => {
  assert.equal(nextLifeState("sleeping", "resume"), "waking");
  assert.equal(nextLifeState("waking", "finish_waking"), "active");
});

test("nextLifeState：低电 → low；充电/稳定 → 恢复 active", () => {
  assert.equal(nextLifeState("active", "battery_low"), "low");
  assert.equal(nextLifeState("low", "battery_charging"), "active");
  assert.equal(nextLifeState("low", "battery_stable"), "active");
  // 非低电状态下电池稳定不打断当前状态
  assert.equal(nextLifeState("free", "battery_stable"), "free");
});

test("nextLifeState：idle → free；user_active → active（被唤醒）", () => {
  assert.equal(nextLifeState("active", "idle"), "free");
  assert.equal(nextLifeState("free", "user_active"), "active");
  assert.equal(nextLifeState("low", "user_active"), "active");
  // idle 不打断 free/低电
  assert.equal(nextLifeState("free", "idle"), "free");
  assert.equal(nextLifeState("low", "idle"), "low");
});

test("nextLifeState：开机场景 clean/unclean → 对应过渡态", () => {
  assert.equal(nextLifeState("active", "boot_clean"), "waking_clean");
  assert.equal(nextLifeState("active", "boot_unclean"), "waking_unclean");
  assert.equal(nextLifeState("waking_clean", "finish_waking"), "active");
});

test("LifeStateStore：空档回默认，写入可读回", () => {
  const file = path.join(os.tmpdir(), `moling_life_test_${Date.now()}_${Math.random().toString(36).slice(2)}.json`);
  const store = new LifeStateStore(file);
  try {
    assert.deepEqual(store.read(), {});
    assert.equal(store.write({ a: 1 }), true);
    assert.deepEqual(store.read(), { a: 1 });
  } finally {
    try {
      fs.unlinkSync(file);
    } catch {}
  }
});

test("LifeStateStore：markCleanExit → consumeBootScenario 返回 clean 并清理标记", () => {
  const file = path.join(os.tmpdir(), `moling_life_test_${Date.now()}_${Math.random().toString(36).slice(2)}.json`);
  const store = new LifeStateStore(file);
  try {
    store.markCleanExit("app_quit");
    const sc = store.consumeBootScenario();
    assert.equal(sc.boot, "clean");
    assert.ok(["bed", "pod", "door"].includes(sc.bedtime));
    // 标记已消费
    assert.equal(store.read().lastExit, undefined);
    assert.equal(store.read().lastKind, undefined);
  } finally {
    try {
      fs.unlinkSync(file);
    } catch {}
  }
});

test("LifeStateStore：无 clean 标记（系统关机/断电）→ unclean", () => {
  const file = path.join(os.tmpdir(), `moling_life_test_${Date.now()}_${Math.random().toString(36).slice(2)}.json`);
  const store = new LifeStateStore(file);
  try {
    const sc = store.consumeBootScenario();
    assert.equal(sc.boot, "unclean");
    assert.ok(["bed", "pod", "door"].includes(sc.bedtime));
  } finally {
    try {
      fs.unlinkSync(file);
    } catch {}
  }
});

test("LifeStateStore：保留 lastBedtime 供开机过场呼应", () => {
  const file = path.join(os.tmpdir(), `moling_life_test_${Date.now()}_${Math.random().toString(36).slice(2)}.json`);
  const store = new LifeStateStore(file);
  try {
    store.write({ lastBedtime: "pod" });
    const sc = store.consumeBootScenario();
    assert.equal(sc.boot, "unclean");
    assert.equal(sc.bedtime, "pod"); // 上次睡休眠舱 → 从休眠舱醒来
  } finally {
    try {
      fs.unlinkSync(file);
    } catch {}
  }
});
