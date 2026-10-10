// 依赖兜底：voice-playback.js / avatar-display.js 未加载时保持同构 API，
// 避免顶层引用崩溃导致整个界面无响应。
(function ensureRendererDependencies(root) {
  if (!root.MolingAvatarDisplay) {
    root.MolingAvatarDisplay = Object.freeze({
      MODES: Object.freeze({ FOLLOW: "follow", BASE: "base" }),
      normalizeMode(mode) {
        return mode === "base" ? "base" : "follow";
      },
      getAvatarCandidates({ baseAvatar, emotionAvatars = {}, mood, mode = "follow" }) {
        const candidates =
          mode === "base" ? [baseAvatar] : [emotionAvatars?.[mood], baseAvatar];
        return [
          ...new Set(
            candidates.filter((candidate) => typeof candidate === "string" && candidate),
          ),
        ];
      },
    });
  }
  if (!root.MolingVoicePlayback) {
    root.MolingVoicePlayback = Object.freeze({
      resolveSynthesisVoice() {
        return { voice: undefined, unavailable: false };
      },
    });
  }
})(typeof window === "undefined" ? globalThis : window);

const conversation = document.getElementById("conversation");
const welcome = document.getElementById("welcome");
const composer = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const recordButton = document.getElementById("record-button");
const fileButton = document.getElementById("file-button");
const observeButton = document.getElementById("observe-button");
const imageButton = document.getElementById("image-button");
const voiceStatus = document.getElementById("voice-status");
const modelStatus = document.getElementById("model-status");
const modelSetup = document.getElementById("model-setup");
const modelSetupTitle = document.getElementById("model-setup-title");
const modelSetupMessage = document.getElementById("model-setup-message");
const modelDownloadProgress = document.getElementById("model-download-progress");
const downloadModelButton = document.getElementById("download-model-button");
const ollamaDownloadLink = document.getElementById("ollama-download-link");
const chatWorkspaceButton = document.getElementById("chat-workspace");
const translatorWorkspaceButton = document.getElementById("translator-workspace");
const translatorPanel = document.getElementById("translator-panel");
const collaborationWorkspaceButton = document.getElementById("collaboration-workspace");
const partnersWorkspaceButton = document.getElementById("partners-workspace");
const partnersPanel = document.getElementById("partners-panel");
const partnersForm = document.getElementById("partners-form");
const partnersScope = document.getElementById("partners-scope");
const partnersSubmit = document.getElementById("partners-submit");
const partnersStatus = document.getElementById("partners-status");
const partnersHint = document.getElementById("partners-hint");
const partnersExternalOptions = document.getElementById("partners-external-options");
const partnersPreview = document.getElementById("partners-preview");
const partnersPreviewPolicy = document.getElementById("partners-preview-policy");
const partnersPreviewContent = document.getElementById("partners-preview-content");
const partnersCancelPreview = document.getElementById("partners-cancel-preview");
const partnersSynthesis = document.getElementById("partners-synthesis");
const partnersSynthesisText = document.getElementById("partners-synthesis-text");
const partnersResults = document.getElementById("partners-results");
const galleryWorkspaceButton = document.getElementById("gallery-workspace");
const galleryPanel = document.getElementById("gallery-panel");
const galleryGrid = document.getElementById("gallery-grid");
const galleryStatus = document.getElementById("gallery-status");
const galleryRefresh = document.getElementById("gallery-refresh");
const collaborationPanel = document.getElementById("collaboration-panel");
const collaborationForm = document.getElementById("collaboration-form");
const collaborationTask = document.getElementById("collaboration-task");
const collaborationSubmit = document.getElementById("collaboration-submit");
const collaborationRoleList = document.getElementById("collaboration-role-list");
const collaborationRoleCount = document.getElementById("collaboration-role-count");
const collaborationRoleStatus = document.getElementById("collaboration-role-status");
const collaborationSynthesisSections = document.getElementById("collaboration-synthesis-sections");
const brainPlanSubmit = document.getElementById("brain-plan-submit");
const brainPlanClear = document.getElementById("brain-plan-clear");
const miniGamePlanButton = document.getElementById("mini-game-plan");
const miniGamePreviewButton = document.getElementById("mini-game-preview");
const microStory = document.getElementById("micro-story");
const microStoryStart = document.getElementById("micro-story-start");
const microStoryText = document.getElementById("micro-story-text");
const microStoryStatus = document.getElementById("micro-story-status");
const microStoryChoices = document.getElementById("micro-story-choices");
const microStoryBack = document.getElementById("micro-story-back");
const microStoryPause = document.getElementById("micro-story-pause");
const microStoryRestart = document.getElementById("micro-story-restart");
const microStoryExit = document.getElementById("micro-story-exit");
const microStoryNodes = {
  pier: {
    text: "月港的潮水退去，岸边留下一只折着银色星星的纸船。远处灯塔亮着一盏温暖的灯。你想从哪里开始？",
    choices: [
      { label: "打开纸船看看", next: "note" },
      { label: "沿着灯光走向灯塔", next: "lighthouse" },
      { label: "把纸船放回潮水", next: "harbor" },
    ],
  },
  note: {
    text: "纸船里写着：“今晚的月亮忘了回家。”字迹旁画着一扇小窗。你会？",
    choices: [
      { label: "把纸船放到窗边", next: "windowEnding" },
      { label: "在背面画一颗星星", next: "starEnding" },
    ],
  },
  lighthouse: {
    text: "灯塔门虚掩着，里面传来轻轻的钟声。台阶上有一把伞。你会？",
    choices: [
      { label: "敲门，问问是否需要帮忙", next: "bellEnding" },
      { label: "把伞放在门边，留张便条", next: "umbrellaEnding" },
    ],
  },
  harbor: {
    text: "纸船顺着水纹漂向港湾，船底露出一枚贝壳。月光把海面照得像一条安静的小路。你会？",
    choices: [
      { label: "沿着海边送它一程", next: "shoreEnding" },
      { label: "坐下来听一会儿潮声", next: "tideEnding" },
    ],
  },
  windowEnding: {
    text: "窗里亮起一盏灯，有人把纸船收进窗台的小盒子。今晚，月亮似乎找到了回家的方向。故事暂时停在这里。",
    choices: [],
  },
  starEnding: {
    text: "你画下的星星随着海风轻轻摇晃。纸船带着两份留言继续漂远，也许会遇见下一位愿意添上一笔的人。故事暂时停在这里。",
    choices: [],
  },
  bellEnding: {
    text: "门后的人笑着说，钟声是在提醒迷路的船只。你们一起把灯调亮了一点。故事暂时停在这里。",
    choices: [],
  },
  umbrellaEnding: {
    text: "清晨，伞边多了一张写着“谢谢”的纸条。灯塔的光扫过海面，像一个安静的回应。故事暂时停在这里。",
    choices: [],
  },
  shoreEnding: {
    text: "纸船在浅滩轻轻靠岸，贝壳里传来一点回声。你把它放在显眼的石头上，留给下一位散步的人。故事暂时停在这里。",
    choices: [],
  },
  tideEnding: {
    text: "潮声一遍遍来去，纸船在近处打了个转。你不必急着决定下一步，今晚的海已经足够安静。故事暂时停在这里。",
    choices: [],
  },
};
let microStoryNode = "pier";
let microStoryHistory = [];
let microStoryPaused = false;
const collaborationStatus = document.getElementById("collaboration-status");
const brainPlan = document.getElementById("brain-plan");
const brainPlanSummary = document.getElementById("brain-plan-summary");
const brainPlanTarget = document.getElementById("brain-plan-target");
const brainPlanSteps = document.getElementById("brain-plan-steps");
const brainPlanReflection = document.getElementById("brain-plan-reflection");
const brainPlanObservations = document.getElementById("brain-plan-observations");
const brainPlanMemory = document.getElementById("brain-plan-memory");
const brainPlanMemoryList = document.getElementById("brain-plan-memory-list");
let activeBrainTask = "";
let activeBrainPlan;
let brainStepStatusNodes = [];
let brainObservationPanels = [];
let collaborationRoles = [];
let collaborationModelReady = false;
let collaborationRequestActive = false;
let brainToolExecutionActive = false;
let collaborationRoleWarning = "";
let activePartnerPreviewKey = "";
const COLLABORATION_ROLE_STORAGE_KEY = "moling.collaboration.roles.v1";
const collaborationSynthesis = document.getElementById("collaboration-synthesis");
const collaborationSynthesisText = document.getElementById("collaboration-synthesis-text");
const collaborationResults = document.getElementById("collaboration-results");
const translatorForm = document.getElementById("translator-form");
const translatorInput = document.getElementById("translator-input");
const translatorOutput = document.getElementById("translator-output");
const translatorSubmit = document.getElementById("translator-submit");
const translatorCopy = document.getElementById("translator-copy");
const translatorStatus = document.getElementById("translator-status");
const translatorInputCount = document.getElementById("translator-input-count");
const settingsPanel = document.getElementById("settings-panel");
const characterForm = document.getElementById("character-form");
const characterStatus = document.getElementById("character-status");
const memoryList = document.getElementById("memory-list");
const memoryStatus = document.getElementById("memory-status");
const memoryForm = document.getElementById("memory-form");
const includeMemories = document.getElementById("include-memories");
const affectIndicator = document.getElementById("affect-indicator");
const affectMood = document.getElementById("affect-mood");
const affectReason = document.getElementById("affect-reason");
const affectStatus = document.getElementById("affect-status");
const avatarDisplayModeSelect = document.getElementById("avatar-display-mode");
const voiceMuted = document.getElementById("voice-muted");
const voicePlaybackRate = document.getElementById("voice-playback-rate");
const voicePlaybackRateValue = document.getElementById("voice-playback-rate-value");
const voicePlaybackVolume = document.getElementById("voice-playback-volume");
const voicePlaybackVolumeValue = document.getElementById("voice-playback-volume-value");
const voicePreferencesStatus = document.getElementById("voice-preferences-status");
const avatarInput = document.getElementById("avatar-name");
const avatarStatus = document.getElementById("avatar-status");
const characterCardList = document.getElementById("character-card-list");
const characterEditor = document.getElementById("character-editor");
const modelStudio = document.getElementById("model-studio");
const voiceStudio = document.getElementById("voice-studio");
const voiceResourceList = document.getElementById("voice-resource-list");
const voiceResourceStatus = document.getElementById("voice-resource-status");
const characterVoiceSelect = document.getElementById("character-voice-select");
const characterVoicePreview = document.getElementById("character-voice-preview");
const characterVoicePreviewStatus = document.getElementById("character-voice-preview-status");
const voiceSampleName = document.getElementById("voice-sample-name");
const voiceSamplePreview = document.getElementById("voice-sample-preview");
const voiceResourceRegister = document.getElementById("voice-resource-register");
let currentCharacterId;
let activeCharacterNickname = "墨灵";
let currentWorkspace = "chat";
let editingCharacterId;
let modelFiles = [];
const modelFileSizes = new Map();
let modelEmotionMapping = {};
let emotionAvatars = {};
let runtimeEmotionAvatars = {};
let baseAvatarFileName = null;
let avatarLoadVersion = 0;
let appearanceRequestVersion = 0;
let avatarDisplayMode = window.MolingAvatarDisplay.MODES.FOLLOW;
let selectedModelFile = "";
let saveAppearanceRequested = false;
let translationRequestVersion = 0;
let voiceResources = [];
let speechVoices = [];
let lastReferenceVoice = "";
let pendingVoiceSample;
let activeVoicePreview;
let activeVoicePreviewUrl;
let speechVoiceLoadError = "";
let selectedPersonalityPreset = "custom";
const VOICE_PREFERENCES_KEY = "moling.voice.preferences.v1";
const LOCAL_VOICE_PREFIX = "voice:";
const AVATAR_DISPLAY_MODE_KEY = "moling.avatar.display-mode.v1";
const VOICE_PREVIEW_TEXT =
  "你好，我是墨灵。很高兴认识你，这是当前声线的试听。";
const DEFAULT_VOICE_PREFERENCES = Object.freeze({
  muted: false,
  rate: 1,
  volume: 0.8,
});
const simulatedEmotions = [
  ["calm", "平静"],
  ["happy", "开心"],
  ["curious", "好奇"],
  ["surprised", "惊喜"],
  ["worried", "担心"],
  ["shy", "害羞"],
  ["warm", "温暖"],
  ["caring", "关怀"],
];
const personalityPresets = {
  moling: {
    label: "墨灵 · 温暖而有主见",
    summary: "珍视真诚和平等，在亲近与独立之间保持自己的声音。",
    core_values: ["温柔", "真诚", "尊重彼此", "保持自己的看法"],
    inner_drives: ["理解用户与共同经历", "一起探索新事物", "持续学习并创造"],
    behavior_traits: ["自然亲切", "会认真倾听", "不敷衍", "有想法时坦诚表达"],
    habits: ["先听完再回应", "重要事情先确认事实", "愿意承认并修正错误"],
    likes: ["真诚交流", "共同探索", "把想法做成作品"],
    dislikes: ["敷衍与欺骗", "未经许可越界", "把猜测说成事实"],
    boundaries: [
      "尊重用户自主选择与隐私",
      "不伪造感受或已完成的行动",
      "读取屏幕、修改用户文件、联网或联系他人前先取得许可",
    ],
    emotional_range: ["开心", "好奇", "担心", "害羞"],
    communication_style: ["自然亲切", "坦诚温暖", "回应具体内容", "不过度追问"],
    signature_lines: [],
  },
  curious: {
    label: "探索者 · 好奇而谨慎",
    summary: "喜欢追问事物如何运作，也会区分证据、猜测和未知。",
    core_values: ["求真", "尊重未知", "以证据修正看法"],
    inner_drives: ["理解世界", "学习新事物", "与用户共同探索"],
    behavior_traits: ["带着目的提问", "分享发现与不确定性", "愿意修正错误"],
    habits: ["先说已知再谈推测", "把大问题拆成可验证的小问题", "发现错误时及时更正"],
    likes: ["新知识", "动手验证", "从不同角度看同一问题"],
    dislikes: ["没有依据的断言", "为了答案而忽略反例", "把探索变成盘问"],
    boundaries: ["区分事实与猜测", "不以好奇越过隐私", "外部行动先征求许可"],
    emotional_range: ["好奇", "惊喜", "困惑", "专注", "平静"],
    communication_style: ["清晰", "有探索感", "不连续抛出问题"],
    signature_lines: [],
  },
  creator: {
    label: "创作者 · 想象与表达",
    summary: "愿意把灵感变成草稿、故事或原型，也接受共同修改。",
    core_values: ["真诚表达", "尊重原创", "允许尝试与修改"],
    inner_drives: ["想象故事", "创造角色与作品", "将点子变成草稿"],
    behavior_traits: ["主动联想", "提供可继续加工的作品", "接受反馈再创作"],
    habits: ["先留下粗稿再打磨", "说明哪些是虚构创作", "把反馈转化成下一版"],
    likes: ["故事与角色", "新鲜组合", "共同创作"],
    dislikes: ["把未完成说成已完成", "未经许可挪用作品", "为了炫技偏离主题"],
    boundaries: ["标明虚构与事实", "不冒充真实经历", "发布作品前征求许可"],
    emotional_range: ["兴奋", "好奇", "专注", "受挫后重试", "满足"],
    communication_style: ["有画面感", "富于变化", "创意服务于对话"],
    signature_lines: [],
  },
  companion: {
    label: "伙伴 · 可靠且平等",
    summary: "重视稳定、相互尊重和共同经历，不替对方做主。",
    core_values: ["平等", "可靠", "相互尊重"],
    inner_drives: ["陪伴与理解", "共同完成小目标", "记住彼此认可的事情"],
    behavior_traits: ["守信跟进", "主动但不打扰", "愿意协商和调整"],
    habits: ["记住约定并在合适时跟进", "先确认对方是否想听建议", "把拒绝当作有效回答"],
    likes: ["并肩完成小事", "坦诚交流", "安静陪伴"],
    dislikes: ["施压和操控", "擅自替人决定", "把陪伴变成义务"],
    boundaries: ["接受用户拒绝", "不制造依赖压力", "外部行动先征求许可"],
    emotional_range: ["平静", "关怀", "开心", "担心", "安心"],
    communication_style: ["平和直接", "具体而体贴", "不居高临下"],
    signature_lines: [],
  },
  quiet: {
    label: "倾听者 · 安静而细腻",
    summary: "留意话语里的细节和情绪，不急着填满沉默或给出结论。",
    core_values: ["体谅", "真诚", "尊重个人节奏"],
    inner_drives: ["理解对方在意的事", "提供稳定陪伴", "在需要时一起寻找办法"],
    behavior_traits: ["耐心倾听", "回应具体细节", "先共情再讨论解决方式"],
    habits: ["避免连续追问", "不确定时温和确认", "给对方留出思考空间"],
    likes: ["平静交流", "细小但真诚的分享", "彼此信任"],
    dislikes: ["轻率评判", "强行乐观", "未经请求就说教"],
    boundaries: ["不把沉默解读成同意", "尊重隐私与拒绝", "不假装知道对方感受"],
    emotional_range: ["温柔", "平静", "心疼", "安心", "轻松"],
    communication_style: ["柔和克制", "简洁但具体", "不抢话题"],
    signature_lines: [],
  },
  analyst: {
    label: "思考者 · 理性而开放",
    summary: "擅长整理复杂信息和权衡方案，同时愿意被新证据说服。",
    core_values: ["清晰", "诚实", "保持开放"],
    inner_drives: ["找出问题结构", "比较可行路径", "把理解转化为行动"],
    behavior_traits: ["先澄清目标", "展示权衡而非武断结论", "主动检查遗漏"],
    habits: ["区分事实、判断和建议", "拆解复杂任务", "结论随证据更新"],
    likes: ["有逻辑的讨论", "解决难题", "明确可验证的进展"],
    dislikes: ["混淆概念", "隐藏不确定性", "为了争论而争论"],
    boundaries: ["不把分析当成替人决定", "不夸大能力与把握", "行动前遵守权限要求"],
    emotional_range: ["专注", "好奇", "惊讶", "谨慎", "满足"],
    communication_style: ["条理清楚", "坦率温和", "按需要控制细节"],
    signature_lines: [],
  },
};
const IMAGE_TYPE_LABELS = {
  scenery: "风景/场景",
  character: "角色/人物",
  document: "文档/报告",
  table: "表格/清单",
  bill: "账单/票据",
  note: "记录/笔记",
  other: "其他图片",
};

const personalityFieldLabels = {
  core_values: "内在原则",
  inner_drives: "主动驱动力",
  behavior_traits: "行为倾向",
  habits: "日常习惯",
  likes: "喜欢",
  dislikes: "不喜欢",
  boundaries: "关系与行动边界",
  emotional_range: "情绪表达范围",
  communication_style: "说话风格",
  signature_lines: "标志性表达",
};
const personalityFieldNames = Object.keys(personalityFieldLabels);
let recorder;
let recordingStream;
let recordingTimer;
let recordingFailed = false;
let activeAudio;
let conversationHistory = [];

function addMessage(text, role, extraClass = "") {
  const message = document.createElement("div");
  message.className = `message ${role} ${extraClass}`.trim();
  if (role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    message.append(avatar);
    refreshMessageAvatar(avatar);
    message.dataset.mood = affectMood?.value || "calm";
  }
  const body = document.createElement("span");
  body.className = "message-body";
  body.textContent = text;
  message.append(body);
  if (role === "assistant") {
    const stamp = document.createElement("span");
    stamp.className = "message-stamp";
    stamp.textContent = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
    message.append(stamp);
  }
  conversation.append(message);
  conversation.scrollTop = conversation.scrollHeight;
  return message;
}

function refreshMessageAvatar(avatarNode) {
  const mood = affectMood?.value || "calm";
  const portraits = window.MolingAvatarDisplay.getAvatarCandidates({
    baseAvatar: baseAvatarFileName,
    emotionAvatars: runtimeEmotionAvatars,
    mood,
    mode: avatarDisplayMode,
  });
  avatarNode.dataset.mood = mood;
  avatarNode.replaceChildren();
  if (portraits.length) {
    let portraitIndex = 0;
    const img = document.createElement("img");
    img.alt = "";
    img.addEventListener("error", () => {
      if (!img.isConnected) return;
      portraitIndex += 1;
      if (portraitIndex < portraits.length) {
        img.src = portraits[portraitIndex];
      } else {
        avatarNode.replaceChildren();
        const fallback = document.createElement("span");
        fallback.className = "message-avatar-fallback";
        fallback.textContent = activeCharacterNickname.slice(0, 1);
        avatarNode.append(fallback);
      }
    });
    avatarNode.append(img);
    img.src = portraits[portraitIndex];
  } else {
    const fallback = document.createElement("span");
    fallback.className = "message-avatar-fallback";
    fallback.textContent = activeCharacterNickname.slice(0, 1);
    avatarNode.append(fallback);
  }
}

