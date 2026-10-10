const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontendDirectory = __dirname;
const html = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const css = fs.readFileSync(path.join(frontendDirectory, "style.css"), "utf8");
const renderer = fs.readFileSync(path.join(frontendDirectory, "renderer.js"), "utf8");
const main = fs.readFileSync(path.join(frontendDirectory, "main.cjs"), "utf8");
const floating = fs.readFileSync(path.join(frontendDirectory, "floating.html"), "utf8");
const index = fs.readFileSync(path.join(frontendDirectory, "index.html"), "utf8");
const packageManifest = JSON.parse(
  fs.readFileSync(path.join(frontendDirectory, "package.json"), "utf8"),
);

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
    /collaborationRequestActive \|\|[\s\S]*?brainToolExecutionActive[\s\S]*?!collaborationModelReady[\s\S]*?enabledCount === 0/,
  );
  assert.match(
    renderer,
    /`\$\{enabledCount\} \/ \$\{collaborationRoles\.length\} 个角色已启用`/,
  );
});

test("voice preferences and user-selected image analysis are visible, local-first controls", () => {
  assert.match(html, /id="voice-muted"/);
  assert.match(html, /id="voice-playback-rate"/);
  assert.match(html, /id="voice-playback-volume"/);
  assert.match(html, /id="voice-preferences-reset"/);
  assert.match(html, /id="image-button"[^>]*title="选择一张图片，单次分析"/);
  assert.match(renderer, /function applyVoicePreferences\(audio\)/);
  assert.match(renderer, /localStorage\.setItem\(VOICE_PREFERENCES_KEY/);
  assert.match(renderer, /window\.companion\.synthesize\(text, selectedVoice\)/);
  assert.match(renderer, /getCharacterSynthesisVoice\(\)/);
  assert.match(index, /voice-playback\.js[\s\S]*renderer\.js/);
  assert.ok(packageManifest.build.files.includes("voice-playback.js"));
  assert.ok(packageManifest.build.files.includes("avatar-display.js"));
  assert.match(renderer, /translatorVoiceSelect\.append\(option\)/);
  assert.match(renderer, /无法读取本地声线目录/);
  assert.match(main, /showOpenDialog/);
  assert.match(main, /\/v1\/vision\/analyze/);
  assert.match(main, /X-Moling-Vision-Consent/);
  assert.match(main, /createHmac\([\s\S]*?"sha256"/);
  assert.match(renderer, /possible_interpretations/);
  assert.match(renderer, /模型看错了/);
});

test("floating character presentation follows current affect and rejects stale updates", () => {
  assert.match(main, /ipcMain\.handle\("companion:set-affect", async[\s\S]*?pushCharacterToFloating\(\)/);
  assert.match(main, /updateVersion !== floatingCharacterUpdateVersion/);
  assert.match(main, /getAvatarCandidates\(\{/);
  assert.match(main, /avatarFallbackDataUrl: portraitDataUrls\[1\]/);
  assert.match(floating, /characterUpdateVersion/);
  assert.match(floating, /image\.onerror = \(\) => \{[\s\S]*?updateVersion !== characterUpdateVersion/);
  assert.match(floating, /image\.removeAttribute\("src"\)/);
  assert.match(floating, /模拟状态 · \$\{character\.moodLabel\}/);
  assert.match(index, /id="avatar-display-mode"/);
  assert.match(index, /value="follow">跟随模拟状态切换立绘/);
  assert.match(index, /value="base">固定显示基础立绘/);
  assert.match(renderer, /AVATAR_DISPLAY_MODE_KEY/);
  assert.match(renderer, /setAvatarDisplayMode\(nextMode\)/);
  assert.match(main, /companion:set-avatar-display-mode/);
});

test("plans can be cleared honestly and offer a review-first offline mini-game task", () => {
  assert.match(html, /id="brain-plan-clear"[^>]*>清除计划 · 停止后续步骤/);
  assert.match(html, /id="mini-game-plan"[^>]*>共创一个小游戏/);
  assert.match(
    renderer,
    /正在执行的步骤可通过观察面板的“停止当前步骤”请求中断/,
  );
  assert.match(renderer, /计划清除前已批准的当前步骤已完成/);
  assert.match(renderer, /停止当前步骤/);
  assert.doesNotMatch(renderer, /当前已批准的单步工具调用无法中断/);
  assert.match(renderer, /const requestVersion = \+\+avatarLoadVersion/);
  assert.match(renderer, /requestVersion === avatarLoadVersion/);
  assert.match(renderer, /不加载外部资源或联网/);
  assert.match(renderer, /绝不覆盖已有文件/);
  assert.match(renderer, /create_project_file/);
});

test("micro-story is local, branching, reversible, pausable, and disposable", () => {
  assert.match(html, /id="micro-story-start"[^>]*>一起走一段微故事/);
  assert.match(html, /id="micro-story"[^>]*hidden/);
  for (const id of [
    "micro-story-choices",
    "micro-story-back",
    "micro-story-pause",
    "micro-story-restart",
    "micro-story-exit",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(renderer, /const microStoryNodes = \{/);
  assert.match(renderer, /microStoryHistory\.push\(microStoryNode\)/);
  assert.match(renderer, /microStoryNode = microStoryHistory\.pop\(\)/);
  assert.match(renderer, /microStoryPaused = !microStoryPaused/);
  assert.match(renderer, /resetMicroStory\(true\)/);
  assert.match(renderer, /不调用模型、不联网，也不会保存为记忆/);
  assert.match(css, /\.micro-story-choice:hover:not\(:disabled\)/);
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

test("chat replies expose evidence and user-controlled correction actions", () => {
  assert.match(renderer, /查看本次回答依据/);
  assert.match(renderer, /本轮输入/);
  assert.match(renderer, /纠正理解/);
  assert.match(renderer, /给我另一种解释/);
  assert.match(renderer, /这次不要记住/);
  assert.match(renderer, /attachReplyTools\(pending, result\.evidence\)/);
  const sendMessage = renderer.match(/async function sendMessage\(text\) \{([\s\S]*?)\n\}/)?.[1] || "";
  assert.doesNotMatch(sendMessage, /reflectOnConversation/);
  assert.match(html, /聊天不会自动触发复盘/);
  assert.match(css, /\.reply-tools\s*\{/);
});

test("image analysis classifies the image type and offers read/organize/list actions", () => {
  assert.match(renderer, /const IMAGE_TYPE_LABELS = \{/);
  assert.match(renderer, /图片类型：\$\{IMAGE_TYPE_LABELS/);
  assert.match(renderer, /为你朗读这段分析/);
  assert.match(renderer, /帮你整理信息/);
  assert.match(renderer, /列出可见内容/);
  assert.match(renderer, /analysis\.append\(analysisActions\)/);
  assert.match(css, /\.image-analysis-type/);
});

test("character studio offers an 8-emotion portrait tour with a voice sample", () => {
  assert.match(html, /id="emotion-tour-start"/);
  assert.match(html, /id="emotion-tour-voice"/);
  assert.match(html, /情绪巡演预览/);
  assert.match(renderer, /async function startEmotionTour\(\)/);
  assert.match(renderer, /async function showEmotionTourStep\(index\)/);
  assert.match(renderer, /emotionTourTimer = setInterval/);
  assert.match(renderer, /2200\);/);
  assert.match(renderer, /async function emotionTourVoiceSample\(\)/);
  assert.match(renderer, /getCharacterSynthesisVoice\(\)/);
  assert.match(css, /\.emotion-tour\s*\{/);
  assert.match(css, /\.emotion-tour-actions\s*\{/);
});

test("external partner reviews require a local preview and per-run confirmation", () => {
  assert.match(html, /默认只使用本地主引擎/);
  assert.match(html, /id="partners-external-options"/);
  assert.match(html, /id="partners-preview"/);
  assert.match(renderer, /正在本机准备脱敏评审内容；尚未向外部发送/);
  assert.match(renderer, /确认发送给所选伙伴并开始评审/);
  assert.match(renderer, /partnersEvaluate\(\s*scope,\s*partnerIds,\s*partnerIds\.length > 0/);
  assert.match(renderer, /已取消；没有向外部伙伴发送评审内容/);
  assert.match(main, /external_consent: externalConsent/);
  assert.match(main, /\/v1\/partners\/preview/);
  assert.match(main, /"\/v1\/partners\/evaluate": \["POST"\]/);
  assert.match(main, /"\/v1\/partners\/status": \["GET"\]/);
});

test("assistant messages carry a mood-aware avatar that refreshes on affect change", () => {
  assert.match(renderer, /refreshMessageAvatar\(avatar\)/);
  assert.match(renderer, /refreshAllMessageAvatars\(\)/);
  assert.match(renderer, /const portraits = window\.MolingAvatarDisplay\.getAvatarCandidates/);
  assert.match(renderer, /portraitIndex < portraits\.length/);
  assert.match(renderer, /message-avatar-fallback/);
  assert.match(css, /\.message-avatar \{/);
  assert.match(css, /\.message\.assistant \.message-body/);
});

test("avatars breathe, speak, and carry mood-tinted glow without external deps", () => {
  assert.match(css, /@keyframes message-speaking/);
  assert.match(css, /\.message-avatar\.listening/);
  assert.match(css, /\[data-mood="happy"\]/);
  assert.match(css, /\[data-mood="curious"\]/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(renderer, /messageAvatar\?\.classList\.add\("listening"\)/);
  assert.match(renderer, /messageAvatar\?\.classList\.remove\("listening"\)/);
  assert.match(renderer, /characterDisplay\.dataset\.mood = state\.mood/);
  assert.match(renderer, /avatarNode\.dataset\.mood = mood/);
});

test("assistant bubbles take mood-tinted borders and thinking avatars pulse while pending", () => {
  assert.match(renderer, /message\.dataset\.mood = affectMood\?\.value \|\| "calm"/);
  assert.match(renderer, /message\.dataset\.mood = affectMood\?\.value \|\| "calm"/);
  assert.match(css, /\.message\.assistant\[data-mood="happy"\]/);
  assert.match(css, /\.message\.assistant\[data-mood="curious"\]/);
  assert.match(css, /@keyframes message-thinking/);
  assert.match(css, /\.message\.pending \.message-avatar/);
});
