// 墨灵生活状态机（电池 / 空闲自由时间 / 睡眠与起床过场）
//
// 设计（用户 2026-10-22 拍板）：
//   - 不做"精力条"数值管理；墨灵空闲时是自由时间（睡觉/看书/发呆）
//   - 电池是"真电量"映射：低电趴着、充电恢复（台式机无电池 = 电源稳定）
//   - 系统睡眠/正常退出 → 睡觉过场（躺床/休眠舱/出门 随机）；开机 → 起床过场
//   - Windows 无法可靠捕获系统关机 → 用"上次退出是否干净"驱动开机过场：
//       正常退出(before-quit) → 开机播"睡饱起床"；系统关机/断电 → 开机播"迷糊被带走"
//
// 本文件分两部分：
//   [1] 纯逻辑（classifyBattery / pickBedtime / decideFreeActivity / nextLifeState / LifeStateStore）
//       —— 不依赖 Electron，可被 life-state.test.cjs 单测。
//   [2] createLifeMonitor —— Electron 适配器（powerMonitor + WMI 电池 + IPC 广播）。

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFile } = require("child_process");

// ---------------------------------------------------------------------------
// [1] 纯逻辑
// ---------------------------------------------------------------------------

// 电池分级：无电池(台式机)=stable；充电中=charging；<=20%=low；其余=stable
function classifyBattery({ hasBattery = true, percent = 100, charging = false } = {}) {
  if (!hasBattery) return "stable";
  if (charging) return "charging";
  if (Number.isFinite(percent) && percent <= 20) return "low";
  return "stable";
}

// 睡觉方式随机：躺床 / 休眠舱 / 开门出去
function pickBedtime() {
  const pool = ["bed", "pod", "door"];
  return pool[Math.floor(Math.random() * pool.length)];
}

// 自由时间活动随机：睡觉 / 看书 / 发呆看窗外
function decideFreeActivity() {
  const r = Math.random();
  if (r < 0.5) return "sleep";
  if (r < 0.8) return "read";
  return "stare";
}

// 状态机：active | free | low | sleeping | waking | waking_clean | waking_unclean
// 事件：
//   user_active / idle / battery_low / battery_charging / battery_stable
//   suspend / resume / boot_clean / boot_unclean / finish_waking
function nextLifeState(cur, evt) {
  switch (evt) {
    case "suspend":
      return "sleeping";
    case "resume":
      return "waking";
    case "finish_waking":
      return "active";
    case "battery_low":
      return "low";
    case "battery_charging":
    case "battery_stable":
      return cur === "low" ? "active" : cur;
    case "idle":
      return cur === "active" ? "free" : cur;
    case "user_active":
      return cur === "free" || cur === "low" || cur === "waking" ? "active" : cur;
    case "boot_clean":
      return "waking_clean";
    case "boot_unclean":
      return "waking_unclean";
    default:
      return cur;
  }
}

// 生活状态存档：记录"上次退出是否干净" + 睡觉方式，供开机过场消费
class LifeStateStore {
  constructor(file) {
    this.file = file || path.join(os.tmpdir(), "moling_life_state.json");
  }

  read() {
    try {
      const raw = fs.readFileSync(this.file, "utf8");
      const obj = JSON.parse(raw);
      return obj && typeof obj === "object" ? obj : {};
    } catch {
      return {};
    }
  }

  write(obj) {
    try {
      fs.writeFileSync(this.file, JSON.stringify(obj));
      return true;
    } catch {
      return false;
    }
  }

  // 正常退出：记 clean 标记 + 本次睡觉方式
  markCleanExit(kind = "app_quit") {
    const s = this.read();
    s.lastExit = "clean";
    s.lastKind = kind;
    s.ts = Date.now();
    return this.write(s);
  }

  // 开机消费场景并清理：clean → 睡饱起床；无 clean 标记 → 被突然带走
  consumeBootScenario() {
    const s = this.read();
    const kind = s.lastExit === "clean" ? "clean" : "unclean";
    const bedtime = s.lastBedtime || pickBedtime();
    const next = { ...s };
    delete next.lastExit;
    delete next.lastKind;
    delete next.ts;
    if (!next.lastBedtime) {
      // 保留 bedtime 供后续
      next.lastBedtime = bedtime;
    }
    this.write(next);
    return { boot: kind, bedtime };
  }
}

// ---------------------------------------------------------------------------
// [2] Electron 适配器
// ---------------------------------------------------------------------------

// Windows 电池读取（WMI）。输出强制 UTF-8 避免 GBK/UTF-16 乱码。
function readBattery(cb) {
  if (process.platform !== "win32") {
    // 非 Windows：视为电源稳定（桌面环境）
    return cb({ hasBattery: false, percent: 100, charging: true, source: "non-windows" });
  }
  const ps =
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " +
    "$b=Get-CimInstance Win32_Battery; " +
    "if($b){$p=[math]::Round($b.EstimatedChargeRemaining); " +
    "$c=($b.BatteryStatus -eq 2); " +
    "[pscustomobject]@{p=$p;c=$c}|ConvertTo-Json -Compress}else{Write-Output 'NOBATTERY'}";
  execFile(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", ps],
    { timeout: 8000, windowsHide: true },
    (err, stdout) => {
      if (err) {
        return cb({ hasBattery: true, percent: 100, charging: true, source: "read_error" });
      }
      const t = String(stdout || "").trim();
      if (!t || t === "NOBATTERY") {
        return cb({ hasBattery: false, percent: 100, charging: true, source: "no_battery" });
      }
      try {
        const o = JSON.parse(t);
        return cb({
          hasBattery: true,
          percent: Number(o.p),
          charging: Boolean(o.c),
          source: "wmi",
        });
      } catch {
        return cb({ hasBattery: true, percent: 100, charging: true, source: "parse_fail" });
      }
    }
  );
}