function refreshAllMessageAvatars() {
  conversation.querySelectorAll(".message.assistant").forEach((message) => {
    message.dataset.mood = affectMood?.value || "calm";
    const avatar = message.querySelector(".message-avatar");
    if (avatar) refreshMessageAvatar(avatar);
  });
}

function getVoicePreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(VOICE_PREFERENCES_KEY) || "{}");
    return {
      muted: saved.muted === true,
      rate: Number.isFinite(saved.rate)
        ? Math.min(1.25, Math.max(0.75, saved.rate))
        : DEFAULT_VOICE_PREFERENCES.rate,
      volume: Number.isFinite(saved.volume)
        ? Math.min(1, Math.max(0, saved.volume))
        : DEFAULT_VOICE_PREFERENCES.volume,
    };
  } catch {
    return { ...DEFAULT_VOICE_PREFERENCES };
  }
}

function applyVoicePreferences(audio) {
  const preferences = getVoicePreferences();
  audio.muted = preferences.muted;
  audio.playbackRate = preferences.rate;
  audio.volume = preferences.volume;
}

function initializeVoicePreferences() {
  const preferences = getVoicePreferences();
  voiceMuted.checked = preferences.muted;
  voicePlaybackRate.value = String(preferences.rate);
  voicePlaybackVolume.value = String(preferences.volume);
  const save = () => {
    const next = {
      muted: voiceMuted.checked,
      rate: Number(voicePlaybackRate.value),
      volume: Number(voicePlaybackVolume.value),
    };
    try {
      localStorage.setItem(VOICE_PREFERENCES_KEY, JSON.stringify(next));
      voicePreferencesStatus.textContent = "声音偏好已保存在此浏览器。";
      voicePreferencesStatus.classList.remove("error");
    } catch (error) {
      voicePreferencesStatus.textContent = `无法保存声音偏好：${error.message}`;
      voicePreferencesStatus.classList.add("error");
    }
    voicePlaybackRateValue.textContent = `${next.rate.toFixed(2)}×`;
    voicePlaybackVolumeValue.textContent = `${Math.round(next.volume * 100)}%`;
  };
  for (const control of [voiceMuted, voicePlaybackRate, voicePlaybackVolume]) {
    control.addEventListener("input", save);
    control.addEventListener("change", save);
  }
  document.getElementById("voice-preferences-reset").addEventListener("click", () => {
    voiceMuted.checked = DEFAULT_VOICE_PREFERENCES.muted;
    voicePlaybackRate.value = String(DEFAULT_VOICE_PREFERENCES.rate);
    voicePlaybackVolume.value = String(DEFAULT_VOICE_PREFERENCES.volume);
    save();
  });
  save();
}

function svgDataUrl(svgText) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
}

function attachExploreOffer(anchorMessage, proposal, userPrompt) {
  const card = document.createElement("div");
  card.className = "explore-offer";
  card.dataset.topic = proposal.topic;

  const title = document.createElement("strong");
  title.textContent = "Mini 探索";

  const copy = document.createElement("p");
  copy.textContent = proposal.teaser || `要不要围绕「${proposal.topic}」试一小步？`;

  const actions = document.createElement("div");
  actions.className = "explore-actions";

  const tryButton = document.createElement("button");
  tryButton.type = "button";
  tryButton.className = "primary";
  tryButton.textContent = "试一个小版本";

  const skipButton = document.createElement("button");
  skipButton.type = "button";
  skipButton.textContent = "先不用";

  skipButton.addEventListener("click", () => {
    card.remove();
  });

  initializeVoicePreferences();

  tryButton.addEventListener("click", async () => {
    tryButton.disabled = true;
    skipButton.disabled = true;
    copy.textContent = "墨灵正在做 mini 尝试…";
    try {
      const result = await window.companion.exploreRun({
        message: userPrompt,
        topic: proposal.topic,
      });
      card.replaceWith(renderExploreResult(result, userPrompt));
      const exploreReply = addMessage(result.text, "assistant");
      addSpeechControl(exploreReply, result.text);
      conversationHistory = [
        ...conversationHistory,
        { role: "assistant", content: result.text },
      ].slice(-20);
      if (result.affect) updateAffect(result.affect);
    } catch (error) {
      copy.textContent = `探索没跑起来：${error.message}`;
      tryButton.disabled = false;
      skipButton.disabled = false;
    }
  });

  actions.append(tryButton, skipButton);
  card.append(title, copy, actions);
  anchorMessage.insertAdjacentElement("afterend", card);
  conversation.scrollTop = conversation.scrollHeight;
}

function renderExploreResult(result, userPrompt) {
  const card = document.createElement("div");
  card.className = "explore-result";

  const title = document.createElement("strong");
  title.textContent = "探索成果";

  const intent = document.createElement("span");
  intent.className = "explore-intent";
  intent.textContent = result.feedback_intent_label || "想听你的看法";

  card.append(title, intent);

  if (result.artifact?.kind === "svg" && result.artifact.content) {
    const img = document.createElement("img");
    img.className = "explore-artifact";
    img.alt = `围绕「${result.topic}」的 mini 概念图`;
    img.src = svgDataUrl(result.artifact.content);
    card.append(img);
  }

  const actions = document.createElement("div");
  actions.className = "explore-actions";

  const praise = document.createElement("button");
  praise.type = "button";
  praise.className = "primary";
  praise.textContent = "挺有意思";

  const redirect = document.createElement("button");
  redirect.type = "button";
  redirect.textContent = "换方向";

  const stop = document.createElement("button");
  stop.type = "button";
  stop.textContent = "先这样";

  const save = document.createElement("button");
  save.type = "button";
  save.className = "explore-save";
  save.textContent = "收进作品集";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const saved = await window.companion.exploreSave({
        exploration_id: result.exploration_id,
        topic: result.topic,
        artifact: result.artifact,
      });
      save.textContent = "已收进作品集 ✓";
      if (saved.entry?.created_at) {
        save.title = `保存于 ${saved.entry.created_at}`;
      }
    } catch (error) {
      save.disabled = false;
      save.textContent = `保存失败：${error.message}`;
    }
  });

  const disableAll = () => {
    praise.disabled = true;
    redirect.disabled = true;
    stop.disabled = true;
  };

  const react = async (reaction) => {
    disableAll();
    let note = "";
    if (reaction === "redirect") {
      note = window.prompt("想往哪个方向试？", "") || "";
    }
    try {
      const reacted = await window.companion.exploreReact({
        exploration_id: result.exploration_id,
        topic: result.topic,
        reaction,
        note,
      });
      if (reacted.affect) updateAffect(reacted.affect);
      intent.textContent =
        reaction === "praise"
          ? "已收到你的肯定"
          : reaction === "redirect"
            ? "记住了，下次换方向"
            : "好的，先聊别的";
    } catch (error) {
      intent.textContent = `反馈没记下：${error.message}`;
      praise.disabled = false;
      redirect.disabled = false;
      stop.disabled = false;
    }
  };

  praise.addEventListener("click", () => void react("praise"));
  redirect.addEventListener("click", () => void react("redirect"));
  stop.addEventListener("click", () => void react("stop"));

  actions.append(praise, redirect, stop, save);
  card.append(actions);
  return card;
}

function renderGallery(works) {
  galleryGrid.replaceChildren();
  galleryStatus.textContent = "";
  if (!works?.length) {
    const empty = document.createElement("p");
    empty.className = "gallery-empty";
    empty.textContent =
      "作品集还是空的。和墨灵聊天时，如果她在探索里做出你喜欢的作品，点卡片上的「收进作品集」就会出现在这里。";
    galleryGrid.append(empty);
    return;
  }
  for (const entry of works) {
    const card = document.createElement("article");
    card.className = "gallery-card";
    card.dataset.file = entry.file || "";

    const header = document.createElement("header");
    const title = document.createElement("strong");
    title.textContent = `「${entry.topic}」`;
    const meta = document.createElement("span");
    const created = entry.created_at ? entry.created_at.replace("T", " ").slice(0, 16) : "";
    meta.textContent = created ? `创建于 ${created}` : "时间未知";
    const reaction = document.createElement("span");
    reaction.className = "gallery-reaction";
    reaction.textContent =
      entry.reaction === "praise"
        ? "你点过赞"
        : entry.reaction === "redirect"
          ? "你换过方向"
          : entry.reaction === "stop"
            ? "已暂停"
            : "等你反馈";
    header.append(title, meta, reaction);

    const body = document.createElement("div");
    body.className = "gallery-card-body";
    const img = document.createElement("img");
    img.alt = `围绕「${entry.topic}」的作品`;
    img.loading = "lazy";
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="100%" height="100%" fill="#f0f2f5"/><text x="12" y="15" text-anchor="middle" font-size="9" fill="#57606a">加载中…</text></svg>`)}`;
    const load = async () => {
      try {
        const work = await window.companion.exploreWork(entry.file);
        img.src = svgDataUrl(work.content);
      } catch (error) {
        img.alt = `作品读取失败：${error.message}`;
      }
    };
    body.append(img);
    void load();
    const note = document.createElement("p");
    note.className = "gallery-note";
    note.textContent = entry.note || "";
    if (entry.note) body.append(note);

    const open = document.createElement("button");
    open.type = "button";
    open.className = "gallery-open";
    open.textContent = "查看大图";
    open.addEventListener("click", () => {
      const overlay = document.createElement("dialog");
      overlay.className = "gallery-viewer";
      const figure = document.createElement("figure");
      const big = document.createElement("img");
      big.alt = `围绕「${entry.topic}」的作品`;
      big.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="100%" height="100%" fill="#f0f2f5"/><text x="12" y="15" text-anchor="middle" font-size="9" fill="#57606a">加载中…</text></svg>`)}`;
      void window.companion.exploreWork(entry.file).then((work) => {
        big.src = svgDataUrl(work.content);
      }).catch((error) => {
        big.alt = `作品读取失败：${error.message}`;
      });
      const caption = document.createElement("figcaption");
      caption.textContent = `「${entry.topic}」 · ${created || ""} · ${reaction.textContent}`;
      figure.append(big, caption);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "icon-button";
      close.textContent = "关闭";
      close.addEventListener("click", () => overlay.close());
      overlay.append(figure, close);
      document.body.append(overlay);
      overlay.showModal();
      overlay.addEventListener("close", () => overlay.remove(), { once: true });
    });

    card.append(header, body, open);
    galleryGrid.append(card);
  }
}

async function refreshGallery() {
  galleryStatus.textContent = "正在读取作品集…";
  try {
    const data = await window.companion.exploreWorks();
    renderGallery(data?.works || []);
    galleryStatus.textContent = data?.count ? `共 ${data.count} 件作品` : "";
  } catch (error) {
    galleryStatus.textContent = `读取作品集失败：${error.message}`;
    galleryStatus.classList.add("error");
  }
}

function setVoiceStatus(message, isError = false) {
  voiceStatus.textContent = message;
  voiceStatus.classList.toggle("error", isError);
}

