"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const {
  MAX_DRAFT_CONTENT,
  seedDraft,
  draftStatus,
  readDraft,
  writeWorking,
  resetWorking,
  discardDrafts,
  promoteWorking,
  isReasonableDraftContent,
} = require("./mini-game-drafts.cjs");

async function makeTempDirs() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "j1-drafts-"));
  const draftsDir = path.join(root, "drafts");
  const projectDir = path.join(root, "project");
  const projectPath = path.join(projectDir, "moling-mini-game.html");
  return { root, draftsDir, projectDir, projectPath };
}

const GENERATED = "<!doctype html><html><body>墨灵生成的小游戏</body></html>";
const EDITED = "<!doctype html><html><body>我编辑过的版本</body></html>";

test("seedDraft stores original and working drafts outside the project", async () => {
  const { draftsDir, projectPath } = await makeTempDirs();
  const result = await seedDraft(draftsDir, GENERATED);
  assert.equal(result.seeded, true);
  const status = await draftStatus(draftsDir, projectPath);
  assert.equal(status.hasOriginal, true);
  assert.equal(status.hasWorking, true);
  assert.equal(status.projectExists, false, "确认保存前项目目录不应有新增文件");
  const { original, working } = await readDraft(draftsDir);
  assert.equal(original, GENERATED);
  assert.equal(working, GENERATED);
});

test("writeWorking updates only the working draft", async () => {
  const { draftsDir, projectPath } = await makeTempDirs();
  await seedDraft(draftsDir, GENERATED);
  await writeWorking(draftsDir, EDITED);
  const { original, working } = await readDraft(draftsDir);
  assert.equal(original, GENERATED, "生成基准不被编辑覆盖");
  assert.equal(working, EDITED);
  assert.equal((await draftStatus(draftsDir, projectPath)).projectExists, false);
});

test("resetWorking restores the generated version; fails without a baseline", async () => {
  const { draftsDir, projectPath } = await makeTempDirs();
  await assert.rejects(() => resetWorking(draftsDir), /没有可重置的生成版本/);
  await seedDraft(draftsDir, GENERATED);
  await writeWorking(draftsDir, EDITED);
  await resetWorking(draftsDir);
  const { working } = await readDraft(draftsDir);
  assert.equal(working, GENERATED);
  assert.equal((await draftStatus(draftsDir, projectPath)).hasWorking, true);
});

test("discardDrafts removes both drafts; missing files are tolerated", async () => {
  const { draftsDir } = await makeTempDirs();
  assert.equal((await discardDrafts(draftsDir)).removed, 0);
  await seedDraft(draftsDir, GENERATED);
  const result = await discardDrafts(draftsDir);
  assert.equal(result.removed, 2);
  const status = await draftStatus(draftsDir, "");
  assert.equal(status.hasOriginal, false);
  assert.equal(status.hasWorking, false);
});

test("promoteWorking creates the project file only when absent; never overwrites", async () => {
  const { draftsDir, projectDir, projectPath } = await makeTempDirs();
  // 无草案
  let result = await promoteWorking(draftsDir, projectPath);
  assert.equal(result.written, false);
  assert.match(result.error, /没有可保存的草案/);

  await seedDraft(draftsDir, GENERATED);
  await writeWorking(draftsDir, EDITED);

  // 目标不存在 → 新建，内容与获批草案一致
  result = await promoteWorking(draftsDir, projectPath);
  assert.equal(result.written, true);
  assert.equal(result.path, projectPath);
  assert.equal(await fs.readFile(projectPath, "utf8"), EDITED);

  // 目标已存在 → 拒绝，且不覆盖原内容
  await fs.writeFile(projectPath, "已有内容不可覆盖", "utf8");
  result = await promoteWorking(draftsDir, projectPath);
  assert.equal(result.written, false);
  assert.equal(result.conflict, true);
  assert.equal(await fs.readFile(projectPath, "utf8"), "已有内容不可覆盖");
});

test("isReasonableDraftContent enforces size and content bounds", () => {
  assert.equal(isReasonableDraftContent("<html></html>"), true);
  assert.equal(isReasonableDraftContent(""), false);
  assert.equal(isReasonableDraftContent("   "), false);
  assert.equal(isReasonableDraftContent("x".repeat(MAX_DRAFT_CONTENT + 1)), false);
  assert.equal(isReasonableDraftContent("x".repeat(MAX_DRAFT_CONTENT)), true);
  assert.equal(isReasonableDraftContent(123), false);
  assert.equal(isReasonableDraftContent(null), false);
});

test("writeWorking rejects oversized or empty content", async () => {
  const { draftsDir } = await makeTempDirs();
  await seedDraft(draftsDir, GENERATED);
  await assert.rejects(() => writeWorking(draftsDir, ""), /草案内容无效/);
  await assert.rejects(
    () => writeWorking(draftsDir, "x".repeat(MAX_DRAFT_CONTENT + 1)),
    /草案内容无效/,
  );
  const { working } = await readDraft(draftsDir);
  assert.equal(working, GENERATED, "拒绝的写入不得改动既有草案");
});