// 创建生活状态监视器。
// opts: { idleThresholdSec=300, batteryIntervalMs=60000, idleIntervalMs=30000,
//         wakeDelayMs=8000, store }
// 返回 { start(), stop(), getState(), markUserActive(), beforeQuit(), bootScenario(), channel }
function createLifeMonitor({ store, onEvent, opts = {} }) {
  const { powerMonitor } = require("electron"); // 适配器才依赖 Electron
  const idleThresholdSec = opts.idleThresholdSec || 300;
  const batteryIntervalMs = opts.batteryIntervalMs || 60000;
  const idleIntervalMs = opts.idleIntervalMs || 30000;
  const wakeDelayMs = opts.wakeDelayMs || 8000;

  let state = "active";
  let activity = "sleep"; // 自由时间当前活动
  let bedtime = "bed"; // 本次睡觉方式
  let battery = { hasBattery: true, percent: 100, charging: true, source: "init" };

  const timers = [];
  let stopped = false;

  function setState(next, extra = {}) {
    const prev = state;
    state = next;
    const payload = {
      state,
      prev,
      activity,
      bedtime,
      battery,
      ts: Date.now(),
      ...extra,
    };
    try {
      onEvent(payload);
    } catch (e) {
      console.error("[life-state] onEvent failed:", e);
    }
    return payload;
  }

  function applyBattery(nextBattery) {
    battery = nextBattery;
    const cls = classifyBattery(nextBattery);
    const evt =
      cls === "low"
        ? "battery_low"
        : cls === "charging"
          ? "battery_charging"
          : "battery_stable";
    setState(nextLifeState(state, evt), { batteryEvt: evt, battery });
  }

  function pollBattery() {
    readBattery((b) => {
      if (!stopped) applyBattery(b);
    });
  }

  function pollIdle() {
    if (stopped) return;
    let idle = 0;
    try {
      idle = powerMonitor.getSystemIdleTime() || 0;
    } catch {
      return;
    }
    if (state === "active" && idle >= idleThresholdSec) {
      activity = decideFreeActivity();
      setState("free", { activity });
    } else if (state === "free" && idle < idleThresholdSec) {
      setState("active", { woken: true });
    } else if (state === "free") {
      // 自由时间持续：偶尔换活动，避免一直同一个动作
      if (Math.floor(idle / 60) % 3 === 0) {
        const nextActivity = decideFreeActivity();
        if (nextActivity !== activity) {
          activity = nextActivity;
          setState("free", { activity });
        }
      }
    }
  }

  function markUserActive() {
    if (state === "free" || state === "low" || state === "waking") {
      setState("active", { woken: true });
    }
  }

  // 开机场景：返回 { boot:'clean'|'unclean', bedtime }，并据场景进入对应过渡态
  function bootScenario() {
    const sc = store.consumeBootScenario();
    bedtime = sc.bedtime;
    setState(nextLifeState(state, sc.boot === "clean" ? "boot_clean" : "boot_unclean"), sc);
    // 起床过场播完自动回 active
    const t = setTimeout(() => {
      if (!stopped) setState("active", { finishWaking: true });
    }, wakeDelayMs);
    if (typeof t.unref === "function") t.unref();
    timers.push(t);
    return sc;
  }

  function beforeQuit() {
    store.markCleanExit("app_quit");
  }

  function start() {
    if (stopped) return;
    // 电池：立即读 + 周期读
    pollBattery();
    const bt = setInterval(pollBattery, batteryIntervalMs);
    if (typeof bt.unref === "function") bt.unref();
    timers.push(bt);
    // 空闲：周期轮询
    const it = setInterval(pollIdle, idleIntervalMs);
    if (typeof it.unref === "function") it.unref();
    timers.push(it);
    // 系统睡眠/唤醒
    powerMonitor.on("suspend", () => {
      bedtime = pickBedtime();
      const s = store.read();
      s.lastBedtime = bedtime;
      store.write(s);
      setState("sleeping", { bedtime });
    });
    powerMonitor.on("resume", () => {
      setState("waking", { bedtime });
      const t = setTimeout(() => {
        if (!stopped) setState("active", { finishWaking: true });
      }, wakeDelayMs);
      if (typeof t.unref === "function") t.unref();
      timers.push(t);
    });
  }

  function stop() {
    stopped = true;
    for (const t of timers) clearInterval(t);
    timers.length = 0;
  }

  function getState() {
    return { state, activity, bedtime, battery };
  }

  return {
    start,
    stop,
    getState,
    markUserActive,
    beforeQuit,
    bootScenario,
    channel: "companion:life-event",
  };
}

module.exports = {
  // 纯逻辑
  classifyBattery,
  pickBedtime,
  decideFreeActivity,
  nextLifeState,
  LifeStateStore,
  // 适配器
  createLifeMonitor,
  readBattery,
};