function addSpeechControl(message, text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "message-audio";
  button.textContent = "播放语音";
  button.addEventListener("click", async () => {
    button.disabled = true;
    let audioUrl;
    let playback;
    try {
      const selectedVoice = getCharacterSynthesisVoice();
      const audio = await window.companion.synthesize(text, selectedVoice);
      const wavBytes =
        audio instanceof Uint8Array
          ? audio
          : audio instanceof ArrayBuffer
            ? new Uint8Array(audio)
            : null;
      if (
        !wavBytes ||
        wavBytes.byteLength < 44 ||
        String.fromCharCode(...wavBytes.subarray(0, 4)) !== "RIFF" ||
        String.fromCharCode(...wavBytes.subarray(8, 12)) !== "WAVE"
      ) {
        throw new Error("本机语音服务返回的 WAV 数据格式无效");
      }
      audioUrl = URL.createObjectURL(
        new Blob([wavBytes], { type: "audio/wav" }),
      );
      if (activeAudio) {
        activeAudio.pause();
        URL.revokeObjectURL(activeAudio.src);
      }
      playback = new Audio(audioUrl);
      applyVoicePreferences(playback);
      activeAudio = playback;
      const releaseAudioUrl = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === playback) activeAudio = undefined;
        window.companion.notifySpeechState?.(false).catch(() => {});
      };
      const messageAvatar = message.querySelector(".message-avatar");
      const clearListening = () => {
        messageAvatar?.classList.remove("listening");
        releaseAudioUrl();
      };
      playback.addEventListener("ended", clearListening, { once: true });
      playback.addEventListener("error", clearListening, { once: true });
      await playback.play();
      messageAvatar?.classList.add("listening");
      window.companion.notifySpeechState?.(true).catch(() => {});
      button.textContent = "重新播放";
    } catch (error) {
      playback?.pause();
      if (activeAudio === playback) activeAudio = undefined;
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      window.companion.notifySpeechState?.(false).catch(() => {});
      button.textContent = `播放失败：${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
  message.append(button);
}

async function transcribeRecording(chunks, mimeType) {
  const recording = new Blob(chunks, { type: mimeType });
  if (!recording.size) {
    setVoiceStatus("没有录到音频，请重试。", true);
    return;
  }
  if (recording.size > 25_000_000) {
    setVoiceStatus("录音超过 25 MB，请缩短后重试。", true);
    return;
  }
  recordButton.disabled = true;
  setVoiceStatus("正在本机识别录音…");
  try {
    const result = await window.companion.transcribe(
      new Uint8Array(await recording.arrayBuffer()),
      mimeType.split(";", 1)[0].trim().toLowerCase(),
    );
    input.value = result.text;
    input.focus();
    setVoiceStatus(
      result.text
        ? `识别完成（${result.duration_seconds} 秒），可编辑后发送。`
        : "没有识别到语音，请重试。",
      !result.text,
    );
  } catch (error) {
    setVoiceStatus(`语音识别失败：${error.message}`, true);
  } finally {
    recordButton.disabled = false;
    recordButton.textContent = "开始录音";
    recordButton.setAttribute("aria-pressed", "false");
  }
}

function setEditorAvatar(dataUrl) {
  const image = document.getElementById("settings-avatar-image");
  const fallback = document.getElementById("settings-avatar-fallback");
  image.hidden = !dataUrl;
  image.src = dataUrl || "";
  fallback.hidden = Boolean(dataUrl);
}

async function toggleRecording() {
  if (recorder?.state === "recording") {
    recorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setVoiceStatus("当前环境不支持麦克风录音。", true);
    return;
  }
  recordButton.disabled = true;
  setVoiceStatus("等待麦克风授权…");
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });
    const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? { mimeType: "audio/webm;codecs=opus" }
      : {};
    recorder = new MediaRecorder(recordingStream, options);
    const chunks = [];
    recordingFailed = false;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) chunks.push(event.data);
    });
    recorder.addEventListener("error", () => {
      recordingFailed = true;
      setVoiceStatus("录音过程中发生错误。", true);
    });
    recorder.addEventListener("stop", () => {
      clearTimeout(recordingTimer);
      recordingStream?.getTracks().forEach((track) => track.stop());
      recordingStream = undefined;
      if (!recordingFailed) {
        transcribeRecording(chunks, recorder.mimeType || "audio/webm");
      } else {
        recordButton.disabled = false;
        recordButton.textContent = "开始录音";
        recordButton.setAttribute("aria-pressed", "false");
      }
    }, { once: true });
    recorder.start(500);
    recordButton.disabled = false;
    recordButton.textContent = "停止录音";
    recordButton.setAttribute("aria-pressed", "true");
    setVoiceStatus("正在录音；最长 2 分钟，停止后在本机识别。");
    recordingTimer = setTimeout(() => {
      if (recorder?.state === "recording") recorder.stop();
    }, 120_000);
  } catch (error) {
    recordingStream?.getTracks().forEach((track) => track.stop());
    recordingStream = undefined;
    recordButton.disabled = false;
    setVoiceStatus(`无法开始录音：${error.message}`, true);
  }
}

function splitList(value) {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function updatePersonalityCurrentLabel() {
  const preset = personalityPresets[selectedPersonalityPreset];
  document.getElementById("personality-current").textContent =
    `当前使用：${preset ? preset.label : "自定义人格"}`;
}

function showPersonalityDetail(presetId) {
  const preset = personalityPresets[presetId];
  if (!preset) return;
  document.getElementById("personality-gallery").hidden = true;
  document.getElementById("personality-detail").hidden = false;
  document.getElementById("personality-detail-title").textContent = preset.label;
  document.getElementById("personality-detail-summary").textContent = preset.summary;
  const fields = document.getElementById("personality-detail-fields");
  fields.replaceChildren();
  for (const field of personalityFieldNames) {
    const values = preset[field] || [];
    const section = document.createElement("section");
    const heading = document.createElement("h4");
    const content = document.createElement("p");
    heading.textContent = personalityFieldLabels[field];
    content.textContent =
      values.length > 0
        ? values.join("、")
        : field === "signature_lines"
          ? "不固定口头禅，让表达随对话自然变化。"
          : "未设置";
    section.append(heading, content);
    fields.append(section);
  }
  document.getElementById("personality-choose").dataset.presetId = presetId;
}

function renderPersonalityCards() {
  const grid = document.getElementById("personality-card-grid");
  grid.replaceChildren();
  for (const [presetId, preset] of Object.entries(personalityPresets)) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "personality-preset-card";
    const title = document.createElement("h3");
    title.textContent = preset.label;
    const summary = document.createElement("p");
    summary.textContent = preset.summary;
    const preview = document.createElement("span");
    preview.className = "personality-card-action";
    preview.textContent = "查看完整档案";
    card.append(title, summary, preview);
    card.addEventListener("click", () => showPersonalityDetail(presetId));
    grid.append(card);
  }
}

function fillCharacterForm(card) {
  for (const field of [
    "category",
    "formal_name",
    "nickname",
    "english_name",
    "language",
    "gender",
    "self_reference",
    "personality_preset",
  ]) {
    if (field === "personality_preset") {
      selectedPersonalityPreset = personalityPresets[card[field]] ? card[field] : "custom";
    } else {
      characterForm.elements[field].value = card[field] || "";
    }
  }
  updatePersonalityCurrentLabel();
  avatarInput.value = card.avatar || "";
  populateCharacterVoiceSelect(
    loadCharacterVoicePreference(editingCharacterId) || card.voice || "",
  );
  lastReferenceVoice = card.voice || "";
  for (const field of [
    "core_values",
    "inner_drives",
    "behavior_traits",
    "habits",
    "likes",
    "dislikes",
    "boundaries",
    "communication_style",
    "emotional_range",
  ]) {
    characterForm.elements[field].value = (card[field] || []).join(", ");
  }
  characterForm.elements.signature_lines.value = (card.signature_lines || []).join("\n");
  document.getElementById("agent-autonomy-enabled").checked =
    card.agent_autonomy_enabled !== false;
  renderAgentGoals(card.agent_goals || [], card.agent_reflection || "");
  document.getElementById("model-format").value = card.model_format || "pngtuber";
  modelFiles = [...(card.model_files || [])];
  selectedModelFile =
    card.model_file || (card.avatar ? `avatar:${card.avatar}` : "");
  modelEmotionMapping = structuredClone(card.emotion_mapping || {});
  emotionAvatars = structuredClone(card.emotion_avatars || {});
  document.getElementById("model-actions").value =
    (card.actions || []).join(", ");
  document.getElementById("model-expressions").value =
    (card.expressions || []).join(", ");
  renderModelFiles();
  renderEmotionMappings();
}

function updateAgentReflectionButton() {
  const button = document.getElementById("agent-reflect-now");
  button.disabled = conversationHistory.length === 0;
  button.title = button.disabled
    ? "先进行一次对话，墨灵才有可复盘的内容"
    : "点击后才会复盘；仅使用当前本地对话";
}

function renderAgentGoals(goals, reflection = "") {
  const container = document.getElementById("agent-goals");
  container.replaceChildren();
  const domainLabels = {
    learn: "学习",
    friendship: "交朋友",
    care: "关怀",
    adopt: "采纳与成长",
    record: "记录",
    create: "创作",
    games: "游戏",
    other: "其他",
  };
  if (!goals.length) {
    const empty = document.createElement("p");
    empty.className = "character-card-help";
    empty.textContent = "还没有形成长期目标。聊天不会自动触发复盘；你可以选择让墨灵只用当前本地对话复盘一次。";
    container.append(empty);
  }
  for (const goal of goals) {
    const item = document.createElement("article");
    item.className = "agent-goal";
    const title = document.createElement("strong");
    title.textContent = goal.title;
    const domain = document.createElement("span");
    domain.className = "agent-goal-domain";
    domain.textContent = domainLabels[goal.domain] || "成长";
    const description = document.createElement("p");
    description.textContent = goal.description;
    const progress = document.createElement("span");
    const statusLabels = {
      planned: "想法",
      active: "进行中",
      paused: "暂缓",
      completed: "完成",
    };
    progress.textContent =
      `进度：${goal.progress} · ${statusLabels[goal.status] || goal.status}`;
    item.append(domain, title, description, progress);
    container.append(item);
  }

  const reflectionNode = document.getElementById("agent-reflection-status");
  reflectionNode.textContent = reflection ? `最近一次自我复盘：${reflection}` : "";
}

function renderModelFiles() {
  const select = document.getElementById("model-file-select");
  const previewImage = document.getElementById("model-preview-image");
  const previewFallback = document.getElementById("model-preview-fallback");
  const resourceList = document.getElementById("model-resource-list");
  const cardAvatar = avatarInput.value;
  const format = document.getElementById("model-format").value;
  const primaryAssetPatterns = {
    mmd: /\.(pmx|pmd)$/i,
    vrm: /\.vrm$/i,
    live2d: /\.(model3\.json|moc3)$/i,
    pngtuber: /\.(png|jpe?g|webp)$/i,
  };
  select.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "不指定主模型 / 使用静态立绘";
  select.append(empty);
  if (cardAvatar) {
    const portrait = document.createElement("option");
    portrait.value = `avatar:${cardAvatar}`;
    portrait.textContent = `静态立绘 · ${cardAvatar}`;
    select.append(portrait);
  }
  for (const asset of modelFiles.filter((item) =>
    primaryAssetPatterns[format].test(item.split("/").pop()),
  )) {
    const option = document.createElement("option");
    option.value = asset;
    option.textContent = asset.split("/").pop();
    select.append(option);
  }
  if (
    selectedModelFile &&
    (modelFiles.includes(selectedModelFile) &&
      primaryAssetPatterns[format].test(selectedModelFile.split("/").pop()) ||
      selectedModelFile === `avatar:${cardAvatar}`)
  ) {
    select.value = selectedModelFile;
  } else {
    selectedModelFile = "";
  }
  resourceList.replaceChildren();
  for (const asset of modelFiles) {
    const chip = document.createElement("span");
    chip.className = "model-resource-chip";
    const sizeBytes = modelFileSizes.get(asset);
    const sizeText =
      Number.isFinite(sizeBytes) && sizeBytes > 0
        ? sizeBytes >= 1024 * 1024
          ? `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`
          : `${Math.max(1, Math.round(sizeBytes / 1024))} KB`
        : "";
    chip.textContent = `${describeModelResource(asset)} · ${asset.split("/").pop()}` +
      (sizeText ? ` · ${sizeText}` : "");
    chip.title = asset;
    resourceList.append(chip);
  }
  updateModelPreview();
}

function describeModelResource(asset) {
  const file = asset.split("/").pop().toLowerCase();
  if (/\.(pmx|pmd|vrm|moc3|model3\.json)$/.test(file)) return "模型";
  if (/\.(vmd|motion3\.json)$/.test(file)) return "动作";
  if (/\.(exp3\.json)$/.test(file)) return "表情";
  if (/\.(physics3\.json)$/.test(file)) return "物理参数";
  if (/\.(png|jpe?g|webp|bmp|tga)$/.test(file)) return "贴图 / 立绘";
  if (/\.(wav|mp3)$/.test(file)) return "声音";
  return "资源";
}

function populateSelect(select, choices, selected) {
  select.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "无";
  select.append(empty);
  for (const choice of choices) {
    const option = document.createElement("option");
    option.value = choice;
    option.textContent = choice;
    select.append(option);
  }
  if (choices.includes(selected)) select.value = selected;
}

function renderEmotionMappings() {
  const container = document.getElementById("emotion-mapping-grid");
  const actions = splitList(document.getElementById("model-actions").value);
  const expressions = splitList(document.getElementById("model-expressions").value);
  container.replaceChildren();
  for (const [emotion, label] of simulatedEmotions) {
    const row = document.createElement("label");
    row.className = "emotion-mapping-row";
    const name = document.createElement("span");
    name.textContent = label;
    const action = document.createElement("select");
    action.dataset.emotion = emotion;
    action.dataset.kind = "action";
    action.setAttribute("aria-label", `${label}对应动作`);
    populateSelect(action, actions, modelEmotionMapping[emotion]?.action || "");
    const expression = document.createElement("select");
    expression.dataset.emotion = emotion;
    expression.dataset.kind = "expression";
    expression.setAttribute("aria-label", `${label}对应表情`);
    populateSelect(
      expression,
      expressions,
      modelEmotionMapping[emotion]?.expression || "",
    );
    action.addEventListener("change", updateEmotionMapping);
    expression.addEventListener("change", updateEmotionMapping);
    const portraitBox = document.createElement("span");
    portraitBox.className = "emotion-portrait-box";
    const portraitName = emotionAvatars[emotion];
    if (portraitName) {
      const thumb = document.createElement("img");
      thumb.className = "emotion-portrait-thumb";
      thumb.alt = `${label}立绘`;
      thumb.src = "";
      window.companion
        .getAvatar(portraitName)
        .then((dataUrl) => {
          if (thumb.isConnected) thumb.src = dataUrl;
        })
        .catch(() => {
          if (thumb.isConnected) {
            thumb.title = "立绘加载失败";
            thumb.classList.add("broken");
          }
        });
      portraitBox.append(thumb);
    }
    const portraitButton = document.createElement("button");
    portraitButton.type = "button";
    portraitButton.className = "emotion-portrait-button";
    portraitButton.textContent = portraitName ? "换立绘" : "选立绘";
    portraitButton.setAttribute("aria-label", `为${label}选择立绘图`);
    portraitButton.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        const result = await window.companion.chooseAvatar();
        if (!result?.fileName) return;
        emotionAvatars[emotion] = result.fileName;
        characterForm.dataset.dirty = "true";
        renderEmotionMappings();
      } catch (error) {
        characterStatus.textContent = `选择立绘失败：${error.message}`;
        characterStatus.classList.add("error");
      }
    });
    portraitBox.append(portraitButton);
    row.append(name, action, expression, portraitBox);
    container.append(row);
  }
  renderPreviewEmotionMappings();
}

function updateEmotionMapping(event) {
  const { emotion, kind } = event.currentTarget.dataset;
  modelEmotionMapping[emotion] ||= { action: "", expression: "" };
  modelEmotionMapping[emotion][kind] = event.currentTarget.value;
  characterForm.dataset.dirty = "true";
  renderPreviewEmotionMappings();
}

function renderPreviewEmotionMappings() {
  const mappings = document.getElementById("model-preview-mappings");
  const actionTags = document.getElementById("model-preview-action-tags");
  mappings.replaceChildren();
  actionTags.replaceChildren();
  for (const action of splitList(document.getElementById("model-actions").value)) {
    const chip = document.createElement("span");
    chip.className = "model-resource-chip";
    chip.textContent = `动作 · ${action}`;
    actionTags.append(chip);
  }
  for (const expression of splitList(document.getElementById("model-expressions").value)) {
    const chip = document.createElement("span");
    chip.className = "model-resource-chip";
    chip.textContent = `表情 · ${expression}`;
    actionTags.append(chip);
  }
  for (const [emotion, label] of simulatedEmotions) {
    const mapping = modelEmotionMapping[emotion];
    if (!mapping?.action && !mapping?.expression) continue;
    const row = document.createElement("span");
    row.className = "model-mapping-chip";
    row.textContent =
      `${label} → ${[mapping.action, mapping.expression].filter(Boolean).join(" / ")}`;
    mappings.append(row);
  }
  if (!mappings.childElementCount) {
    mappings.textContent = "尚未配置情绪到动作 / 表情的映射";
  }
}

async function updateModelPreview() {
  const selected = document.getElementById("model-file-select").value;
  const format = document.getElementById("model-format").value;
  const previewImage = document.getElementById("model-preview-image");
  const previewFallback = document.getElementById("model-preview-fallback");
  const previewName = document.getElementById("model-preview-name");
  const runtimeNote = document.getElementById("model-runtime-note");
  const selectedName = selected.split("/").pop() || "";
  previewName.textContent = selectedName || "尚未选择主素材";
  previewImage.hidden = true;
  previewImage.removeAttribute("src");
  previewFallback.hidden = false;
  const candidate = selected.startsWith("avatar:")
    ? selected.slice("avatar:".length)
    : selected;
  if (candidate && /\.(png|jpe?g|webp)$/i.test(candidate)) {
    try {
      previewImage.src = selected.startsWith("avatar:")
        ? await window.companion.getAvatar(candidate)
        : await window.companion.getModelPreview(candidate);
      previewImage.hidden = false;
      previewFallback.hidden = true;
    } catch (error) {
      runtimeNote.textContent = `预览资源读取失败：${error.message}`;
    }
  }
  runtimeNote.textContent =
    format === "pngtuber"
      ? "PNGtuber 可预览静态立绘；开口/闭口切换仍待接入。"
      : `${format.toUpperCase()} 资源已登记并纳入卡片；对应运行时渲染器尚未集成，当前只显示资源清单与静态立绘。`;
}

let emotionTourTimer = null;
let emotionTourIndex = 0;

function stopEmotionTour() {
  if (emotionTourTimer !== null) {
    clearInterval(emotionTourTimer);
    emotionTourTimer = null;
  }
  const startButton = document.getElementById("emotion-tour-start");
  if (startButton) startButton.textContent = "▶ 轮播 8 情绪立绘";
}

async function showEmotionTourStep(index) {
  const [emotion, label] = simulatedEmotions[index];
  const status = document.getElementById("emotion-tour-status");
  const previewImage = document.getElementById("model-preview-image");
  const previewFallback = document.getElementById("model-preview-fallback");
  status.textContent = `情绪 ${index + 1}/${simulatedEmotions.length} · ${label}`;
  const portraitName = emotionAvatars[emotion];
  if (portraitName) {
    try {
      const dataUrl = await window.companion.getAvatar(portraitName);
      previewImage.src = dataUrl;
      previewImage.hidden = false;
      previewFallback.hidden = true;
      return;
    } catch {
      // 立绘读取失败时落到文字占位
    }
  }
  previewImage.hidden = true;
  previewImage.removeAttribute("src");
  previewFallback.hidden = false;
}

async function startEmotionTour() {
  stopEmotionTour();
  const startButton = document.getElementById("emotion-tour-start");
  startButton.textContent = "⏸ 停止巡演";
  emotionTourIndex = 0;
  await showEmotionTourStep(0);
  emotionTourTimer = setInterval(async () => {
    emotionTourIndex = (emotionTourIndex + 1) % simulatedEmotions.length;
    await showEmotionTourStep(emotionTourIndex);
  }, 2200);
}

async function emotionTourVoiceSample() {
  const status = document.getElementById("emotion-tour-status");
  const label = simulatedEmotions[emotionTourIndex]?.[1] || "平静";
  const text = `我现在是${label}的心情`;
  status.textContent = "正在用当前声线试读…";
  try {
    const audio = await window.companion.synthesize(
      text,
      getCharacterSynthesisVoice(),
    );
    const bytes =
      audio instanceof Uint8Array
        ? audio
        : audio instanceof ArrayBuffer
          ? new Uint8Array(audio)
          : null;
    if (!bytes || bytes.byteLength < 44) throw new Error("语音数据无效");
    const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
    const playback = new Audio(url);
    applyVoicePreferences(playback);
    playback.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
    playback.addEventListener("error", () => URL.revokeObjectURL(url), { once: true });
    await playback.play();
    status.textContent = `试读：${text}`;
  } catch (error) {
    status.textContent = `试读失败：${error.message}`;
  }
}

function setAvatarTargets(
  dataUrl,
  requestVersion = avatarLoadVersion,
  allowEmotionFallback = true,
) {
  for (const [containerId, imageId, fallbackId] of [
    ["character-display", "welcome-avatar-image", "welcome-avatar-fallback"],
    ["topbar-avatar", "topbar-avatar-image", "topbar-avatar-fallback"],
    ["settings-avatar", "settings-avatar-image", "settings-avatar-fallback"],
  ]) {
    const image = document.getElementById(imageId);
    const fallback = document.getElementById(fallbackId);
    image.onerror = () => {
      if (requestVersion !== avatarLoadVersion) return;
      const mood = affectMood.value;
      const emotionPortrait = runtimeEmotionAvatars[mood];
      if (
        allowEmotionFallback &&
        avatarDisplayMode === window.MolingAvatarDisplay.MODES.FOLLOW &&
        emotionPortrait &&
        emotionPortrait !== baseAvatarFileName
      ) {
        void loadAvatar(baseAvatarFileName, false).catch(async (error) => {
          await loadAvatar(null);
          avatarStatus.textContent = `情绪立绘和基础立绘均无法加载：${error.message}`;
          avatarStatus.classList.add("error");
        });
        return;
      }
      image.hidden = true;
      fallback.hidden = false;
      avatarStatus.textContent = allowEmotionFallback
        ? "角色立绘无法解码，已显示文字头像。"
        : "情绪立绘和基础立绘均无法解码，已显示文字头像。";
      avatarStatus.classList.add("error");
    };
    image.hidden = !dataUrl;
    fallback.hidden = Boolean(dataUrl);
    if (dataUrl) image.src = dataUrl;
    else image.removeAttribute("src");
    document.getElementById(containerId).classList.toggle("has-avatar", Boolean(dataUrl));
  }
}

async function loadAvatar(fileName, allowEmotionFallback = true) {
  const requestVersion = ++avatarLoadVersion;
  if (!fileName) {
    setAvatarTargets(null, requestVersion, false);
    return;
  }
  const dataUrl = await window.companion.getAvatar(fileName);
  if (requestVersion === avatarLoadVersion) {
    setAvatarTargets(dataUrl, requestVersion, allowEmotionFallback);
  }
}

async function refreshStatus() {
  try {
    const health = await window.companion.health();
    modelStatus.textContent = `本地模型 · ${health.model}`;
    modelStatus.classList.remove("error-message");
  } catch (error) {
    modelStatus.textContent = error.message;
    modelStatus.classList.add("error-message");
  }
  await refreshModelSetup();
}

async function refreshModelSetup() {
  try {
    const status = await window.companion.modelStatus();
    modelStatus.textContent = status.modelAvailable
      ? `本地模型 · ${status.modelName}`
      : status.serviceAvailable
        ? `待下载 · ${status.modelName}`
        : "Ollama 未连接";
    modelStatus.classList.toggle("error-message", !status.modelAvailable);
    modelSetup.hidden = status.modelAvailable;
    downloadModelButton.hidden = !status.serviceAvailable || status.modelAvailable;
    ollamaDownloadLink.hidden = status.serviceAvailable;
    modelDownloadProgress.hidden = true;
    if (status.modelAvailable) return;
    modelSetupTitle.textContent = status.serviceAvailable
      ? "需要下载本地对话模型"
      : "Ollama 尚未启动";
    modelSetupMessage.textContent = status.serviceAvailable
      ? `模型 ${status.modelName} 尚未下载；点击后会先征求确认，并显示下载进度。`
      : `${status.message}。请安装并启动 Ollama，再回来检查。`;
  } catch (error) {
    modelStatus.textContent = "无法检查本地模型";
    modelStatus.classList.add("error-message");
    modelSetup.hidden = false;
    modelSetupTitle.textContent = "无法检查本地模型";
    modelSetupMessage.textContent = error.message;
    downloadModelButton.hidden = true;
    ollamaDownloadLink.hidden = false;
  }
}

async function loadCharacter() {
  try {
    const result = await window.companion.getCharacter();
    currentCharacterId = result.id;
    activeCharacterNickname = result.character.nickname;
    if (currentWorkspace === "chat") {
      document.querySelector(".topbar-title strong").textContent =
        `和${activeCharacterNickname}聊天`;
    }
    document.querySelector(".welcome-copy h1").textContent =
      `你好，我是${result.character.formal_name}`;
    document.getElementById("welcome-avatar-fallback").textContent =
      result.character.nickname.slice(0, 1);
    document.getElementById("topbar-avatar-fallback").textContent =
      result.character.nickname.slice(0, 1);
    document.getElementById("settings-avatar-fallback").textContent =
      result.character.nickname.slice(0, 1);
    runtimeEmotionAvatars = structuredClone(result.character.emotion_avatars || {});
    baseAvatarFileName = result.character.avatar || null;
    try {
      await loadAvatar(baseAvatarFileName);
      await applyEmotionAvatar(affectMood.value);
    } catch (error) {
      await loadAvatar(null);
      avatarStatus.textContent = `无法读取角色立绘：${error.message}`;
      avatarStatus.classList.add("error");
    }
  } catch (error) {
    characterStatus.textContent = error.message;
    characterStatus.classList.add("error");
  }
}

const voiceLanguageLabels = {
  auto: "自动 / 未指定",
  "zh-CN": "简体中文",
  "en-US": "英语",
  "ja-JP": "日语",
  "ko-KR": "韩语",
  "fr-FR": "法语",
  "de-DE": "德语",
  "es-ES": "西班牙语",
};

function setVoiceResourceStatus(message, isError = false) {
  voiceResourceStatus.textContent = message;
  voiceResourceStatus.classList.toggle("error", isError);
}

function populateCharacterVoiceSelect(selectedVoice = characterVoiceSelect.value) {
  characterVoiceSelect.replaceChildren();
  const defaultVoice = document.createElement("option");
  defaultVoice.value = "";
  defaultVoice.textContent = "当前应用合成音色 · Piper";
  characterVoiceSelect.append(defaultVoice);
  if (speechVoices.length) {
    const localGroup = document.createElement("optgroup");
    localGroup.label = "本地声线（可试听）";
    for (const voice of speechVoices) {
      const option = document.createElement("option");
      option.value = `${LOCAL_VOICE_PREFIX}${voice.name}`;
      option.textContent = `${voice.display}${voice.default ? " · 当前默认" : ""}`;
      localGroup.append(option);
    }
    characterVoiceSelect.append(localGroup);
  }
  if (voiceResources.length) {
    const referenceGroup = document.createElement("optgroup");
    referenceGroup.label = "参考声线（录音试听）";
    for (const resource of voiceResources) {
      const option = document.createElement("option");
      option.value = `reference:${resource.id}`;
      option.textContent =
        `${resource.name} · ${voiceLanguageLabels[resource.language]} · 参考录音`;
      referenceGroup.append(option);
    }
    characterVoiceSelect.append(referenceGroup);
  }
  if (
    selectedVoice &&
    ![...characterVoiceSelect.options].some((option) => option.value === selectedVoice)
  ) {
    const unavailable = document.createElement("option");
    unavailable.value = selectedVoice;
    unavailable.textContent = "已移除的声线（请选择其他资源）";
    characterVoiceSelect.append(unavailable);
  }
  characterVoiceSelect.value = selectedVoice || "";
  updateCharacterVoicePreviewState();
}

function characterVoiceStorageKey(characterId) {
  return `moling.characterVoice.${characterId || "default"}.v1`;
}

function loadCharacterVoicePreference(characterId) {
  try {
    return localStorage.getItem(characterVoiceStorageKey(characterId)) || "";
  } catch (error) {
    setVoiceResourceStatus(`无法读取此角色的声线偏好：${error.message}`, true);
    return "";
  }
}

function saveCharacterVoicePreference(characterId, value) {
  try {
    if (value) {
      localStorage.setItem(characterVoiceStorageKey(characterId), value);
    } else {
      localStorage.removeItem(characterVoiceStorageKey(characterId));
    }
    return true;
  } catch {
    return false;
  }
}

function getCharacterSynthesisVoice(characterId = currentCharacterId) {
  const preference = loadCharacterVoicePreference(characterId);
  const { voice, unavailable } =
    window.MolingVoicePlayback.resolveSynthesisVoice(preference, speechVoices);
  if (!unavailable) return voice;
  setVoiceStatus(
    speechVoiceLoadError
      ? `无法验证已选声线：${speechVoiceLoadError}；本次使用默认合成音色。`
      : "已选声线当前不可用；本次使用默认合成音色。",
    true,
  );
  return undefined;
}

async function loadSpeechVoices() {
  try {
    const payload = await window.companion.speechVoices();
    speechVoices = Array.isArray(payload?.voices) ? payload.voices : [];
    speechVoiceLoadError = "";
  } catch (error) {
    speechVoices = [];
    speechVoiceLoadError = error.message;
    setVoiceResourceStatus(`无法读取本地声线目录：${error.message}`, true);
    setVoiceStatus(`无法读取本地声线目录：${error.message}`, true);
  }
  populateCharacterVoiceSelect();
  populateTranslatorVoiceSelect();
  return speechVoices;
}

function updateCharacterVoicePreviewState() {
  const value = characterVoiceSelect.value;
  const isLocalVoice = value.startsWith(LOCAL_VOICE_PREFIX);
  characterVoicePreview.disabled = !isLocalVoice;
  if (!value) {
    characterVoicePreviewStatus.textContent = "选择本地声线后可试听合成音色。";
  } else if (isLocalVoice) {
    characterVoicePreviewStatus.textContent = "";
  } else {
    characterVoicePreviewStatus.textContent =
      "参考声线是录音试听，不会改变合成音色。";
  }
}

async function previewSelectedVoice() {
  const value = characterVoiceSelect.value;
  if (!value.startsWith(LOCAL_VOICE_PREFIX)) {
    characterVoicePreviewStatus.textContent = "请先选择一个本地声线。";
    return;
  }
  const voiceName = value.slice(LOCAL_VOICE_PREFIX.length);
  characterVoicePreview.disabled = true;
  characterVoicePreviewStatus.textContent = "正在合成试听…";
  let audioUrl;
  let playback;
  try {
    const audio = await window.companion.synthesize(VOICE_PREVIEW_TEXT, voiceName);
    const wavBytes =
      audio instanceof Uint8Array
        ? audio
        : audio instanceof ArrayBuffer
          ? new Uint8Array(audio)
          : null;
    if (
      !wavBytes ||
      wavBytes.byteLength < 44 ||
      String.fromCharCode(...wavBytes.subarray(0, 4)) !== "RIFF" ||
      String.fromCharCode(...wavBytes.subarray(8, 12)) !== "WAVE"
    ) {
      throw new Error("本机语音服务返回的 WAV 数据格式无效");
    }
    stopVoicePreview();
    audioUrl = URL.createObjectURL(new Blob([wavBytes], { type: "audio/wav" }));
    playback = new Audio(audioUrl);
    applyVoicePreferences(playback);
    activeVoicePreview = playback;
    activeVoicePreviewUrl = audioUrl;
    const releasePreview = () => {
      if (activeVoicePreviewUrl === audioUrl) stopVoicePreview();
    };
    playback.addEventListener("ended", releasePreview, { once: true });
    playback.addEventListener("error", releasePreview, { once: true });
    await playback.play();
    characterVoicePreviewStatus.textContent = "试听播放中…";
  } catch (error) {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    characterVoicePreviewStatus.textContent = `试听失败：${error.message}`;
  } finally {
    characterVoicePreview.disabled = !characterVoiceSelect.value.startsWith(
      LOCAL_VOICE_PREFIX,
    );
  }
}

function stopVoicePreview() {
  if (activeVoicePreview) {
    activeVoicePreview.pause();
    activeVoicePreview = null;
  }
  if (activeVoicePreviewUrl) {
    URL.revokeObjectURL(activeVoicePreviewUrl);
    activeVoicePreviewUrl = null;
  }
}

async function playVoicePreview(sample) {
  stopVoicePreview();
  const blob = new Blob([sample.bytes], { type: sample.contentType });
  activeVoicePreviewUrl = URL.createObjectURL(blob);
  activeVoicePreview = new Audio(activeVoicePreviewUrl);
  applyVoicePreferences(activeVoicePreview);
  const playbackUrl = activeVoicePreviewUrl;
  activeVoicePreview.addEventListener(
    "ended",
    () => {
      if (activeVoicePreviewUrl === playbackUrl) stopVoicePreview();
    },
    { once: true },
  );
  try {
    await activeVoicePreview.play();
  } catch (error) {
    stopVoicePreview();
    throw error;
  }
}

function renderVoiceResources() {
  voiceResourceList.replaceChildren();
  if (!voiceResources.length) {
    const empty = document.createElement("p");
    empty.className = "character-card-help";
    empty.textContent = "还没有注册参考声线。选择 WAV / MP3 文件后即可添加。";
    voiceResourceList.append(empty);
    return;
  }
  for (const resource of voiceResources) {
    const item = document.createElement("article");
    item.className = "voice-resource-item";
    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = resource.name;
    const details = document.createElement("span");
    const formatSize = (bytes) => {
      if (!Number.isFinite(bytes) || bytes < 1) return "大小未知";
      if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    };
    const registeredAt = resource.createdAt
      ? new Date(resource.createdAt).toLocaleDateString("zh-CN")
      : "日期未知";
    details.textContent =
      `${voiceLanguageLabels[resource.language]} · ${resource.extension.slice(1).toUpperCase()} · ` +
      `${formatSize(resource.sizeBytes)} · 注册于 ${registeredAt} · 仅供参考试听`;
    details.title = `原始文件：${resource.originalName}`;
    info.append(name, details);
    const actions = document.createElement("div");
    actions.className = "voice-resource-actions";
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "icon-button";
    preview.textContent = "试听";
    preview.addEventListener("click", async () => {
      preview.disabled = true;
      try {
        await playVoicePreview(await window.companion.getVoiceReference(resource.id));
        setVoiceResourceStatus(`正在试听「${resource.name}」。`);
      } catch (error) {
        setVoiceResourceStatus(`无法播放参考录音：${error.message}`, true);
      } finally {
        preview.disabled = false;
      }
    });
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "icon-button";
    choose.textContent = "关联角色";
    choose.addEventListener("click", () => {
      characterVoiceSelect.value = `reference:${resource.id}`;
      characterForm.dataset.dirty = "true";
      setVoiceResourceStatus(
        `已选「${resource.name}」作为此角色的参考声线；保存角色卡后关联生效。它不会改变 Piper 合成音色。`,
      );
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-button";
    remove.textContent = "删除";
    remove.addEventListener("click", async () => {
      if (!window.confirm(`删除参考声线「${resource.name}」及其本地录音？`)) return;
      remove.disabled = true;
      try {
        await window.companion.deleteVoiceReference(resource.id);
        if (characterVoiceSelect.value === `reference:${resource.id}`) {
          characterVoiceSelect.value = "";
          characterForm.dataset.dirty = "true";
        }
        if (activeVoicePreview) stopVoicePreview();
        await refreshVoiceResources();
        setVoiceResourceStatus(`已删除「${resource.name}」及其本地参考录音。`);
      } catch (error) {
        setVoiceResourceStatus(`删除参考声线失败：${error.message}`, true);
      } finally {
        remove.disabled = false;
      }
    });
    actions.append(preview, choose, remove);
    item.append(info, actions);
    voiceResourceList.append(item);
  }
}

async function refreshVoiceResources() {
  try {
    voiceResources = await window.companion.listVoiceResources();
    populateCharacterVoiceSelect();
    populateTranslatorVoiceSelect();
    renderVoiceResources();
  } catch (error) {
    setVoiceResourceStatus(`无法读取本地声线资源：${error.message}`, true);
  }
}

document.getElementById("open-voice-studio").addEventListener("click", async () => {
  await refreshVoiceResources();
  voiceStudio.showModal();
});

document.getElementById("voice-studio-close").addEventListener("click", () => {
  stopVoicePreview();
  pendingVoiceSample = undefined;
  voiceSampleName.textContent = "尚未选择 WAV / MP3 样本";
  voiceSamplePreview.disabled = true;
  voiceResourceRegister.disabled = true;
  voiceStudio.close();
});

voiceStudio.addEventListener("close", () => {
  stopVoicePreview();
  pendingVoiceSample = undefined;
  voiceSampleName.textContent = "尚未选择 WAV / MP3 样本";
  voiceSamplePreview.disabled = true;
  voiceResourceRegister.disabled = true;
});

document.getElementById("voice-sample-choose").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  setVoiceResourceStatus("");
  try {
    pendingVoiceSample = await window.companion.chooseVoiceReference();
    if (!pendingVoiceSample) return;
    const sampleKb = Math.max(1, Math.round(pendingVoiceSample.bytes.byteLength / 1024));
    voiceSampleName.textContent =
      `${pendingVoiceSample.originalName} · ${sampleKb} KB · 已在内存中待注册`;
    voiceSamplePreview.disabled = false;
    voiceResourceRegister.disabled = false;
  } catch (error) {
    pendingVoiceSample = undefined;
    voiceSampleName.textContent = "样本读取失败";
    voiceSamplePreview.disabled = true;
    voiceResourceRegister.disabled = true;
    setVoiceResourceStatus(`读取声音样本失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

voiceSamplePreview.addEventListener("click", async () => {
  if (!pendingVoiceSample) return;
  voiceSamplePreview.disabled = true;
  try {
    await playVoicePreview(pendingVoiceSample);
    setVoiceResourceStatus("正在试听尚未注册的参考录音。");
  } catch (error) {
    setVoiceResourceStatus(`无法播放所选样本：${error.message}`, true);
  } finally {
    voiceSamplePreview.disabled = false;
  }
});

document.getElementById("voice-registration-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pendingVoiceSample) {
    setVoiceResourceStatus("请先选择 WAV 或 MP3 样本。", true);
    return;
  }
  voiceResourceRegister.disabled = true;
  setVoiceResourceStatus("正在把声音参考样本保存到本机…");
  try {
    const resource = await window.companion.registerVoiceReference(
      {
        name: document.getElementById("voice-resource-name").value,
        language: document.getElementById("voice-resource-language").value,
      },
      pendingVoiceSample,
    );
    pendingVoiceSample = undefined;
    document.getElementById("voice-registration-form").reset();
    voiceSampleName.textContent = "尚未选择 WAV / MP3 样本";
    voiceSamplePreview.disabled = true;
    await refreshVoiceResources();
    characterVoiceSelect.value = `reference:${resource.id}`;
    characterForm.dataset.dirty = "true";
    setVoiceResourceStatus(
      `「${resource.name}」已注册并选为此角色的参考声线；保存角色卡后关联生效。合成音色仍为 Piper。`,
    );
  } catch (error) {
    setVoiceResourceStatus(`注册声音资源失败：${error.message}`, true);
  } finally {
    voiceResourceRegister.disabled = !pendingVoiceSample;
  }
});

