const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontendDirectory = __dirname;
const html = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const css = fs.readFileSync(path.join(frontendDirectory, "style.css"), "utf8");
const renderer = fs.readFileSync(path.join(frontendDirectory, "renderer.js"), "utf8");
const main = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");

test("collapsed navigation keeps an accessible new-chat action and distinct workspaces", () => {
  assert.match(
    html,
    /<button class="new-chat" id="new-chat" type="button" aria-label="新对话" title="新对话">/,
  );
  assert.match(html, /<span class="new-chat-icon" aria-hidden="true">＋<\/span>/);
  assert.match(html, /<span class="new-chat-label">新对话<\/span>/);

  for (const [id, label, icon] of [
    ["chat-workspace", "和墨灵聊天", "聊"],
    ["translator-workspace", "文本翻译器", "译"],
    ["collaboration-workspace", "智能体协作", "协"],
    ["gallery-workspace", "墨灵的作品集", "藏"],
  ]) {
    const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const escapedIcon = icon.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.match(
      html,
      new RegExp(
        `<button[^>]*id="${id}"[^>]*aria-label="${escapedLabel}"[^>]*>[\\s\\S]*?<span class="workspace-icon" aria-hidden="true">${escapedIcon}</span>[\\s\\S]*?<span class="workspace-label">${escapedLabel}</span>`,
      ),
    );
  }

  const compactNavigation = css.match(/@media \(max-width: 900px\) \{([\s\S]*)$/);
  assert.ok(compactNavigation, "compact navigation breakpoint exists");
  assert.match(compactNavigation[1], /\.new-chat\s*\{[\s\S]*?width:\s*44px/);
  assert.doesNotMatch(compactNavigation[1], /\.new-chat\s*\{[^}]*display:\s*none/);
  assert.match(compactNavigation[1], /\.workspace-icon\s*\{[\s\S]*?font-size:\s*12px/);
  assert.match(
    compactNavigation[1],
    /\.workspace-label,\s*\.sidebar-bottom > span:last-child\s*\{\s*display:\s*none/,
  );
  assert.doesNotMatch(compactNavigation[1], /\.conversation-label\s*\{/);
  assert.match(css, /\.new-chat\[hidden\]\s*\{\s*display:\s*none;\s*\}/);
  assert.match(
    renderer,
    /chatWorkspaceButton\.setAttribute\(\s*"aria-pressed",\s*String\(isChat\)\s*\)/,
  );
  assert.match(
    renderer,
    /galleryWorkspaceButton\.setAttribute\(\s*"aria-pressed",\s*String\(isGallery\)\s*\)/,
  );
});

test("collaboration feedback reports UI-measured request round-trip time", () => {
  assert.match(renderer, /const requestStartedAt = performance\.now\(\)/);
  assert.match(renderer, /formatDurationMs\(performance\.now\(\) - requestStartedAt\)/);
  assert.match(renderer, /请求往返 \$\{requestDuration\}/);
  assert.match(renderer, /function formatDurationMs\(durationMs\)/);
});

test("collaboration actions require a ready local model and show the enabled-role count", () => {
  assert.match(html, /<details class="collaboration-role-settings">/);
  assert.doesNotMatch(html, /<details class="collaboration-role-settings" open>/);
  assert.match(html, /id="collaboration-role-count">正在加载…<\/span>/);
  assert.match(html, /id="brain-plan-submit" type="button" disabled/);
  assert.match(html, /id="collaboration-submit" type="submit" disabled>等待本机模型就绪/);
  assert.match(
    renderer,
    /status\.model_status === "configured" && modelStatus\.modelAvailable/,
  );
  assert.match(
    renderer,
    /collaborationRequestActive \|\| !collaborationModelReady \|\| enabledCount === 0/,
  );
  assert.match(
    renderer,
    /`\$\{enabledCount\} \/ \$\{collaborationRoles\.length\} 个角色已启用`/,
  );
});

test("starting a plan or collaboration clears stale results from the other flow", () => {
  assert.match(
    renderer,
    /collaborationStatus\.textContent = "本地协作伙伴正在分别评审，随后由墨灵综合…";\s*collaborationStatus\.classList\.remove\("error"\);\s*collaborationSynthesis\.hidden = true;\s*brainPlan\.hidden = true;/,
  );
  assert.match(
    renderer,
    /collaborationStatus\.textContent = "墨灵正在整理目标、权限和可验证步骤…";\s*collaborationStatus\.classList\.remove\("error"\);\s*brainPlan\.hidden = true;\s*activeBrainPlan = undefined;\s*collaborationSynthesis\.hidden = true;\s*collaborationResults\.replaceChildren\(\);/,
  );
});

test("brain plans stay bound to the exact task used to create them", () => {
  assert.match(html, /id="brain-plan-target"/);
  assert.match(renderer, /function updateBrainPlanTaskState\(\)/);
  assert.match(
    renderer,
    /collaborationTask\.value\.trim\(\) !== activeBrainTask/,
  );
  assert.match(
    renderer,
    /brain-step-execute, \.brain-observation-verify/,
  );
  assert.match(
    renderer,
    /目标已修改，请重新生成计划后再执行或核验/,
  );
  assert.match(
    renderer,
    /计划目标已修改；请重新生成计划后再申请工具读取/,
  );
  assert.match(
    renderer,
    /execute\.addEventListener\("click", \(\) => executeBrainStep\(index\)\)/,
  );
  assert.match(
    renderer,
    /const planIsStale = updateBrainPlanTaskState\(\);\s*for \(const candidate of plan\.memory_candidates\)/,
  );
  assert.match(
    renderer,
    /button\.dataset\.busy = "true";\s*button\.disabled = true;\s*updateBrainStepStatus\([\s\S]*?isCreate \? "等待创建审批" : "等待审批"[\s\S]*?status\.setAttribute\("role", "status"\);\s*status\.setAttribute\("aria-live", "polite"\);\s*try \{\s*const result = await window\.companion\.executeAgentTool/,
  );
  assert.match(
    renderer,
    /collaborationTask\.addEventListener\("input", updateBrainPlanTaskState\)/,
  );
});

test("brain execution shows step states and explicit retry actions", () => {
  assert.match(
    renderer,
    /stepStatus\.dataset\.state = step\.tool\s*\?\s*step\.tool === "create_project_file"\s*\?\s*"permission"\s*:\s*"planned"/,
  );
  assert.match(renderer, /updateBrainStepStatus\([\s\S]*?isCreate \? "等待创建审批" : "等待审批"/);
  assert.match(renderer, /updateBrainStepStatus\(stepIndex, "rejected", "已拒绝"\)/);
  assert.match(renderer, /updateBrainStepStatus\(stepIndex, "observed", "已读取 · 待核验"\)/);
  assert.match(renderer, /updateBrainStepStatus\(stepIndex, "verifying", "核验中"\)/);
  assert.match(renderer, /confirmed: \["confirmed", "核验符合"\]/);
  assert.match(renderer, /uncertain: \["uncertain", "证据不足"\]/);
  assert.match(renderer, /not_met: \["not-met", "未满足"\]/);
  assert.match(renderer, /isCreate \? "创建失败 · 可重试" : "读取失败 · 可重试"/);
  assert.match(renderer, /updateBrainStepStatus\(stepIndex, "verification-error", "核验失败 · 可重试"\)/);
  assert.match(renderer, /button\.textContent =[\s\S]*?"重试读取项目清单"/);
  assert.match(renderer, /verifyButton\.textContent = "重试核验"/);
  assert.match(renderer, /brainObservationPanels\[stepIndex\]/);
  assert.match(css, /\.brain-step-status\[data-state="observed"\],[\s\S]*?\.brain-step-status\[data-state="confirmed"\]/);
  assert.match(css, /\.brain-step-status\[data-state="verification-error"\]/);
});

test("new project files show the exact proposal and require one-time native approval", () => {
  assert.match(renderer, /项目内路径：\$\{step\.arguments\.path\}\\n\\n\$\{step\.arguments\.content\}/);
  assert.match(renderer, /预览并申请创建新文件/);
  assert.match(renderer, /step\.risk !== "requires_permission"/);
  assert.match(renderer, /status\.textContent = "新文件已创建，并已回读确认内容一致。"/);
  assert.match(renderer, /button\.dataset\.terminal = "true"/);
  assert.match(main, /create_project_file: "在项目中创建新文本文件"/);
  assert.match(main, /完整路径：\$\{requestedTarget\}/);
  assert.match(main, /以下为将写入的完整内容：/);
  assert.match(main, /buttons: \["本次允许", "拒绝"\]/);
  assert.match(main, /if \(approval\.response !== 0\)/);
});
