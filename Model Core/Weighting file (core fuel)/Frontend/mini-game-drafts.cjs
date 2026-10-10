"use strict";

// 小游戏草案生命周期（J1）。
//
// 生成内容先进入项目目录之外的临时草案（应用数据目录），支持
// 查看 / 编辑 / 重置为生成版本 / 丢弃；"保存到项目"只新建、不覆盖，
// 由调用方在确认后调用 promoteWorking。所有写入都是 UTF-8。

const fs = require("node:fs/promises");
const path = require("node:path");

const MAX_DRAFT_BYTES = 20_000;
const MAX_DRAFT_CONTENT = 4000;

function originalPath(draftsDir) {
  return path.join(draftsDir, "moling-mini-game.original.html");
}

function workingPath(draftsDir) {
  return path.join(draftsDir, "moling-mini-game.working.html");
}

async function ensureDraftDir(draftsDir) {
  await fs.mkdir(draftsDir, { recursive: true });
}

function isReasonableDraftContent(content) {
  return (
    typeof content === "string" &&
    content.trim().length > 0 &&
    content.length <= MAX_DRAFT_CONTENT &&
    Buffer.byteLength(content, "utf8") <= MAX_DRAFT_BYTES
  );
}

// 模型生成后首次落盘：同时写 original（生成基准）与 working（可编辑草案）。
async function seedDraft(draftsDir, content) {
  if (!isReasonableDraftContent(content)) {
    throw new Error("草案内容无效或超出长度限制。");
  }
  await ensureDraftDir(draftsDir);
  await fs.writeFile(originalPath(draftsDir), content, "utf8");
  await fs.writeFile(workingPath(draftsDir), content, "utf8");
  return { seeded: true, content };
}

async function draftStatus(draftsDir, projectPath) {
  let hasOriginal = false;
  let hasWorking = false;
  let projectExists = false;
  try {
    await fs.access(originalPath(draftsDir));
    hasOriginal = true;
  } catch {
    /* 不存在 */
  }
  try {
    await fs.access(workingPath(draftsDir));
    hasWorking = true;
  } catch {
    /* 不存在 */
  }
  try {
    await fs.access(projectPath);
    projectExists = true;
  } catch {
    /* 不存在 */
  }
  return { hasOriginal, hasWorking, projectExists };
}

async function readDraft(draftsDir) {
  let original = "";
  let working = "";
  try {
    original = await fs.readFile(originalPath(draftsDir), "utf8");
  } catch {
    /* 不存在则空 */
  }
  try {
    working = await fs.readFile(workingPath(draftsDir), "utf8");
  } catch {
    /* 不存在则空 */
  }
  return { original, working };
}

async function writeWorking(draftsDir, content) {
  if (!isReasonableDraftContent(content)) {
    throw new Error("草案内容无效或超出长度限制。");
  }
  await ensureDraftDir(draftsDir);
  await fs.writeFile(workingPath(draftsDir), content, "utf8");
  return { saved: true };
}

// 重置：把编辑后的草案恢复为模型生成版本。没有生成基准时报错。
async function resetWorking(draftsDir) {
  let original = "";
  try {
    original = await fs.readFile(originalPath(draftsDir), "utf8");
  } catch {
    throw new Error("没有可重置的生成版本；请先让墨灵生成草案。");
  }
  await ensureDraftDir(draftsDir);
  await fs.writeFile(workingPath(draftsDir), original, "utf8");
  return { reset: true };
}

// 丢弃：删除草案（original + working）。无文件时静默成功。
async function discardDrafts(draftsDir) {
  let removed = 0;
  for (const p of [originalPath(draftsDir), workingPath(draftsDir)]) {
    try {
      await fs.unlink(p);
      removed += 1;
    } catch {
      /* 不存在 */
    }
  }
  return { discarded: true, removed };
}

// 保存到项目：只新建、不覆盖。目标已存在时返回 conflict，绝不覆盖。
async function promoteWorking(draftsDir, projectPath) {
  let working = "";
  try {
    working = await fs.readFile(workingPath(draftsDir), "utf8");
  } catch {
    return { written: false, error: "没有可保存的草案；请先让墨灵生成草案。" };
  }
  if (!working.trim()) {
    return { written: false, error: "草案为空，拒绝写入项目。" };
  }
  try {
    await fs.access(projectPath);
    return { written: false, conflict: true, path: projectPath };
  } catch {
    /* 目标不存在，可以新建 */
  }
  try {
    await fs.mkdir(path.dirname(projectPath), { recursive: true });
    await fs.writeFile(projectPath, working, "utf8");
    return { written: true, path: projectPath };
  } catch (error) {
    return { written: false, error: error.message };
  }
}

module.exports = {
  MAX_DRAFT_CONTENT,
  originalPath,
  workingPath,
  seedDraft,
  draftStatus,
  readDraft,
  writeWorking,
  resetWorking,
  discardDrafts,
  promoteWorking,
  isReasonableDraftContent,
};