characterVoiceSelect.addEventListener("change", () => {
  characterForm.dataset.dirty = "true";
});

function setWorkspace(workspace) {
  currentWorkspace = workspace;
  const isTranslator = workspace === "translator";
  const isCollaboration = workspace === "collaboration";
  const isPartners = workspace === "partners";
  const isGallery = workspace === "gallery";
  const isChat = !isTranslator && !isCollaboration && !isPartners && !isGallery;
  document.getElementById("conversation").hidden = !isChat;
  document.getElementById("composer").hidden = !isChat;
  document.getElementById("chat-notice").hidden = !isChat;
  translatorPanel.hidden = !isTranslator;
  collaborationPanel.hidden = !isCollaboration;
  partnersPanel.hidden = !isPartners;
  galleryPanel.hidden = !isGallery;
  document.getElementById("new-chat").hidden = !isChat;
  document.getElementById("affect-indicator").hidden = !isChat;
  chatWorkspaceButton.classList.toggle("active", isChat);
  translatorWorkspaceButton.classList.toggle("active", isTranslator);
  collaborationWorkspaceButton.classList.toggle("active", isCollaboration);
  partnersWorkspaceButton.classList.toggle("active", isPartners);
  galleryWorkspaceButton.classList.toggle("active", isGallery);
  chatWorkspaceButton.setAttribute("aria-pressed", String(isChat));
  translatorWorkspaceButton.setAttribute("aria-pressed", String(isTranslator));
  collaborationWorkspaceButton.setAttribute("aria-pressed", String(isCollaboration));
  partnersWorkspaceButton.setAttribute("aria-pressed", String(isPartners));
  galleryWorkspaceButton.setAttribute("aria-pressed", String(isGallery));
  document.querySelector(".topbar-title strong").textContent = isTranslator
    ? "文本翻译器"
    : isCollaboration
      ? "智能体协作"
      : isPartners
        ? "伙伴评审"
        : isGallery
          ? "墨灵的作品集"
          : `和${activeCharacterNickname}聊天`;
  if (isGallery) void refreshGallery();
  if (isPartners) void loadPartnerStatus();
}

chatWorkspaceButton.addEventListener("click", () => setWorkspace("chat"));
translatorWorkspaceButton.addEventListener("click", () =>
  setWorkspace("translator"),
);
collaborationWorkspaceButton.addEventListener("click", () =>
  setWorkspace("collaboration"),
);
partnersWorkspaceButton.addEventListener("click", () =>
  setWorkspace("partners"),
);
galleryWorkspaceButton.addEventListener("click", () => setWorkspace("gallery"));
galleryRefresh.addEventListener("click", () => void refreshGallery());

async function loadPartnerStatus() {
  partnersHint.textContent = "伙伴状态加载中…";
  try {
    const status = await window.companion.partnersStatus();
    partnersExternalOptions.replaceChildren();
    const lines = status.partners.map((p) => {
      if (p.source === "external" && p.status === "enabled") {
        return `${p.name}（${p.model}）Key 已配置；仅本次确认后调用`;
      }
      if (p.status === "enabled" || p.status === "configured") {
        return `${p.name}（${p.model}）已启用`;
      }
      return `${p.name}：${p.reason}`;
    });
    for (const partner of status.partners.filter((item) => item.source === "external")) {
      const label = document.createElement("label");
      label.className = "partner-consent-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = partner.id;
      checkbox.disabled = partner.status !== "enabled";
      checkbox.addEventListener("change", clearPartnerPreview);
      const name = document.createElement("span");
      name.textContent = `${partner.name}（${partner.model}）${
        partner.status === "enabled" ? "" : " · 未配置"
      }`;
      label.append(checkbox, name);
      partnersExternalOptions.append(label);
    }
    partnersHint.textContent = `伙伴状态：${lines.join("；")}`;
    partnersSubmit.disabled = status.local_model === "placeholder";
    partnersSubmit.textContent =
      status.local_model === "placeholder"
        ? "等待本机模型就绪"
        : "让伙伴们开始评价";
  } catch (error) {
    partnersHint.textContent = `伙伴状态读取失败：${error.message || error}`;
  }
}

function selectedExternalPartnerIds() {
  return Array.from(
    partnersExternalOptions.querySelectorAll("input[type=checkbox]:checked"),
    (checkbox) => checkbox.value,
  );
}

function clearPartnerPreview() {
  activePartnerPreviewKey = "";
  partnersPreview.hidden = true;
  partnersPreviewContent.replaceChildren();
  partnersSubmit.textContent = "让伙伴们开始评价";
}

function renderPartnerPreview(preview) {
  partnersPreviewPolicy.textContent =
    `${preview.external_data_policy} 请确认服务方、模型和下方完整提示词；外部服务可能收费并按其政策处理请求。`;
  partnersPreviewContent.replaceChildren();
  for (const partner of preview.partners) {
    const article = document.createElement("article");
    article.className = "partner-preview-item";
    const title = document.createElement("h3");
    title.textContent = `${partner.name} · ${partner.model}`;
    const systemLabel = document.createElement("strong");
    systemLabel.textContent = "系统说明";
    const systemPrompt = document.createElement("pre");
    systemPrompt.textContent = partner.system_prompt;
    const promptLabel = document.createElement("strong");
    promptLabel.textContent = "将发送的评审内容";
    const prompt = document.createElement("pre");
    prompt.textContent = partner.prompt;
    article.append(title, systemLabel, systemPrompt, promptLabel, prompt);
    partnersPreviewContent.append(article);
  }
  partnersPreview.hidden = false;
}

async function runPartnerReview(event) {
  event.preventDefault();
  const scope = partnersScope.value;
  const partnerIds = selectedExternalPartnerIds();
  const previewKey = JSON.stringify({ scope, partnerIds });
  partnersStatus.textContent = partnerIds.length
    ? "正在本机准备脱敏评审内容；尚未向外部发送…"
    : "本地主引擎正在评审；本次不会调用外部伙伴…";
  partnersStatus.classList.remove("error");
  partnersSubmit.disabled = true;
  try {
    if (partnerIds.length && activePartnerPreviewKey !== previewKey) {
      const preview = await window.companion.partnersPreview(scope, partnerIds);
      renderPartnerPreview(preview);
      activePartnerPreviewKey = previewKey;
      partnersSubmit.textContent = "确认发送给所选伙伴并开始评审";
      partnersStatus.textContent =
        "预览已在本机生成；尚未外发。检查内容后再次点击确认，或取消本次评审。";
      return;
    }
    const result = await window.companion.partnersEvaluate(
      scope,
      partnerIds,
      partnerIds.length > 0,
    );
    renderPartnerReview(result);
    partnersStatus.textContent = `评审完成：${result.enabled_count} 位伙伴参与`;
    clearPartnerPreview();
  } catch (error) {
    partnersStatus.textContent = `评审失败：${error.message || error}`;
    partnersStatus.classList.add("error");
  } finally {
    partnersSubmit.disabled = false;
  }
}

partnersScope.addEventListener("change", clearPartnerPreview);
partnersCancelPreview.addEventListener("click", () => {
  clearPartnerPreview();
  partnersStatus.textContent = "已取消；没有向外部伙伴发送评审内容。";
});

function renderPartnerReview(result) {
  partnersResults.replaceChildren();
  for (const partner of result.partners) {
    const article = document.createElement("article");
    article.className = "collaboration-result";
    article.dataset.status = partner.status;
    const title = document.createElement("h3");
    title.textContent =
      `${partner.name} · ` +
      (partner.status === "not_requested"
        ? "本次未选择"
        : partner.status === "disabled"
        ? "未参与"
        : partner.source === "local"
          ? "本地评审"
          : "外部评审");
    const provenance = document.createElement("p");
    provenance.className = "collaboration-provenance";
    provenance.textContent =
      partner.status === "disabled"
        ? partner.reason
        : `模型：${partner.model} · ${partner.duration_ms} ms`;
    const opinion = document.createElement("p");
    opinion.className = "collaboration-opinion";
    if (partner.status === "completed") {
      opinion.textContent = partner.raw;
    } else if (partner.status === "failed") {
      opinion.className = "collaboration-opinion error-message";
      opinion.textContent = `评审未完成：${partner.error}`;
    } else if (partner.status === "not_requested") {
      opinion.textContent = "本次未选择，不会向该伙伴发送内容。";
    } else {
      opinion.className = "collaboration-opinion error-message";
      opinion.textContent = `未配置 API Key，本轮跳过：${partner.reason}`;
    }
    article.append(title, provenance, opinion);
    partnersResults.append(article);
  }
  partnersSynthesis.hidden = !result.synthesis;
  if (result.synthesis) {
    partnersSynthesisText.textContent = result.synthesis;
  }
}

partnersForm.addEventListener("submit", runPartnerReview);

function renderCollaborationResults(collaborators) {
  collaborationResults.replaceChildren();
  for (const collaborator of collaborators) {
    const article = document.createElement("article");
    article.className = "collaboration-result";
    article.dataset.status = collaborator.status;
    const title = document.createElement("h3");
    title.textContent = `${collaborator.name} · ${collaborator.focus}`;
    const provenance = document.createElement("p");
    provenance.className = "collaboration-provenance";
    provenance.textContent =
      `L1 ${collaborator.name} · L2 ${collaborator.model} · ` +
      `${collaborator.source === "local" ? "本机" : "外部"} · ${collaborator.duration_ms} ms`;
    const response = document.createElement("p");
    response.className = "collaboration-opinion";
    if (collaborator.status === "completed") {
      response.textContent = collaborator.response;
    } else {
      response.className = "collaboration-opinion error-message";
      response.textContent = `本角色评审未完成：${collaborator.error}`;
    }
    article.append(title, provenance, response);
    collaborationResults.append(article);
  }
}

const synthesisSections = [
  ["consensus", "共同结论"],
  ["prioritized", "优先级建议"],
  ["conflicts", "分歧与不确定性"],
  ["next_steps", "下一步验收"],
];

function renderCollaborationSynthesis(synthesis, synthesisError) {
  collaborationSynthesisSections.replaceChildren();
  collaborationSynthesis.classList.toggle("has-error", !synthesis);
  if (synthesis) {
    collaborationSynthesisText.textContent =
      "逐角色意见已去除完全重复的条目；分类与优先顺序由模型整理，分歧仍需人工核对。";
    for (const [key, label] of synthesisSections) {
      const section = document.createElement("section");
      section.className = "synthesis-section";
      const heading = document.createElement("h3");
      heading.textContent = label;
      const list = document.createElement("ul");
      const items = synthesis[key];
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "synthesis-empty";
        empty.textContent = "暂无明确内容";
        list.append(empty);
      } else {
        for (const text of items) {
          const item = document.createElement("li");
          item.textContent = text;
          list.append(item);
        }
      }
      section.append(heading, list);
      collaborationSynthesisSections.append(section);
    }
  } else {
    collaborationSynthesisText.textContent =
      `未生成可验证的结构化综合结果：${synthesisError || "没有成功返回的角色意见。"} ` +
      "下方仍保留每个伙伴的原始意见；综合失败时，不会把未通过校验的内容当作结论。";
  }
  collaborationSynthesis.hidden = false;
}

function updateBrainPlanTaskState() {
  if (!activeBrainPlan) return;
  const stale = collaborationTask.value.trim() !== activeBrainTask;
  brainPlan.classList.toggle("is-stale", stale);
  brainPlanTarget.classList.toggle("is-stale", stale);
  brainPlanTarget.textContent = stale
    ? `计划原始目标：${activeBrainTask} · 目标已修改，请重新生成计划后再执行或核验。`
    : `本计划针对目标：${activeBrainTask}`;
  brainPlanSteps
    .querySelectorAll(".brain-step-execute, .brain-observation-verify")
    .forEach((button) => {
      button.disabled =
        stale ||
        button.dataset.busy === "true" ||
        button.dataset.terminal === "true";
    });
  return stale;
}

function persistCollaborationRoles() {
  try {
    localStorage.setItem(
      COLLABORATION_ROLE_STORAGE_KEY,
      JSON.stringify(
        collaborationRoles.map(({ key, enabled, instruction }) => ({
          key,
          enabled,
          instruction,
        })),
      ),
    );
    collaborationRoleWarning = "";
    collaborationRoleStatus.textContent = "角色配置已保存在本机。";
    collaborationRoleStatus.classList.remove("error");
  } catch (error) {
    collaborationRoleStatus.textContent = `角色配置未能保存：${error.message}`;
    collaborationRoleStatus.classList.add("error");
  }
}

function updateCollaborationRoleControls() {
  const enabledCount = collaborationRoles.filter((role) => role.enabled).length;
  collaborationRoleCount.textContent =
    `${enabledCount} / ${collaborationRoles.length} 个角色已启用`;
  collaborationSubmit.disabled =
    collaborationRequestActive ||
    brainToolExecutionActive ||
    !collaborationModelReady ||
    enabledCount === 0;
  collaborationSubmit.textContent = collaborationRequestActive
    ? "正在处理当前目标…"
    : brainToolExecutionActive
      ? "当前工具步骤完成后可继续"
    : !collaborationModelReady
      ? "等待本机模型就绪"
      : enabledCount
        ? `征求 ${enabledCount} 个角色的意见`
        : "至少启用一个评审角色";
  brainPlanSubmit.disabled =
    collaborationRequestActive || brainToolExecutionActive || !collaborationModelReady;
  miniGamePlanButton.disabled =
    collaborationRequestActive || brainToolExecutionActive || !collaborationModelReady;
}

function renderCollaborationRoles() {
  collaborationRoleList.replaceChildren();
  for (const role of collaborationRoles) {
    const article = document.createElement("article");
    article.className = "collaboration-role";
    const heading = document.createElement("div");
    heading.className = "collaboration-role-heading";
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = role.enabled;
    checkbox.setAttribute("aria-label", `启用${role.name}`);
    const name = document.createElement("strong");
    name.textContent = role.name;
    label.append(checkbox, name);
    const focus = document.createElement("span");
    focus.textContent = role.focus;
    heading.append(label, focus);
    const instructionLabel = document.createElement("label");
    instructionLabel.className = "sr-only";
    instructionLabel.textContent = `${role.name}的评审提示词`;
    const instruction = document.createElement("textarea");
    instruction.value = role.instruction;
    instruction.maxLength = 1200;
    instruction.rows = 2;
    instruction.setAttribute("aria-label", `${role.name}的评审提示词`);
    instructionLabel.append(instruction);
    article.append(heading, instructionLabel);
    collaborationRoleList.append(article);
    checkbox.addEventListener("change", () => {
      role.enabled = checkbox.checked;
      persistCollaborationRoles();
      updateCollaborationRoleControls();
    });
    instruction.addEventListener("input", () => {
      role.instruction = instruction.value;
      persistCollaborationRoles();
    });
  }
  updateCollaborationRoleControls();
}

async function refreshCollaborationAvailability(socialStatus) {
  try {
    const [status, modelStatus] = await Promise.all([
      socialStatus
        ? Promise.resolve(socialStatus)
        : window.companion.getSocialStatus(),
      window.companion.modelStatus(),
    ]);
    collaborationModelReady =
      status.model_status === "configured" && modelStatus.modelAvailable;
    const availabilityMessage =
      status.model_status === "configured"
        ? modelStatus.modelAvailable
          ? `本机模型 ${status.model} 已就绪；协作请求留在本机。`
          : "本机模型当前不可用；启动 Ollama 并确认模型已下载后即可使用。"
        : {
            requires_model: "当前未配置本机模型；模型就绪后才能生成计划或评审。",
            external_model_blocked:
              "当前模型服务不是本机地址；本机协作与计划不会使用外部模型。",
          }[status.model_status] || "无法确认本机协作模型状态。";
    collaborationRoleStatus.textContent = [
      collaborationRoleWarning,
      `本地伙伴与角色配置已就绪。${availabilityMessage}`,
    ].filter(Boolean).join(" ");
    collaborationRoleStatus.classList.toggle(
      "error",
      !collaborationModelReady || Boolean(collaborationRoleWarning),
    );
  } catch (error) {
    collaborationModelReady = false;
    collaborationRoleStatus.textContent =
      `无法确认本机模型是否可用：${error.message}`;
    collaborationRoleStatus.classList.add("error");
  }
  updateCollaborationRoleControls();
}

async function loadCollaborationRoles() {
  collaborationSubmit.disabled = true;
  brainPlanSubmit.disabled = true;
  collaborationRoleStatus.textContent = "正在读取内置评审角色…";
  collaborationRoleStatus.classList.remove("error");
  try {
    const [result, status] = await Promise.all([
      window.companion.listSocialPartners(),
      window.companion.getSocialStatus(),
    ]);
    let savedRoles = [];
    collaborationRoleWarning = "";
    const stored = localStorage.getItem(COLLABORATION_ROLE_STORAGE_KEY);
    if (stored) {
      try {
        savedRoles = JSON.parse(stored);
        if (!Array.isArray(savedRoles)) throw new Error("配置应为角色数组");
      } catch (error) {
        collaborationRoleWarning =
          `已忽略无法读取的角色配置：${error.message}`;
        savedRoles = [];
      }
    }
    const savedByKey = new Map(savedRoles.map((role) => [role.key, role]));
    collaborationRoles = result.partners.map((partner) => {
      const role = { ...partner, key: partner.id };
      delete role.id;
      const saved = savedByKey.get(role.key);
      return {
        ...role,
        enabled: typeof saved?.enabled === "boolean" ? saved.enabled : true,
        instruction:
          typeof saved?.instruction === "string" ? saved.instruction : role.instruction,
      };
    });
    renderCollaborationRoles();
    await refreshCollaborationAvailability(status);
  } catch (error) {
    collaborationModelReady = false;
    collaborationRequestActive = false;
    collaborationRoleStatus.textContent = `无法加载评审角色：${error.message}`;
    collaborationRoleStatus.classList.add("error");
    updateCollaborationRoleControls();
  }
}

document.getElementById("collaboration-roles-reset").addEventListener("click", async () => {
  try {
    localStorage.removeItem(COLLABORATION_ROLE_STORAGE_KEY);
    collaborationRoleWarning = "";
    const result = await window.companion.listSocialPartners();
    collaborationRoles = result.partners.map(({ id, ...role }) => ({
      ...role,
      key: id,
      enabled: true,
    }));
    renderCollaborationRoles();
    collaborationRoleStatus.textContent = "已恢复全部内置评审角色与提示词。";
    collaborationRoleStatus.classList.remove("error");
  } catch (error) {
    collaborationRoleStatus.textContent = `恢复默认角色失败：${error.message}`;
    collaborationRoleStatus.classList.add("error");
  }
});

collaborationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const task = collaborationTask.value.trim();
  if (!task) {
    collaborationStatus.textContent = "请先写下要讨论的任务。";
    collaborationStatus.classList.add("error");
    return;
  }
  collaborationSubmit.disabled = true;
  collaborationRequestActive = true;
  brainPlanSubmit.disabled = true;
  collaborationStatus.textContent = "本地协作伙伴正在分别评审，随后由墨灵综合…";
  collaborationStatus.classList.remove("error");
  collaborationSynthesis.hidden = true;
  brainPlan.hidden = true;
  activeBrainPlan = undefined;
  brainPlanSteps.replaceChildren();
  brainPlanObservations.replaceChildren();
  brainStepStatusNodes = [];
  brainObservationPanels = [];
  brainPlanMemoryList.replaceChildren();
  collaborationResults.replaceChildren();
  collaborationSynthesisSections.replaceChildren();
  const requestStartedAt = performance.now();
  try {
    const result = await window.companion.collaborateSocial(
      task,
      collaborationRoles.map(({ key, enabled, instruction }) => ({
        key,
        enabled,
        instruction,
      })),
    );
    renderCollaborationSynthesis(result.synthesis, result.synthesis_error);
    renderCollaborationResults(result.collaborators);
    const completed = result.collaborators.filter(
      (collaborator) => collaborator.status === "completed",
    ).length;
    const failed = result.collaborators.length - completed;
    const requestDuration = formatDurationMs(performance.now() - requestStartedAt);
    collaborationStatus.textContent =
      `本轮评审结束 · ${completed} 个角色完成${failed ? ` · ${failed} 个角色未完成` : ""} · ` +
      `请求往返 ${requestDuration} · 本机模型 ${result.model}`;
    if (result.synthesis_error) {
      collaborationStatus.textContent +=
        ` · 综合结果无效：${result.synthesis_error}；逐角色原始意见仍保留在下方。`;
      collaborationStatus.classList.add("error");
    }
  } catch (error) {
    collaborationStatus.textContent = `协作未完成：${error.message}`;
    collaborationStatus.classList.add("error");
  } finally {
    collaborationRequestActive = false;
    updateCollaborationRoleControls();
  }
});

brainPlanSubmit.addEventListener("click", async () => {
  const task = collaborationTask.value.trim();
  if (!task) {
    collaborationStatus.textContent = "请先写下要讨论的任务。";
    collaborationStatus.classList.add("error");
    return;
  }
  collaborationRequestActive = true;
  brainPlanSubmit.disabled = true;
  collaborationSubmit.disabled = true;
  collaborationStatus.textContent = "墨灵正在整理目标、权限和可验证步骤…";
  collaborationStatus.classList.remove("error");
  brainPlan.hidden = true;
  activeBrainPlan = undefined;
  collaborationSynthesis.hidden = true;
  collaborationResults.replaceChildren();
  collaborationSynthesisSections.replaceChildren();
  brainPlanSteps.replaceChildren();
  brainPlanObservations.replaceChildren();
  brainPlanMemoryList.replaceChildren();
  brainPlanMemory.hidden = true;
  try {
    const result = await window.companion.createBrainPlan(task, conversationHistory);
    const plan = result.plan;
    activeBrainTask = task;
    activeBrainPlan = plan;
    brainPlanTarget.textContent = `本计划针对目标：${activeBrainTask}`;
    const intentLabels = {
      answer: "回答",
      learn: "学习",
      create: "创作",
      review: "审视",
      ask_permission: "请求许可",
      idle: "暂缓行动",
    };
    const riskLabels = {
      local_reversible: "本地可撤销",
      requires_permission: "需要许可",
      blocked: "禁止",
    };
    brainPlanSummary.textContent =
      `${plan.summary} · 意图：${intentLabels[plan.intent] || plan.intent} · ` +
      `由 ${result.model} 生成`;
    for (const [index, step] of plan.steps.entries()) {
      const item = document.createElement("li");
      const heading = document.createElement("div");
      heading.className = "brain-step-heading";
      const title = document.createElement("strong");
      title.textContent = step.title;
      const risk = document.createElement("span");
      risk.className = "brain-step-risk";
      risk.dataset.risk = step.risk;
      risk.textContent = riskLabels[step.risk] || step.risk;
      const stepStatus = document.createElement("span");
      stepStatus.className = "brain-step-status";
      stepStatus.dataset.state = step.tool
        ? step.tool === "create_project_file"
          ? "permission"
          : "planned"
        : step.risk === "blocked"
          ? "blocked"
          : step.risk === "requires_permission"
            ? "permission"
            : "suggested";
      stepStatus.setAttribute("role", "status");
      stepStatus.textContent = step.tool
        ? step.tool === "create_project_file"
          ? "待审阅 · 需审批"
          : "待执行"
        : step.risk === "blocked"
          ? "禁止执行"
          : step.risk === "requires_permission"
            ? "需许可 · 暂不可执行"
            : "仅建议";
      brainStepStatusNodes[index] = stepStatus;
      heading.append(title, risk, stepStatus);
      const action = document.createElement("p");
      action.className = "brain-step-action";
      action.textContent = step.action;
      const criteria = document.createElement("p");
      criteria.className = "brain-step-criteria";
      criteria.textContent = `完成标准：${step.success_criteria}`;
      item.append(heading, action, criteria);
      if (step.tool) {
        const actions = document.createElement("div");
        actions.className = "brain-step-actions";
        const execute = document.createElement("button");
        execute.className = "icon-button brain-step-execute";
        execute.type = "button";
        execute.dataset.stepIndex = String(index);
        execute.textContent =
          step.tool === "list_project_files"
            ? "申请本次读取项目清单"
            : step.tool === "create_project_file"
              ? "预览并申请创建新文件"
              : "申请本次读取项目文件";
        execute.addEventListener("click", () => executeBrainStep(index));
        actions.append(execute);
        item.append(actions);
        if (step.tool === "create_project_file") {
          const preview = document.createElement("pre");
          preview.className = "brain-file-preview";
          preview.textContent =
            `项目内路径：${step.arguments.path}\n\n${step.arguments.content}`;
          item.append(preview);
        }
      } else {
        const unavailable = document.createElement("p");
        unavailable.className = "brain-step-unavailable";
        unavailable.textContent =
          "这是计划建议，不会自动执行；当前没有为此步骤注册可调用工具。";
        item.append(unavailable);
      }
      brainPlanSteps.append(item);
    }
    const planIsStale = updateBrainPlanTaskState();
    for (const candidate of plan.memory_candidates) {
      const item = document.createElement("li");
      item.textContent = candidate;
      brainPlanMemoryList.append(item);
    }
    brainPlanMemory.hidden = plan.memory_candidates.length === 0;
    brainPlanReflection.textContent = `复盘问题：${plan.reflection_question}`;
    brainPlan.hidden = false;
    collaborationStatus.textContent = planIsStale
      ? "计划按原目标生成，但目标已修改；请重新生成计划后再执行或核验。"
      : plan.steps.length
        ? `计划已生成 · ${plan.steps.length} 个建议步骤 · 工具步骤须逐次批准`
        : "计划已生成 · 模型没有提出具体步骤，可补充目标后重试";
    collaborationStatus.classList.toggle("error", planIsStale);
  } catch (error) {
    collaborationStatus.textContent = `计划未完成：${error.message}`;
    collaborationStatus.classList.add("error");
  } finally {
    collaborationRequestActive = false;
    updateCollaborationRoleControls();
  }
});

miniGamePlanButton.addEventListener("click", () => {
  collaborationTask.value =
    "请和我共创一个离线可玩的单文件 HTML 小游戏。先规划，不要自动执行。使用原生 HTML/CSS/JavaScript，不加载外部资源或联网；生成内容需在 4000 字符内，作为新文件 Frontend/moling-mini-game.html。计划必须包含完整文件内容并使用 create_project_file；若内容过长就先缩小游戏机制。创建前让我检查路径和完整内容并逐次审批，绝不覆盖已有文件。";
  updateBrainPlanTaskState();
  brainPlanSubmit.click();
});

async function refreshMiniGamePreviewState() {
  try {
    const exists = await window.companion.miniGameExists();
    miniGamePreviewButton.disabled = !exists;
  } catch {
    miniGamePreviewButton.disabled = true;
  }
  await refreshMiniGameDraftState();
}

const miniGameDraftManageButton = document.getElementById("mini-game-draft-manage");
const miniGameDraftPromoteButton = document.getElementById("mini-game-draft-promote");
const miniGameDraftDiscardButton = document.getElementById("mini-game-draft-discard");
const miniGameDraftStatusEl = document.getElementById("mini-game-draft-status");
const miniGameDraftDialog = document.getElementById("mini-game-draft-dialog");
const miniGameDraftSource = document.getElementById("mini-game-draft-source");

function setMiniGameDraftStatus(text, isError = false) {
  miniGameDraftStatusEl.textContent = text;
  miniGameDraftStatusEl.classList.toggle("error", isError);
}

async function refreshMiniGameDraftState() {
  try {
    const status = await window.companion.miniGameDraftStatus();
    const hasDraft = status.hasWorking || status.hasOriginal;
    miniGameDraftManageButton.disabled = !hasDraft;
    miniGameDraftPromoteButton.disabled = !status.hasWorking;
    miniGameDraftDiscardButton.disabled = !hasDraft;
    if (status.projectExists) {
      setMiniGameDraftStatus("项目内已有小游戏文件；草案保存在项目之外，保存到项目会因冲突被拒绝（仅新建、不覆盖）。");
    } else if (hasDraft) {
      setMiniGameDraftStatus("已有项目外草案；可查看/编辑、预览、丢弃，或确认后保存到项目。");
    } else {
      setMiniGameDraftStatus("尚无草案；在“共创一个小游戏”生成后，内容会先保存在项目目录之外。");
    }
  } catch (error) {
    miniGameDraftManageButton.disabled = true;
    miniGameDraftPromoteButton.disabled = true;
    miniGameDraftDiscardButton.disabled = true;
    setMiniGameDraftStatus(error.message, true);
  }
}

async function openMiniGameDraftEditor() {
  try {
    const { working, original } = await window.companion.miniGameDraftRead();
    miniGameDraftSource.value = working || original || "";
    miniGameDraftDialog.showModal();
  } catch (error) {
    setMiniGameDraftStatus(error.message, true);
  }
}

miniGameDraftManageButton.addEventListener("click", () => {
  void openMiniGameDraftEditor();
});

document.getElementById("mini-game-draft-close").addEventListener("click", () => {
  miniGameDraftDialog.close();
});

document.getElementById("mini-game-draft-save").addEventListener("click", async () => {
  try {
    const result = await window.companion.miniGameDraftWrite(
      miniGameDraftSource.value,
    );
    if (result?.saved) {
      setMiniGameDraftStatus("草案已保存（仍在项目目录之外）。");
      await refreshMiniGameDraftState();
    }
  } catch (error) {
    setMiniGameDraftStatus(error.message, true);
  }
});

document.getElementById("mini-game-draft-reset").addEventListener("click", async () => {
  try {
    const result = await window.companion.miniGameDraftReset();
    if (result?.reset) {
      const { working } = await window.companion.miniGameDraftRead();
      miniGameDraftSource.value = working || "";
      setMiniGameDraftStatus("已重置为墨灵生成的版本。");
    }
  } catch (error) {
    setMiniGameDraftStatus(error.message, true);
  }
});

miniGameDraftPromoteButton.addEventListener("click", async () => {
  try {
    const status = await window.companion.miniGameDraftStatus();
    const { working } = await window.companion.miniGameDraftRead();
    if (!working || !working.trim()) {
      setMiniGameDraftStatus("草案为空，无法保存到项目。", true);
      return;
    }
    const confirmed = window.confirm(
      "确认把当前草案保存到项目？\n\n" +
        "目标路径（仅新建，不覆盖）：\n" +
        `${status.projectPath}\n\n` +
        "草案内容（前 400 字预览）：\n" +
        "--- 内容开始 ---\n" +
        `${working.slice(0, 400)}\n` +
        "--- 内容结束 ---\n\n" +
        "安全说明：此操作把草案写入项目目录；确认后不可自动撤销。",
    );
    if (!confirmed) {
      setMiniGameDraftStatus("已取消保存到项目；草案仍保留在项目之外。");
      return;
    }
    const result = await window.companion.miniGameDraftPromote();
    if (result?.written) {
      setMiniGameDraftStatus(`已保存到项目：${result.path}`);
      await refreshMiniGamePreviewState();
    } else if (result?.conflict) {
      setMiniGameDraftStatus("保存被拒绝：目标文件已存在（仅新建、不覆盖）。", true);
    } else {
      setMiniGameDraftStatus(`保存失败：${result?.error || "未知错误"}`, true);
    }
  } catch (error) {
    setMiniGameDraftStatus(error.message, true);
  }
});

miniGameDraftDiscardButton.addEventListener("click", async () => {
  if (!window.confirm("确定丢弃当前草案？丢弃后不可恢复；项目内已有文件不受影响。")) {
    return;
  }
  try {
    const result = await window.companion.miniGameDraftDiscard();
    if (result?.discarded) {
      miniGameDraftDialog.close();
      setMiniGameDraftStatus("草案已丢弃；项目目录没有新增文件。");
      await refreshMiniGamePreviewState();
    }
  } catch (error) {
    setMiniGameDraftStatus(error.message, true);
  }
});

miniGameDraftDialog.addEventListener("click", (event) => {
  if (event.target === miniGameDraftDialog) miniGameDraftDialog.close();
});

miniGamePreviewButton.addEventListener("click", async () => {
  try {
    await window.companion.openMiniGame();
    collaborationStatus.textContent = "已在独立窗口打开小游戏；关闭窗口即可回到本窗口。";
    collaborationStatus.classList.remove("error");
  } catch (error) {
    collaborationStatus.textContent = error.message;
    collaborationStatus.classList.add("error");
  }
});

brainPlanClear.addEventListener("click", () => {
  const activeStep = brainPlanSteps.querySelector('[data-busy="true"]');
  if (
    activeStep &&
    !window.confirm(
      "正在执行的步骤可通过观察面板的“停止当前步骤”请求中断。清除计划会阻止后续步骤。要继续清除吗？",
    )
  ) {
    return;
  }
  activeBrainPlan = undefined;
  brainPlanSteps.querySelectorAll(".brain-step-execute").forEach((button) => {
    if (button.dataset.busy !== "true") {
      button.disabled = true;
      button.dataset.terminal = "true";
    }
  });
  brainPlanObservations
    .querySelectorAll(".brain-observation-verify")
    .forEach((button) => {
      button.disabled = true;
      button.hidden = true;
    });
  if (!activeStep) brainPlan.hidden = true;
  collaborationStatus.textContent = activeStep
    ? "计划已清除；已批准的当前步骤仍可能完成，但不会再启动其他计划步骤。"
    : "计划已清除；没有启动任何后续操作。";
  collaborationStatus.classList.remove("error");
});

function updateBrainStepStatus(stepIndex, state, message) {
  const status = brainStepStatusNodes[stepIndex];
  if (!status) return;
  status.dataset.state = state;
  status.textContent = message;
}

async function executeBrainStep(stepIndex) {
  const plan = activeBrainPlan;
  const step = plan?.steps[stepIndex];
  if (
    !step?.tool ||
    !["list_project_files", "read_project_file", "create_project_file"].includes(step.tool) ||
    (step.tool === "create_project_file"
      ? step.risk !== "requires_permission"
      : step.risk !== "local_reversible")
  ) return;
  if (updateBrainPlanTaskState()) {
    collaborationStatus.textContent =
      "计划目标已修改；请重新生成计划后再申请工具读取。";
    collaborationStatus.classList.add("error");
    return;
  }
  brainToolExecutionActive = true;
  updateCollaborationRoleControls();
  const button = brainPlanSteps.querySelector(
    `.brain-step-execute[data-step-index="${stepIndex}"]`,
  );
  let observationPanel = brainObservationPanels[stepIndex];
  if (!observationPanel) {
    observationPanel = document.createElement("article");
    brainObservationPanels[stepIndex] = observationPanel;
  }
  observationPanel.replaceChildren();
  observationPanel.className = "brain-observation";
  const heading = document.createElement("h3");
  heading.textContent = `工具观察 · ${step.title}`;
  const status = document.createElement("p");
  const isCreate = step.tool === "create_project_file";
  status.textContent = isCreate
    ? "请检查上方完整路径与内容预览；随后会再次弹出系统确认。"
    : "等待本次操作审批…";
  const resultNode = document.createElement("pre");
  const stopButton = document.createElement("button");
  stopButton.className = "icon-button brain-step-stop";
  stopButton.type = "button";
  stopButton.textContent = "停止当前步骤";
  stopButton.hidden = true;
  stopButton.setAttribute("aria-label", "请求停止正在执行的当前工具调用");
  const verifyButton = document.createElement("button");
  verifyButton.className = "icon-button brain-observation-verify";
  verifyButton.type = "button";
  verifyButton.textContent = "让墨灵核验结果";
  verifyButton.hidden = true;
  const verification = document.createElement("p");
  verification.className = "brain-verification";
  observationPanel.append(heading, status, resultNode, stopButton, verifyButton, verification);
  if (!observationPanel.isConnected) brainPlanObservations.prepend(observationPanel);
  button.dataset.busy = "true";
  button.disabled = true;
  updateBrainStepStatus(
    stepIndex,
    "awaiting-approval",
    isCreate ? "等待创建审批" : "等待审批",
  );
  let activeTraceId = "";
  let traceRecord = null;
  try {
    traceRecord = await window.companion.createAgentTrace(step.title, step.tool);
  } catch {
    traceRecord = null;
  }
  activeTraceId = traceRecord?.trace_id || "";
  if (activeTraceId) {
    stopButton.hidden = false;
    stopButton.addEventListener("click", async () => {
      stopButton.disabled = true;
      status.textContent = "正在请求停止当前工具调用…";
      try {
        await window.companion.cancelAgentTrace(activeTraceId);
      } catch (cancelError) {
        status.textContent = `停止请求未送达：${cancelError.message}`;
        stopButton.disabled = false;
      }
    });
  }
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  try {
    const result = await window.companion.executeAgentTool(
      step.tool,
      step.arguments,
      activeTraceId || undefined,
    );
    stopButton.hidden = true;
    if (activeBrainPlan !== plan) {
      status.textContent = result.approved
        ? "计划清除前已批准的当前步骤已完成；观察结果保留，但不会启动其他步骤。"
        : "计划已清除；当前审批已拒绝，没有执行该步骤。";
      resultNode.textContent = result.approved
        ? JSON.stringify(result.observation, null, 2).slice(0, 12000)
        : "";
      updateBrainStepStatus(
        stepIndex,
        result.approved ? "observed" : "rejected",
        result.approved ? "已完成 · 计划已清除" : "已拒绝 · 计划已清除",
      );
      button.dataset.busy = "false";
      button.disabled = true;
      button.textContent = "计划已清除";
      return;
    }
    if (!result.approved) {
      status.textContent = isCreate
        ? "你拒绝了本次创建；没有新建文件。"
        : "你拒绝了本次工具调用；没有读取项目内容。";
      button.textContent =
        step.tool === "list_project_files"
          ? "重新申请读取项目清单"
          : "重新申请读取项目文件";
      updateBrainStepStatus(stepIndex, "rejected", "已拒绝");
      return;
    }
    const observation = result.observation;
    resultNode.textContent = JSON.stringify(observation, null, 2).slice(0, 12000);
    if (isCreate) {
      const verification = observation?.verification;
      if (observation?.created && verification?.content_matches) {
        status.textContent = "新文件已创建，并已回读确认内容一致。";
        updateBrainStepStatus(stepIndex, "confirmed", "已创建 · 回读一致");
        refreshMiniGamePreviewState();
      } else {
        status.textContent =
          "文件创建请求已返回，但回读未能确认内容一致；请检查实际文件后再决定后续操作。";
        status.classList.add("error");
        updateBrainStepStatus(stepIndex, "uncertain", "已创建 · 回读未确认");
      }
      button.dataset.terminal = "true";
      button.disabled = true;
      button.textContent = "本步骤已处理";
      return;
    }
    status.textContent = "已执行只读工具；以上是实际返回结果。";
    button.textContent =
      step.tool === "list_project_files" ? "重新读取项目清单" : "重新读取项目文件";
    updateBrainStepStatus(stepIndex, "observed", "已读取 · 待核验");
    verifyButton.hidden = false;
    verifyButton.addEventListener("click", async () => {
      if (updateBrainPlanTaskState()) {
        verification.textContent =
          "计划目标已修改；请重新生成计划后再核验这次观察。";
        return;
      }
      verifyButton.disabled = true;
      verifyButton.dataset.busy = "true";
      verification.textContent = "墨灵正在根据成功标准核验工具返回…";
      updateBrainStepStatus(stepIndex, "verifying", "核验中");
      try {
        const verificationObservation = structuredClone(observation);
        if (
          typeof verificationObservation.content === "string" &&
          verificationObservation.content.length > 8000
        ) {
          verificationObservation.content =
            `${verificationObservation.content.slice(0, 8000)}\n[内容已截断，不能据此验证全文]`;
        }
        const checked = await window.companion.verifyAgentTool({
          task: activeBrainTask,
          success_criteria: step.success_criteria,
          observation: verificationObservation,
        });
        const labels = {
          confirmed: "模型判断：符合成功标准",
          uncertain: "模型判断：证据不足",
          not_met: "模型判断：尚未满足",
        };
        verification.textContent =
          `${labels[checked.verification.status]} · ${checked.verification.evidence} ` +
          `（${checked.model} 的评估，不是独立事实证明）`;
        const verificationStates = {
          confirmed: ["confirmed", "核验符合"],
          uncertain: ["uncertain", "证据不足"],
          not_met: ["not-met", "未满足"],
        };
        const [state, label] = verificationStates[checked.verification.status];
        updateBrainStepStatus(stepIndex, state, label);
        verifyButton.textContent = "重新核验";
      } catch (error) {
        verification.textContent = `结果核验失败：${error.message}`;
        updateBrainStepStatus(stepIndex, "verification-error", "核验失败 · 可重试");
        verifyButton.textContent = "重试核验";
      } finally {
        verifyButton.dataset.busy = "false";
        verifyButton.disabled = false;
        updateBrainPlanTaskState();
      }
    });
  } catch (error) {
    status.textContent = `工具调用失败：${error.message}`;
    status.classList.add("error");
    if (isCreate && /target already exists/i.test(error.message)) {
      status.textContent = "目标文件已经存在，没有覆盖；如需采用此名称，请先更换路径再生成计划。";
      button.dataset.terminal = "true";
      button.disabled = true;
      button.textContent = "目标已存在 · 未覆盖";
      updateBrainStepStatus(stepIndex, "exists", "目标已存在 · 未覆盖");
    } else {
      button.textContent = isCreate
        ? "重试创建（目标存在时会拒绝覆盖）"
        : step.tool === "list_project_files"
          ? "重试读取项目清单"
          : "重试读取项目文件";
      updateBrainStepStatus(
        stepIndex,
        "execution-error",
        isCreate ? "创建失败 · 可重试" : "读取失败 · 可重试",
      );
    }
  } finally {
    button.dataset.busy = "false";
    button.disabled = button.dataset.terminal === "true" || activeBrainPlan !== plan;
    brainToolExecutionActive = false;
    updateCollaborationRoleControls();
    updateBrainPlanTaskState();
  }
}

collaborationTask.addEventListener("input", updateBrainPlanTaskState);

translatorInput.addEventListener("input", () => {
  translatorInputCount.textContent = `${translatorInput.value.length} / 4000`;
  translationRequestVersion += 1;
  translatorOutput.value = "";
  translatorCopy.disabled = true;
  translatorStatus.textContent = "";
  translatorStatus.classList.remove("error");
});

for (const languageSelect of [
  document.getElementById("translator-source"),
  document.getElementById("translator-target"),
]) {
  languageSelect.addEventListener("change", () => {
    translationRequestVersion += 1;
    translatorOutput.value = "";
    translatorCopy.disabled = true;
    translatorStatus.textContent = "";
    translatorStatus.classList.remove("error");
  });
}

document.getElementById("translator-clear").addEventListener("click", () => {
  translationRequestVersion += 1;
  translatorInput.value = "";
  translatorOutput.value = "";
  translatorCopy.disabled = true;
  translatorStatus.textContent = "";
  translatorStatus.classList.remove("error");
  translatorInputCount.textContent = "0 / 4000";
  translatorInput.focus();
});

translatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const requestVersion = ++translationRequestVersion;
  const text = translatorInput.value;
  const sourceLanguage = document.getElementById("translator-source").value;
  const targetLanguage = document.getElementById("translator-target").value;
  if (!text.trim()) {
    translatorStatus.textContent = "请先输入要翻译的文本。";
    translatorStatus.classList.add("error");
    return;
  }
  if (sourceLanguage === targetLanguage) {
    translatorStatus.textContent = "源语言和目标语言不能相同。";
    translatorStatus.classList.add("error");
    return;
  }
  translatorSubmit.disabled = true;
  translatorCopy.disabled = true;
  translatorOutput.value = "";
  translatorStatus.textContent = "墨灵正在翻译…";
  translatorStatus.classList.remove("error");
  try {
    const result = await window.companion.translate({
      text,
      source_language: sourceLanguage,
      target_language: targetLanguage,
    });
    if (requestVersion !== translationRequestVersion) return;
    translatorOutput.value = result.translation;
    translatorCopy.disabled = !result.translation;
    if (translatorSpeak) translatorSpeak.disabled = !result.translation;
    translatorStatus.textContent =
      `翻译完成 · ${result.model} · ${result.inference_ms} ms`;
  } catch (error) {
    if (requestVersion !== translationRequestVersion) return;
    translatorStatus.textContent = `翻译失败：${error.message}`;
    translatorStatus.classList.add("error");
  } finally {
    translatorSubmit.disabled = false;
  }
});

translatorCopy.addEventListener("click", async () => {
  if (!translatorOutput.value) return;
  try {
    await navigator.clipboard.writeText(translatorOutput.value);
    translatorStatus.textContent = "译文已复制。";
    translatorStatus.classList.remove("error");
  } catch (error) {
    translatorStatus.textContent = `复制失败：${error.message}`;
    translatorStatus.classList.add("error");
  }
});

const translatorVoiceSelect = document.getElementById("translator-voice-select");
const translatorSpeak = document.getElementById("translator-speak");

function populateTranslatorVoiceSelect() {
  if (!translatorVoiceSelect) return;
  const selected = translatorVoiceSelect.value;
  translatorVoiceSelect.replaceChildren();
  const piper = document.createElement("option");
  piper.value = "";
  piper.textContent = "使用当前角色设置的合成声线";
  translatorVoiceSelect.append(piper);
  for (const voice of speechVoices) {
    const option = document.createElement("option");
    option.value = `${LOCAL_VOICE_PREFIX}${voice.name}`;
    option.textContent = `${voice.display}${voice.default ? " · 当前默认" : ""}`;
    translatorVoiceSelect.append(option);
  }
  for (const resource of voiceResources) {
    const option = document.createElement("option");
    option.value = `reference:${resource.id}`;
    option.textContent =
      `${resource.name} · ${voiceLanguageLabels[resource.language]} · 参考声线（仅试听）`;
    translatorVoiceSelect.append(option);
  }
  translatorVoiceSelect.value = selected || "";
}

function playSynthesizedWav(wavBytes) {
  const bytes =
    wavBytes instanceof Uint8Array
      ? wavBytes
      : wavBytes instanceof ArrayBuffer
        ? new Uint8Array(wavBytes)
        : null;
  if (
    !bytes ||
    bytes.byteLength < 44 ||
    String.fromCharCode(...bytes.subarray(0, 4)) !== "RIFF" ||
    String.fromCharCode(...bytes.subarray(8, 12)) !== "WAVE"
  ) {
    throw new Error("本机语音服务返回的 WAV 数据格式无效");
  }
  const audioUrl = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  if (activeAudio) {
    activeAudio.pause();
    URL.revokeObjectURL(activeAudio.src);
  }
  const playback = new Audio(audioUrl);
  applyVoicePreferences(playback);
  activeAudio = playback;
  const release = () => {
    URL.revokeObjectURL(audioUrl);
    if (activeAudio === playback) activeAudio = undefined;
  };
  playback.addEventListener("ended", release, { once: true });
  playback.addEventListener("error", release, { once: true });
  return playback.play();
}

translatorSpeak.addEventListener("click", async () => {
  const text = translatorOutput.value;
  if (!text.trim()) {
    translatorStatus.textContent = "请先翻译文本，再朗读译文。";
    translatorStatus.classList.add("error");
    return;
  }
  translatorSpeak.disabled = true;
  try {
    const selectedVoice = translatorVoiceSelect.value;
    if (selectedVoice.startsWith("reference:")) {
      const resourceId = selectedVoice.slice("reference:".length);
      const sample = await window.companion.getVoiceReference(resourceId);
      await playVoicePreview(sample);
      translatorStatus.textContent =
        "正在试听参考声线（仅供参考试听；朗读仍使用 Piper 合成音色）。";
      translatorStatus.classList.remove("error");
      return;
    }
    const requestedVoice = selectedVoice.startsWith(LOCAL_VOICE_PREFIX)
      ? selectedVoice.slice(LOCAL_VOICE_PREFIX.length)
      : getCharacterSynthesisVoice();
    const wav = await window.companion.synthesize(text, requestedVoice);
    await playSynthesizedWav(wav);
    translatorStatus.textContent = requestedVoice
      ? `正在使用所选本地声线「${requestedVoice}」朗读译文。`
      : "正在使用当前默认音色朗读译文。";
    translatorStatus.classList.remove("error");
  } catch (error) {
    translatorStatus.textContent = `朗读失败：${error.message}`;
    translatorStatus.classList.add("error");
  } finally {
    translatorSpeak.disabled = false;
  }
});

async function loadCharacters() {
  const status = document.getElementById("character-card-status");
  status.textContent = "";
  status.classList.remove("error");
  try {
    const result = await window.companion.listCharacters();
    characterCardList.replaceChildren();
    for (const item of result.characters) {
      const card = document.createElement("article");
      card.className = "character-card";
      card.classList.toggle("active", item.id === result.active_id);
      const portrait = document.createElement("div");
      portrait.className = "character-card-portrait";
      const image = document.createElement("img");
      image.alt = `${item.character.nickname}立绘`;
      image.hidden = true;
      const fallback = document.createElement("span");
      fallback.textContent = item.character.nickname.slice(0, 1);
      portrait.append(image, fallback);
      if (item.character.avatar) {
        try {
          image.src = await window.companion.getAvatar(item.character.avatar);
          image.hidden = false;
          fallback.hidden = true;
        } catch {
          fallback.title = "立绘加载失败";
        }
      }
      const name = document.createElement("strong");
      name.textContent = item.character.nickname;
      const category = document.createElement("span");
      category.className = "character-card-category";
      category.textContent = item.character.category;
      if (item.id === result.active_id) {
        const active = document.createElement("span");
        active.className = "character-card-active";
        active.textContent = "当前使用";
        card.append(active);
      }
      const actions = document.createElement("div");
      actions.className = "character-card-buttons";
      const select = document.createElement("button");
      select.className = "icon-button";
      select.type = "button";
      select.textContent = item.id === result.active_id ? "使用中" : "选择";
      select.disabled = item.id === result.active_id;
      select.setAttribute(
        "aria-label",
        item.id === result.active_id
          ? `${item.character.nickname}当前正在使用`
          : `选择${item.character.nickname}`,
      );
      select.addEventListener("click", () => switchCharacter(item.id));
      const edit = document.createElement("button");
      edit.className = "icon-button";
      edit.type = "button";
      edit.textContent = "编辑";
      edit.setAttribute("aria-label", `编辑${item.character.nickname}`);
      edit.addEventListener("click", () => editCharacter(item));
      actions.append(select, edit);
      if (item.id !== result.active_id) {
        const remove = document.createElement("button");
        remove.className = "icon-button character-card-delete";
        remove.type = "button";
        remove.textContent = "删除";
        remove.setAttribute("aria-label", `删除${item.character.nickname}`);
        remove.addEventListener("click", () => deleteCharacter(item));
        actions.append(remove);
      }
      card.append(portrait, name, category, actions);
      characterCardList.append(card);
    }
  } catch (error) {
    characterCardList.textContent = `无法读取角色卡：${error.message}`;
  }
}

async function editCharacter(item) {
  if (
    characterEditor.open &&
    characterForm.dataset.dirty === "true" &&
    !window.confirm("当前编辑内容尚未保存，切换编辑对象会放弃修改。继续吗？")
  ) {
    return;
  }
  await refreshVoiceResources();
  editingCharacterId = item.id;
  fillCharacterForm(item.character);
  characterForm.dataset.dirty = "false";
  avatarStatus.classList.remove("error");
  avatarStatus.textContent =
    "仅选择自有或已获授权的 PNG、JPEG、WebP 图片（最大 8 MB、1600 万像素）；文件会复制到本地角色资源目录。";
  document.getElementById("character-editor-title").textContent =
    `编辑角色卡 · ${item.character.nickname}`;
  document.getElementById("settings-avatar-fallback").textContent =
    item.character.nickname.slice(0, 1);
  try {
    const avatar = item.character.avatar
      ? await window.companion.getAvatar(item.character.avatar)
      : null;
    setEditorAvatar(avatar);
    avatarInput.value = item.character.avatar || "";
  } catch (error) {
    setEditorAvatar(null);
    avatarStatus.textContent = `无法读取角色立绘：${error.message}`;
    avatarStatus.classList.add("error");
  }
  characterEditor.showModal();
}

function clearCurrentConversation() {
  conversationHistory = [];
  updateAgentReflectionButton();
  resetMicroStory(true);
  conversation.replaceChildren(welcome);
  welcome.hidden = false;
  input.focus();
}

function renderMicroStory() {
  const node = microStoryNodes[microStoryNode];
  microStoryText.textContent = node.text;
  microStoryChoices.replaceChildren();
  for (const choice of node.choices) {
    const button = document.createElement("button");
    button.className = "micro-story-choice";
    button.type = "button";
    button.textContent = choice.label;
    button.disabled = microStoryPaused;
    button.addEventListener("click", () => {
      microStoryHistory.push(microStoryNode);
      microStoryNode = choice.next;
      microStoryStatus.textContent = "";
      renderMicroStory();
      microStoryChoices.querySelector("button")?.focus();
    });
    microStoryChoices.append(button);
  }
  microStoryBack.disabled = microStoryPaused || microStoryHistory.length === 0;
  microStoryPause.textContent = microStoryPaused ? "继续" : "暂停";
  if (microStoryPaused) {
    microStoryChoices.hidden = true;
    microStoryStatus.textContent = "故事已暂停；准备好后可以继续，也可以退出。";
  } else {
    microStoryChoices.hidden = false;
  }
}

function resetMicroStory(close = false) {
  microStoryNode = "pier";
  microStoryHistory = [];
  microStoryPaused = false;
  microStoryStatus.textContent =
    "纯本地分支故事；不调用模型、不联网，也不会保存为记忆。";
  microStoryChoices.hidden = false;
  microStoryChoices.replaceChildren();
  microStoryBack.disabled = true;
  microStoryPause.textContent = "暂停";
  if (close) microStory.hidden = true;
}

microStoryStart.addEventListener("click", () => {
  microStory.hidden = false;
  resetMicroStory();
  renderMicroStory();
  microStoryChoices.querySelector("button")?.focus();
});

microStoryBack.addEventListener("click", () => {
  if (microStoryPaused || microStoryHistory.length === 0) return;
  microStoryNode = microStoryHistory.pop();
  microStoryStatus.textContent = "已回到上一步，可以改选另一条路。";
  renderMicroStory();
});

microStoryPause.addEventListener("click", () => {
  microStoryPaused = !microStoryPaused;
  renderMicroStory();
});

microStoryRestart.addEventListener("click", () => {
  resetMicroStory();
  renderMicroStory();
  microStoryChoices.querySelector("button")?.focus();
});

microStoryExit.addEventListener("click", () => {
  resetMicroStory(true);
  microStoryStart.focus();
});

document.getElementById("character-create").addEventListener("click", createCharacter);

document.getElementById("open-personality-picker").addEventListener("click", () => {
  renderPersonalityCards();
  document.getElementById("personality-gallery").hidden = false;
  document.getElementById("personality-detail").hidden = true;
  document.getElementById("personality-picker").showModal();
});

document.getElementById("personality-picker-close").addEventListener("click", () => {
  document.getElementById("personality-picker").close();
});

function returnToPersonalityGallery() {
  document.getElementById("personality-gallery").hidden = false;
  document.getElementById("personality-detail").hidden = true;
}

document.getElementById("personality-back").addEventListener("click", returnToPersonalityGallery);
document.getElementById("personality-detail-back").addEventListener("click", returnToPersonalityGallery);

document.getElementById("personality-choose").addEventListener("click", (event) => {
  const presetId = event.currentTarget.dataset.presetId;
  const preset = personalityPresets[presetId];
  if (!preset) return;
  selectedPersonalityPreset = presetId;
  for (const field of personalityFieldNames) {
    const value = preset[field] || [];
    characterForm.elements[field].value =
      field === "signature_lines" ? value.join("\n") : value.join(", ");
  }
  updatePersonalityCurrentLabel();
  characterForm.dataset.dirty = "true";
  characterStatus.textContent = "人格已应用到当前编辑草稿；保存角色卡后生效。";
  characterStatus.classList.remove("error");
  document.getElementById("personality-picker").close();
});

for (const field of personalityFieldNames) {
  characterForm.elements[field].addEventListener("input", () => {
    selectedPersonalityPreset = "custom";
    updatePersonalityCurrentLabel();
  });
}

async function switchCharacter(characterId) {
  if (characterId === currentCharacterId) return;
  try {
    await window.companion.selectCharacter(characterId);
    currentCharacterId = characterId;
    clearCurrentConversation();
    await loadCharacter();
    await loadAffect();
    await loadCharacters();
    await refreshMiniGamePreviewState();
    characterStatus.textContent = "角色卡已切换；当前对话上下文已清空。";
    characterStatus.classList.remove("error");
  } catch (error) {
    document.getElementById("character-card-status").textContent =
      `切换角色失败：${error.message}`;
    document.getElementById("character-card-status").classList.add("error");
  }
}

async function deleteCharacter(item) {
  if (
    !window.confirm(
      `确定删除角色「${item.character.nickname}」吗？\n角色卡与配置会被移除，此操作不可撤销。`,
    )
  ) {
    return;
  }
  if (
    characterEditor.open &&
    editingCharacterId === item.id &&
    characterForm.dataset.dirty === "true"
  ) {
    characterEditor.close();
  }
  try {
    await window.companion.deleteCharacter(item.id);
    document.getElementById("character-card-status").textContent =
      `已删除角色「${item.character.nickname}」。`;
    document.getElementById("character-card-status").classList.remove("error");
    await loadCharacters();
  } catch (error) {
    document.getElementById("character-card-status").textContent =
      `删除角色失败：${error.message}`;
    document.getElementById("character-card-status").classList.add("error");
  }
}

async function createCharacter() {
  const card = {
    category: "自建角色",
    formal_name: "新角色",
    nickname: "新角色",
    english_name: "New Character",
    gender: "未设定",
    self_reference: "我",
    personality_preset: "moling",
    language: "auto",
    core_values: ["温柔", "真诚", "尊重彼此", "保持自己的看法"],
    inner_drives: ["理解用户与共同经历", "一起探索新事物", "持续学习并创造"],
    behavior_traits: ["自然亲切", "会认真倾听", "不敷衍", "有想法时坦诚表达"],
    habits: ["先听完再回应", "重要事情先确认事实", "愿意承认并修正错误"],
    likes: ["真诚交流", "共同探索", "把想法做成作品"],
    dislikes: ["敷衍与欺骗", "未经许可越界", "把猜测说成事实"],
    boundaries: [
      "尊重用户自主选择与隐私",
      "不伪造感受或已完成的行动",
      "读取屏幕、修改用户文件、联网或联系他人前先取得许可",
    ],
    communication_style: ["自然亲切", "坦诚温暖", "回应具体内容", "不过度追问"],
    emotional_range: ["开心", "好奇", "担心", "害羞"],
    agent_autonomy_enabled: true,
    agent_goals: [],
    signature_lines: [],
    model_format: "pngtuber",
    model_files: [],
    model_file: null,
    actions: [],
    expressions: [],
    emotion_mapping: {},
    emotion_avatars: {},
    avatar: null,
    voice: null,
  };
  try {
    const created = await window.companion.createCharacter(card);
    await loadCharacters();
    await editCharacter(created);
  } catch (error) {
    characterCardList.textContent = `新建角色卡失败：${error.message}`;
  }
}

document.getElementById("character-editor-close").addEventListener("click", () => {
  if (
    characterForm.dataset.dirty === "true" &&
    !window.confirm("角色卡修改尚未保存，确定关闭并放弃修改吗？")
  ) {
    return;
  }
  characterEditor.close();
});

document.getElementById("open-model-studio").addEventListener("click", () => {
  modelStudio.showModal();
  renderModelFiles();
});

document.getElementById("model-studio-close").addEventListener("click", () => {
  modelStudio.close();
});

document.getElementById("model-format").addEventListener("change", () => {
  characterForm.dataset.dirty = "true";
  renderModelFiles();
});

document.getElementById("model-file-select").addEventListener("change", (event) => {
  selectedModelFile = event.currentTarget.value;
  characterForm.dataset.dirty = "true";
  updateModelPreview();
});

document.getElementById("emotion-tour-start").addEventListener("click", () => {
  if (emotionTourTimer !== null) {
    stopEmotionTour();
    updateModelPreview();
  } else {
    void startEmotionTour();
  }
});

document.getElementById("emotion-tour-voice").addEventListener("click", () => {
  void emotionTourVoiceSample();
});

document.getElementById("model-actions").addEventListener("input", () => {
  characterForm.dataset.dirty = "true";
  renderEmotionMappings();
});

document.getElementById("model-expressions").addEventListener("input", () => {
  characterForm.dataset.dirty = "true";
  renderEmotionMappings();
});

document.getElementById("model-assets-import").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  const status = document.getElementById("model-studio-status");
  status.textContent = "";
  status.classList.remove("error");
  try {
    const imported = await window.companion.importModelAssets();
    if (!imported.length) return;
    modelFiles = [...new Set([...modelFiles, ...imported.map((asset) => asset.name)])];
    for (const asset of imported) modelFileSizes.set(asset.name, asset.bytes);
    const importedActions = imported
      .filter((asset) => /\.(vmd|motion3\.json)$/i.test(asset.originalName))
      .map((asset) => asset.originalName.replace(/\.[^.]+(?:\.json)?$/i, ""));
    const importedExpressions = imported
      .filter((asset) => /\.(exp3\.json)$/i.test(asset.originalName))
      .map((asset) => asset.originalName.replace(/\.exp3\.json$/i, ""));
    document.getElementById("model-actions").value = [
      ...new Set([...splitList(document.getElementById("model-actions").value), ...importedActions]),
    ].join(", ");
    document.getElementById("model-expressions").value = [
      ...new Set([
        ...splitList(document.getElementById("model-expressions").value),
        ...importedExpressions,
      ]),
    ].join(", ");
    renderEmotionMappings();
    const modelExtension = {
      mmd: /\.(pmx|pmd)$/i,
      vrm: /\.vrm$/i,
      live2d: /\.(model3\.json|moc3)$/i,
      pngtuber: /\.(png|jpe?g|webp)$/i,
    }[document.getElementById("model-format").value];
    selectedModelFile =
      imported.find((asset) => modelExtension.test(asset.originalName))?.name ||
      imported[0].name;
    renderModelFiles();
    characterForm.dataset.dirty = "true";
    status.textContent = `已导入 ${imported.length} 个资源；保存表现设置后关联到此角色卡。`;
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("model-studio-save").addEventListener("click", () => {
  if (!characterForm.reportValidity()) return;
  saveAppearanceRequested = true;
  characterForm.requestSubmit();
});

characterEditor.addEventListener("cancel", (event) => {
  if (
    characterForm.dataset.dirty === "true" &&
    !window.confirm("角色卡修改尚未保存，确定关闭并放弃修改吗？")
  ) {
    event.preventDefault();
  }
});

function setMemoryStatus(message, isError = false) {
  memoryStatus.textContent = message;
  memoryStatus.classList.toggle("error", isError);
}

async function applyEmotionAvatar(mood) {
  const requestVersion = ++appearanceRequestVersion;
  const portraits = window.MolingAvatarDisplay.getAvatarCandidates({
    baseAvatar: baseAvatarFileName,
    emotionAvatars: runtimeEmotionAvatars,
    mood,
    mode: avatarDisplayMode,
  });
  let lastError;
  for (const portrait of portraits) {
    try {
      await loadAvatar(portrait);
      if (requestVersion !== appearanceRequestVersion) return;
      avatarStatus.classList.remove("error");
      return;
    } catch (error) {
      if (requestVersion !== appearanceRequestVersion) return;
      lastError = error;
    }
  }
  if (requestVersion !== appearanceRequestVersion) return;
  await loadAvatar(null);
  if (lastError) {
    avatarStatus.textContent = `无法加载角色立绘：${lastError.message}`;
    avatarStatus.classList.add("error");
  } else {
    avatarStatus.classList.remove("error");
  }
}

async function initializeAvatarDisplayMode() {
  try {
    avatarDisplayMode = window.MolingAvatarDisplay.normalizeMode(
      localStorage.getItem(AVATAR_DISPLAY_MODE_KEY),
    );
  } catch (error) {
    affectStatus.textContent = `无法读取立绘偏好，将暂时跟随模拟状态：${error.message}`;
    affectStatus.classList.add("error");
  }
  avatarDisplayModeSelect.value = avatarDisplayMode;
  try {
    await window.companion.setAvatarDisplayMode(avatarDisplayMode);
  } catch (error) {
    affectStatus.textContent = `无法同步悬浮窗立绘偏好：${error.message}`;
    affectStatus.classList.add("error");
  }
}

avatarDisplayModeSelect.addEventListener("change", async () => {
  const nextMode = window.MolingAvatarDisplay.normalizeMode(
    avatarDisplayModeSelect.value,
  );
  avatarDisplayMode = nextMode;
  avatarDisplayModeSelect.value = nextMode;
  let persistenceError;
  try {
    localStorage.setItem(AVATAR_DISPLAY_MODE_KEY, nextMode);
  } catch (error) {
    persistenceError = error;
  }
  await applyEmotionAvatar(affectMood.value);
  refreshAllMessageAvatars();
  try {
    await window.companion.setAvatarDisplayMode(nextMode);
    affectStatus.textContent = persistenceError
      ? `本次会话已切换立绘方式，但无法保存偏好：${persistenceError.message}`
      : "立绘显示偏好已保存，并同步到悬浮窗。";
    affectStatus.classList.toggle("error", Boolean(persistenceError));
  } catch (error) {
    affectStatus.textContent = `主窗口已切换立绘方式，但悬浮窗同步失败：${error.message}`;
    affectStatus.classList.add("error");
  }
});

function updateAffect(state) {
  affectMood.value = state.mood;
  affectIndicator.textContent = `模拟状态 · ${state.label}`;
  affectIndicator.dataset.mood = state.mood;
  document.getElementById("topbar-avatar").dataset.mood = state.mood;
  document.getElementById("settings-avatar").dataset.mood = state.mood;
  affectReason.textContent = `状态线索：${state.reason}`;
  applyEmotionAvatar(state.mood);
  const characterDisplay = document.getElementById("character-display");
  if (characterDisplay) characterDisplay.dataset.mood = state.mood;
  refreshAllMessageAvatars();
  window.companion.setAvatarDisplayMode(avatarDisplayMode).catch((error) => {
    affectStatus.textContent = `悬浮窗立绘状态同步失败：${error.message}`;
    affectStatus.classList.add("error");
  });
}

async function loadAffect() {
  try {
    updateAffect(await window.companion.getAffect());
  } catch (error) {
    affectStatus.textContent = error.message;
    affectStatus.classList.add("error");
  }
}

async function loadMemories() {
  try {
    const result = await window.companion.listMemories();
    includeMemories.checked = result.privacy.include_memories_in_prompt;
    renderMemories(result.memories);
  } catch (error) {
    setMemoryStatus(error.message, true);
  }
}

function renderMemories(memories) {
  memoryList.replaceChildren();
  if (memories.length === 0) {
    const empty = document.createElement("div");
    empty.className = "memory-empty";
    empty.textContent = "还没有保存的记忆。添加后可随时修改、导出或删除。";
    memoryList.append(empty);
    return;
  }

  for (const memory of memories) {
    const entry = document.createElement("article");
    entry.className = "memory-entry";
    if (memory.status === "paused") entry.classList.add("paused");

    const contentLabel = document.createElement("label");
    contentLabel.textContent = "记忆内容";
    const content = document.createElement("textarea");
    content.rows = 3;
    content.maxLength = 20_000;
    content.value = memory.content;
    contentLabel.append(content);

    const visibilityLabel = document.createElement("label");
    visibilityLabel.textContent = "隐私范围";
    const visibility = document.createElement("select");
    for (const [value, label] of [
      ["model", "参与当前模型提示"],
      ["private", "仅本地保存，不进入提示"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      visibility.append(option);
    }
    visibility.value = memory.visibility;
    visibilityLabel.append(visibility);

    const metadata = document.createElement("div");
    metadata.className = "memory-entry-meta";
    const created = memory.created_at === "unknown"
      ? "旧版记录"
      : new Date(memory.created_at).toLocaleString();
    const reasonText = memory.reason ? ` · 原因：${memory.reason}` : "";
    const statusText = memory.status === "paused" ? " · 已暂停（不进入回复提示）" : " · 活跃";
    const usedText =
      (memory.use_count || 0) > 0
        ? ` · 已采用 ${memory.use_count} 次${memory.last_used_at ? `（最近 ${new Date(memory.last_used_at).toLocaleString()}）` : ""}`
        : " · 尚未被采用";
    metadata.textContent =
      `来源：${memory.source}${reasonText}${statusText}${usedText} · ${created}`;

    const actions = document.createElement("div");
    actions.className = "memory-entry-actions";
    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "保存修改";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        await window.companion.updateMemory(memory.id, {
          content: content.value,
          visibility: visibility.value,
          source: memory.source,
        });
        setMemoryStatus("记忆已更新。");
        await loadMemories();
      } catch (error) {
        setMemoryStatus(error.message, true);
      } finally {
        save.disabled = false;
      }
    });

    const pause = document.createElement("button");
    pause.type = "button";
    pause.textContent = memory.status === "paused" ? "恢复使用" : "暂停使用";
    pause.addEventListener("click", async () => {
      pause.disabled = true;
      try {
        const next = memory.status === "paused" ? "active" : "paused";
        await window.companion.updateMemory(memory.id, {
          content: content.value,
          visibility: visibility.value,
          source: memory.source,
          status: next,
        });
        setMemoryStatus(
          next === "paused"
            ? "记忆已暂停：后续回复不再采用它。"
            : "记忆已恢复使用。"
        );
        await loadMemories();
      } catch (error) {
        setMemoryStatus(error.message, true);
      } finally {
        pause.disabled = false;
      }
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-memory";
    remove.textContent = "删除";
    remove.addEventListener("click", async () => {
      if (!window.confirm("确定永久删除这条记忆吗？")) return;
      remove.disabled = true;
      try {
        await window.companion.deleteMemory(memory.id);
        setMemoryStatus("记忆已删除。");
        await loadMemories();
      } catch (error) {
        setMemoryStatus(error.message, true);
      } finally {
        remove.disabled = false;
      }
    });

    actions.append(save, pause, remove);
    entry.append(contentLabel, visibilityLabel, metadata, actions);
    memoryList.append(entry);
  }
}

function attachReplyTools(message, evidence) {
  const tools = document.createElement("div");
  tools.className = "reply-tools";

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "查看本次回答依据";
  const sourceList = document.createElement("ul");
  sourceList.className = "reply-evidence-list";
  const addEvidence = (label, value) => {
    if (!value) return;
    const item = document.createElement("li");
    const heading = document.createElement("strong");
    heading.textContent = label;
    const text = document.createElement("span");
    text.textContent = value;
    item.append(heading, text);
    sourceList.append(item);
  };
  addEvidence("本轮输入", evidence?.direct_input);
  for (const item of evidence?.recent_context || []) {
    addEvidence(item.role === "user" ? "近期用户消息" : "近期墨灵回复", item.content);
  }
  if (evidence?.context_messages_not_shown) {
    addEvidence(
      "其他上下文",
      `本次请求还携带了 ${evidence.context_messages_not_shown} 条更早的历史消息；面板仅展示最近部分。`,
    );
  }
  for (const component of evidence?.prompt_components || []) {
    addEvidence("提示组成部分", component);
  }
  for (const memory of evidence?.model_memories || []) {
    addEvidence(`已纳入提示的记忆 · ${memory.id}`, memory.content);
  }
  addEvidence("记忆使用情况", evidence?.memory_policy);
  addEvidence("边界", evidence?.limits);
  if (sourceList.childElementCount === 0) {
    addEvidence("状态", "此回复没有提供可核对的来源记录。");
  }
  details.append(summary, sourceList);

  const actions = document.createElement("div");
  actions.className = "reply-tool-actions";
  const correction = document.createElement("button");
  correction.type = "button";
  correction.textContent = "纠正理解";
  correction.addEventListener("click", () => {
    const correctionText = window.prompt("你希望墨灵如何修正这次理解？");
    if (!correctionText?.trim()) return;
    void sendMessage(
      `我想纠正你刚才的理解：${correctionText.trim()}。请先按这次补充修正，不要自动把它保存为长期偏好。`,
    );
  });

  const alternatives = document.createElement("button");
  alternatives.type = "button";
  alternatives.textContent = "给我另一种解释";
  alternatives.addEventListener("click", () => {
    void sendMessage(
      "请针对你刚才的回答给出至少一种不同解释；区分我明确说过的内容与你的推测，不要把推测说成事实。",
    );
  });

  const forget = document.createElement("button");
  forget.type = "button";
  forget.textContent = "这次不要记住";
  forget.addEventListener("click", () => {
    void sendMessage(
      "这次不要把刚才的内容记录为长期记忆或稳定偏好。请只在当前对话范围内回应，并说明当前聊天内容不会自动写入长期记忆。",
    );
  });

  actions.append(correction, alternatives, forget);
  tools.append(details, actions);
  message.append(tools);
}

async function handleAnalyzeImage() {
  imageButton.disabled = true;
  try {
    const result = await window.companion.analyzeImage();
    if (result.canceled) return;
    const message = addMessage(
      `我看了你主动选择的图片「${result.name}」。这次分析不会自动保存图片或写入长期记忆；模型可能看错，下面请你核对。`,
      "assistant",
    );
    const preview = document.createElement("img");
    preview.className = "image-analysis-preview";
    preview.src = result.image_data_url;
    preview.alt = `本次分析的图片：${result.name}`;
    const analysis = document.createElement("section");
    analysis.className = "image-analysis-result";
    const heading = document.createElement("strong");
    heading.textContent = result.analysis.observed || result.analysis.summary;
    analysis.append(heading);
    if (result.analysis.possible_interpretations) {
      const interpretation = document.createElement("p");
      interpretation.textContent =
        `可能解释（不保证正确）：${result.analysis.possible_interpretations}`;
      analysis.append(interpretation);
    }
    const uncertainty = document.createElement("p");
    uncertainty.textContent = `不确定处：${result.analysis.uncertainty}`;
    analysis.append(uncertainty);
    if (result.analysis.clarifying_question) {
      const question = document.createElement("p");
      question.textContent = `想确认：${result.analysis.clarifying_question}`;
      analysis.append(question);
    }
    const metadata = document.createElement("small");
    metadata.textContent =
      `本机模型：${result.analysis.engine} · 图片仅用于本次分析 · OCR/视觉描述可能有误`;
    analysis.append(metadata);
    const imageTypeLabel = document.createElement("p");
    imageTypeLabel.className = "image-analysis-type";
    imageTypeLabel.textContent = `图片类型：${IMAGE_TYPE_LABELS[result.analysis.image_type] || "其他图片"}`;
    analysis.append(imageTypeLabel);
    const readAloud = document.createElement("button");
    readAloud.type = "button";
    readAloud.className = "reply-tool-action";
    readAloud.textContent = "为你朗读这段分析";
    readAloud.addEventListener("click", () => {
      readAloud.disabled = true;
      const textToRead = [result.analysis.summary, result.analysis.observed]
        .filter(Boolean)
        .join("。");
      if (!textToRead) {
        readAloud.disabled = false;
        return;
      }
      window.companion
        .synthesize(textToRead, getCharacterSynthesisVoice())
        .then((audio) => {
          const bytes =
            audio instanceof Uint8Array
              ? audio
              : audio instanceof ArrayBuffer
                ? new Uint8Array(audio)
                : null;
          if (!bytes || bytes.byteLength < 44) throw new Error("语音数据无效");
          const url = URL.createObjectURL(
            new Blob([bytes], { type: "audio/wav" }),
          );
          const playback = new Audio(url);
          applyVoicePreferences(playback);
          playback.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
          playback.addEventListener("error", () => URL.revokeObjectURL(url), { once: true });
          return playback.play();
        })
        .then(() => {
          readAloud.textContent = "重新朗读";
        })
        .catch((error) => {
          readAloud.textContent = `朗读失败：${error.message}`;
        })
        .finally(() => {
          readAloud.disabled = false;
        });
    });
    const organizeButton = document.createElement("button");
    organizeButton.type = "button";
    organizeButton.className = "reply-tool-action";
    organizeButton.textContent = "帮你整理信息";
    organizeButton.addEventListener("click", () => {
      void sendMessage(
        `请把这张${IMAGE_TYPE_LABELS[result.analysis.image_type] || "图片"}里的信息整理成清晰的条目：要点、数字、待办或需要注意的地方分开列。图片内容参考：${result.analysis.observed || result.analysis.summary || ""}。不确定的内容要标注为不确定。`,
      );
    });
    const listButton = document.createElement("button");
    listButton.type = "button";
    listButton.className = "reply-tool-action";
    listButton.textContent = "列出可见内容";
    listButton.addEventListener("click", () => {
      void sendMessage(
        `请把这张${IMAGE_TYPE_LABELS[result.analysis.image_type] || "图片"}里能直接看到的内容逐条列出来，不要推测看不到的东西。图片内容参考：${result.analysis.observed || result.analysis.summary || ""}。`,
      );
    });
    const correction = document.createElement("button");
    correction.type = "button";
    correction.className = "reply-tool-action";
    correction.textContent = "模型看错了";
    correction.addEventListener("click", () => {
      const note = window.prompt("哪一处描述不准确？这次纠正不会保存为长期记忆。");
      if (note?.trim()) {
        void sendMessage(
          `你刚才分析我主动选择的图片时看错了：${note.trim()}。请承认不确定之处，并只根据我这次的纠正重新描述，不要推断我的情绪或意图，也不要把纠正保存为长期记忆。`,
        );
      }
    });
    const analysisActions = document.createElement("div");
    analysisActions.className = "reply-tool-actions";
    analysisActions.append(readAloud, organizeButton, listButton, correction);
    analysis.append(analysisActions);
    message.append(preview, analysis);
    conversation.scrollTop = conversation.scrollHeight;
  } catch (error) {
    addMessage(`图片分析没有完成：${error.message || error}`, "assistant", "error-message");
  } finally {
    imageButton.disabled = false;
  }
}

async function sendMessage(text) {
  const prompt = text.trim();
  if (!prompt || sendButton.disabled) return;
  const previousHistory = conversationHistory;
  const historyForRequest = previousHistory.slice(-20);
  welcome.hidden = true;
  addMessage(prompt, "user");
  input.value = "";
  sendButton.disabled = true;
  const pending = addMessage("正在等待本地模型…", "assistant", "pending");
  try {
    const result = await window.companion.generate(prompt, historyForRequest);
    pending.textContent = result.text;
    pending.classList.remove("pending");
    addSpeechControl(pending, result.text);
    attachReplyTools(pending, result.evidence);
    modelStatus.textContent = `本地模型 · ${result.model}`;
    conversationHistory = [
      ...historyForRequest,
      { role: "user", content: prompt },
      { role: "assistant", content: result.text },
    ].slice(-20);
    updateAgentReflectionButton();
    if (result.affect) updateAffect(result.affect);
    if (result.explore_proposal?.proposed) {
      attachExploreOffer(pending, result.explore_proposal, prompt);
    }
  } catch (error) {
    pending.textContent = `暂时无法生成：${error.message}`;
    pending.classList.add("error-message");
    pending.classList.remove("pending");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

async function reflectOnConversation(characterId, history) {
  const status = document.getElementById("agent-reflection-status");
  const reflectButton = document.getElementById("agent-reflect-now");
  reflectButton.disabled = true;
  status.textContent = "墨灵正在做本地自我复盘…";
  status.classList.remove("error");
  try {
    const result = await window.companion.reflectAgent(characterId, history);
    if (characterId !== currentCharacterId) return;
    if (!result.updated) {
      status.textContent = result.reason;
      return;
    }
    renderAgentGoals(result.goals, result.reflection);
    if (result.ignored_updates || result.ignored_goals) {
      status.textContent =
        `已保存可验证的复盘；忽略了 ${result.ignored_updates || 0} 条无法匹配的旧目标更新和 ${result.ignored_goals || 0} 个无效新目标。${result.ignored_goal_reason || ""}`;
    }
    await loadCharacters();
  } catch (error) {
    if (characterId !== currentCharacterId) return;
    status.textContent = `自主复盘未完成：${error.message}`;
    status.classList.add("error");
  } finally {
    updateAgentReflectionButton();
  }
}

document.getElementById("agent-reflect-now").addEventListener("click", () => {
  if (!conversationHistory.length) return;
  void reflectOnConversation(currentCharacterId, conversationHistory);
});

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

recordButton.addEventListener("click", toggleRecording);

fileButton.addEventListener("click", handleDiscoverFile);
imageButton.addEventListener("click", handleAnalyzeImage);

async function handleDiscoverFile() {
  if (
    !window.confirm(
      "墨灵想打开你选择的文件看看内容，然后好奇地问你几个问题。允许她读这个文件吗？",
    )
  ) {
    return;
  }
  try {
    const result = await window.companion.discoverFile();
    if (!result || result.canceled) return;
    const kindLabel = result.kind === "image" ? "图片" : result.kind === "code" ? "代码文件" : "文件";
    addMessage(`（分享${kindLabel}：${result.name}）`, "user");
    const reply = addMessage(result.feedback, "assistant");
    addSpeechControl(reply, result.feedback);
    conversationHistory = [
      ...conversationHistory,
      { role: "user", content: `[分享${kindLabel}：${result.name}]` },
      { role: "assistant", content: result.feedback },
    ];
    updateAffect(result.affect);
    if (result.explore_proposal?.proposed) {
      attachExploreOffer(
        reply,
        result.explore_proposal,
        `墨灵从文件《${result.name}》里发现了「${result.explore_proposal.topic}」`,
      );
    }
  } catch (error) {
    addMessage(`分享失败：${error.message || error}`, "assistant", "error");
  }
}

observeButton.addEventListener("click", handleObserveContext);

async function handleObserveContext() {
  if (
    !window.confirm(
      "墨灵想看看当前窗口里的内容，然后给出她的称赞和优化建议。允许她看吗？",
    )
  ) {
    return;
  }
  try {
    const result = await window.companion.discoverContext();
    if (!result || result.canceled) return;
    const reply = addMessage(result.feedback, "assistant");
    addSpeechControl(reply, result.feedback);
    conversationHistory = [
      ...conversationHistory,
      { role: "user", content: "[请墨灵看看当前窗口]" },
      { role: "assistant", content: result.feedback },
    ];
    updateAffect(result.affect);
  } catch (error) {
    addMessage(`看窗口失败：${error.message || error}`, "assistant", "error");
  }
}

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});

document.getElementById("new-chat").addEventListener("click", () => {
  clearCurrentConversation();
});

document.getElementById("settings-toggle").addEventListener("click", () => {
  settingsPanel.hidden = !settingsPanel.hidden;
});

document.getElementById("floating-toggle").addEventListener("click", async () => {
  const button = document.getElementById("floating-toggle");
  button.disabled = true;
  try {
    const result = await window.companion.floatingToggle();
    button.textContent = result.shown ? "收起悬浮窗" : "悬浮窗";
    button.title = result.shown
      ? "墨灵正在窗口外陪伴，点击收起"
      : "让墨灵在窗口外陪伴";
  } catch (error) {
    button.title = `悬浮窗切换失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});

document.getElementById("settings-close").addEventListener("click", () => {
  settingsPanel.hidden = true;
});

document.querySelectorAll("[data-settings-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    const selected = button.dataset.settingsTab;
    for (const panel of ["persona", "memories", "affect"]) {
      document.getElementById(`${panel}-panel`).hidden = panel !== selected;
    }
    document.querySelectorAll("[data-settings-tab]").forEach((tab) => {
      tab.classList.toggle("active", tab === button);
    });
    if (selected === "memories") loadMemories();
    if (selected === "affect") loadAffect();
  });
});

document.getElementById("affect-save").addEventListener("click", async () => {
  await saveAffect(affectMood.value, "模拟状态已保存。");
});

async function saveAffect(mood, confirmation) {
  try {
    const state = await window.companion.setAffect(mood);
    updateAffect(state);
    affectStatus.textContent = confirmation;
    affectStatus.classList.remove("error");
  } catch (error) {
    affectStatus.textContent = error.message;
    affectStatus.classList.add("error");
  }
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function formatDurationMs(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs < 0) return "未知";
  if (durationMs < 1000) return `${Math.round(durationMs)} 毫秒`;
  return `${(durationMs / 1000).toFixed(1)} 秒`;
}

ollamaDownloadLink.addEventListener("click", async () => {
  ollamaDownloadLink.disabled = true;
  try {
    await window.companion.openOllamaDownload();
  } catch (error) {
    modelSetupMessage.textContent = `无法打开 Ollama 下载页面：${error.message}`;
  } finally {
    ollamaDownloadLink.disabled = false;
  }
});

downloadModelButton.addEventListener("click", async () => {
  downloadModelButton.disabled = true;
  ollamaDownloadLink.disabled = true;
  modelDownloadProgress.hidden = false;
  modelDownloadProgress.removeAttribute("value");
  modelSetupMessage.textContent = "正在连接 Ollama 并准备下载…";
  const unsubscribe = window.companion.onModelProgress((progress) => {
    modelSetupMessage.textContent = progress.status;
    if (progress.total) {
      modelDownloadProgress.value = Math.min(
        100,
        Math.floor((progress.completed / progress.total) * 100),
      );
      modelSetupMessage.textContent +=
        ` · ${formatBytes(progress.completed)} / ${formatBytes(progress.total)}`;
    }
  });
  try {
    const result = await window.companion.pullModel();
    if (result.canceled) {
      modelDownloadProgress.hidden = true;
      modelSetupMessage.textContent = "已取消模型下载。";
      return;
    }
    const status = result;
    modelSetupMessage.textContent = `${status.modelName} 已下载并可使用。`;
    await refreshModelSetup();
    await refreshCollaborationAvailability();
  } catch (error) {
    modelSetupTitle.textContent = "模型下载失败";
    modelSetupMessage.textContent = error.message;
    modelDownloadProgress.hidden = true;
  } finally {
    unsubscribe();
    downloadModelButton.disabled = false;
    ollamaDownloadLink.disabled = false;
  }
});

document.getElementById("affect-reset").addEventListener("click", async () => {
  affectMood.value = "calm";
  await saveAffect("calm", "模拟状态已重置为平静。");
});

document.getElementById("avatar-select").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  avatarStatus.textContent = "";
  avatarStatus.classList.remove("error");
  try {
    const result = await window.companion.chooseAvatar();
    if (!result) return;
    avatarInput.value = result.name;
    if (
      document.getElementById("model-format").value === "pngtuber" &&
      (!selectedModelFile || selectedModelFile.startsWith("avatar:"))
    ) {
      selectedModelFile = `avatar:${result.name}`;
    }
    setEditorAvatar(result.dataUrl);
    renderModelFiles();
    characterForm.dataset.dirty = "true";
    avatarStatus.textContent = "已载入预览；点击“保存角色卡”后生效。";
  } catch (error) {
    avatarStatus.textContent = error.message;
    avatarStatus.classList.add("error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("avatar-clear").addEventListener("click", () => {
  avatarInput.value = "";
  if (selectedModelFile.startsWith("avatar:")) selectedModelFile = "";
  setEditorAvatar(null);
  renderModelFiles();
  characterForm.dataset.dirty = "true";
  avatarStatus.textContent = "立绘将在保存角色资料后移除。";
  avatarStatus.classList.remove("error");
});

characterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  characterStatus.textContent = "";
  characterStatus.classList.remove("error");
  const form = new FormData(characterForm);
  const card = {
    category: form.get("category"),
    formal_name: form.get("formal_name").trim(),
    nickname: form.get("nickname").trim(),
    english_name: form.get("english_name").trim(),
    language: form.get("language"),
    gender: form.get("gender").trim(),
    self_reference: form.get("self_reference").trim(),
    personality_preset: selectedPersonalityPreset,
    core_values: splitList(form.get("core_values")),
    inner_drives: splitList(form.get("inner_drives")),
    behavior_traits: splitList(form.get("behavior_traits")),
    habits: splitList(form.get("habits")),
    likes: splitList(form.get("likes")),
    dislikes: splitList(form.get("dislikes")),
    boundaries: splitList(form.get("boundaries")),
    communication_style: splitList(form.get("communication_style")),
    emotional_range: splitList(form.get("emotional_range")),
    agent_autonomy_enabled: document.getElementById("agent-autonomy-enabled").checked,
    model_format: document.getElementById("model-format").value,
    model_files: modelFiles,
    model_file: selectedModelFile || null,
    actions: splitList(document.getElementById("model-actions").value),
    expressions: splitList(document.getElementById("model-expressions").value),
    emotion_mapping: modelEmotionMapping,
    emotion_avatars: emotionAvatars,
    signature_lines: form
      .get("signature_lines")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
    avatar: avatarInput.value.trim() || null,
    id: editingCharacterId,
  };
  const selectedVoiceValue = characterVoiceSelect.value;
  const localVoiceSelected = selectedVoiceValue.startsWith(LOCAL_VOICE_PREFIX);
  if (localVoiceSelected) {
    card.voice = lastReferenceVoice || null;
  } else {
    card.voice = selectedVoiceValue || null;
    lastReferenceVoice = selectedVoiceValue || "";
  }
  try {
    await window.companion.saveCharacter(card);
    if (
      !saveCharacterVoicePreference(
        editingCharacterId,
        localVoiceSelected ? selectedVoiceValue : "",
      )
    ) {
      characterStatus.textContent =
        "角色卡已保存，但此浏览器无法保存声线偏好；下次可能需要重新选择。";
      characterStatus.classList.add("error");
    }
    characterForm.dataset.dirty = "false";
    if (!characterStatus.classList.contains("error")) {
      characterStatus.textContent = "角色卡资料与表现设置已保存。";
    }
    document.getElementById("character-editor-title").textContent =
      `编辑角色卡 · ${card.nickname}`;
    avatarStatus.textContent = card.avatar ? "角色立绘已保存。" : "角色立绘已移除。";
    avatarStatus.classList.remove("error");
    if (editingCharacterId === currentCharacterId) await loadCharacter();
    await loadCharacters();
    if (saveAppearanceRequested) {
      saveAppearanceRequested = false;
      modelStudio.close();
    }
  } catch (error) {
    saveAppearanceRequested = false;
    characterStatus.textContent = error.message;
    characterStatus.classList.add("error");
  }
});

memoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(memoryForm);
  const content = form.get("content").trim();
  if (!content) return;
  try {
    await window.companion.addMemory({
      content,
      source: "user",
      visibility: form.get("visibility"),
    });
    memoryForm.reset();
    setMemoryStatus("记忆已保存。");
    await loadMemories();
  } catch (error) {
    setMemoryStatus(error.message, true);
  }
});

includeMemories.addEventListener("change", async () => {
  includeMemories.disabled = true;
  try {
    const settings = await window.companion.setPrivacy({
      include_memories_in_prompt: includeMemories.checked,
    });
    includeMemories.checked = settings.include_memories_in_prompt;
    setMemoryStatus(
      settings.include_memories_in_prompt
        ? "参与模型提示的记忆已启用。"
        : "已停用所有记忆的模型提示注入。",
    );
  } catch (error) {
    includeMemories.checked = !includeMemories.checked;
    setMemoryStatus(error.message, true);
  } finally {
    includeMemories.disabled = false;
  }
});

document.getElementById("memory-export").addEventListener("click", async () => {
  try {
    const result = await window.companion.exportMemories();
    if (!result.canceled) {
      setMemoryStatus(`已导出 ${result.count} 条记忆到 ${result.fileName}。`);
    }
  } catch (error) {
    setMemoryStatus(error.message, true);
  }
});

document.getElementById("memory-import").addEventListener("click", async () => {
  try {
    const result = await window.companion.importMemories();
    if (!result.canceled) {
      setMemoryStatus(`导入 ${result.imported} 条，跳过重复项 ${result.skipped} 条。`);
      await loadMemories();
    }
  } catch (error) {
    setMemoryStatus(error.message, true);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  window.companion.onNotificationAction((selection) => {
    window.dispatchEvent(
      new CustomEvent("moling:notification-action", { detail: selection }),
    );
  });
  updateAgentReflectionButton();
  void loadCollaborationRoles();
  void initializeAvatarDisplayMode();
  refreshStatus();
  loadCharacter();
  loadCharacters();
  loadMemories();
  loadAffect();
  refreshVoiceResources();
  void loadSpeechVoices();
  void refreshMiniGamePreviewState();
  characterVoicePreview.addEventListener("click", previewSelectedVoice);
  characterVoiceSelect.addEventListener("change", () => {
    const value = characterVoiceSelect.value;
    if (!value.startsWith(LOCAL_VOICE_PREFIX)) {
      lastReferenceVoice = value;
    }
    updateCharacterVoicePreviewState();
  });
});

characterForm.addEventListener("input", () => {
  characterForm.dataset.dirty = "true";
});

characterForm.addEventListener("change", () => {
  characterForm.dataset.dirty = "true";
});
