const conversation = document.getElementById("conversation");
const welcome = document.getElementById("welcome");
const composer = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const recordButton = document.getElementById("record-button");
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
let collaborationRoleWarning = "";
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
const avatarInput = document.getElementById("avatar-name");
const avatarStatus = document.getElementById("avatar-status");
const characterCardList = document.getElementById("character-card-list");
const characterEditor = document.getElementById("character-editor");
const modelStudio = document.getElementById("model-studio");
const voiceStudio = document.getElementById("voice-studio");
const voiceResourceList = document.getElementById("voice-resource-list");
const voiceResourceStatus = document.getElementById("voice-resource-status");
const characterVoiceSelect = document.getElementById("character-voice-select");
const voiceSampleName = document.getElementById("voice-sample-name");
const voiceSamplePreview = document.getElementById("voice-sample-preview");
const voiceResourceRegister = document.getElementById("voice-resource-register");
let currentCharacterId;
let activeCharacterNickname = "墨灵";
let currentWorkspace = "chat";
let editingCharacterId;
let modelFiles = [];
let modelEmotionMapping = {};
let selectedModelFile = "";
let saveAppearanceRequested = false;
let translationRequestVersion = 0;
let voiceResources = [];
let pendingVoiceSample;
let activeVoicePreview;
let activeVoicePreviewUrl;
let selectedPersonalityPreset = "custom";
const simulatedEmotions = [
  ["calm", "平静"],
  ["happy", "开心"],
  ["curious", "好奇"],
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
  message.textContent = text;
  conversation.append(message);
  conversation.scrollTop = conversation.scrollHeight;
  return message;
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
      const audio = await window.companion.synthesize(text);
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
      activeAudio = playback;
      const releaseAudioUrl = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === playback) activeAudio = undefined;
      };
      playback.addEventListener("ended", releaseAudioUrl, { once: true });
      playback.addEventListener("error", releaseAudioUrl, { once: true });
      await playback.play();
      button.textContent = "重新播放";
    } catch (error) {
      playback?.pause();
      if (activeAudio === playback) activeAudio = undefined;
      if (audioUrl) URL.revokeObjectURL(audioUrl);
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
  populateCharacterVoiceSelect(card.voice || "");
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
    : "仅使用当前本地对话进行一次自主复盘";
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
    empty.textContent = "还没有形成长期目标。墨灵会在真实对话后自主复盘，不会因为空白就强行编造目标。";
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
    chip.textContent = `${describeModelResource(asset)} · ${asset.split("/").pop()}`;
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
    row.append(name, action, expression);
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

function setAvatarTargets(dataUrl) {
  for (const [containerId, imageId, fallbackId] of [
    ["character-display", "welcome-avatar-image", "welcome-avatar-fallback"],
    ["topbar-avatar", "topbar-avatar-image", "topbar-avatar-fallback"],
    ["settings-avatar", "settings-avatar-image", "settings-avatar-fallback"],
  ]) {
    const image = document.getElementById(imageId);
    const fallback = document.getElementById(fallbackId);
    image.onerror = () => {
      image.hidden = true;
      fallback.hidden = false;
      avatarStatus.textContent = "图片无法解码，请选择有效的 PNG、JPEG 或 WebP 文件。";
      avatarStatus.classList.add("error");
    };
    image.hidden = !dataUrl;
    fallback.hidden = Boolean(dataUrl);
    if (dataUrl) image.src = dataUrl;
    else image.removeAttribute("src");
    document.getElementById(containerId).classList.toggle("has-avatar", Boolean(dataUrl));
  }
}

async function loadAvatar(fileName) {
  if (!fileName) {
    setAvatarTargets(null);
    return;
  }
  setAvatarTargets(await window.companion.getAvatar(fileName));
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
    try {
      await loadAvatar(result.character.avatar);
    } catch (error) {
      setAvatarTargets(null);
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
  for (const resource of voiceResources) {
    const option = document.createElement("option");
    option.value = `reference:${resource.id}`;
    option.textContent =
      `${resource.name} · ${voiceLanguageLabels[resource.language]} · 参考录音`;
    characterVoiceSelect.append(option);
  }
  if (
    selectedVoice &&
    ![...characterVoiceSelect.options].some((option) => option.value === selectedVoice)
  ) {
    const unavailable = document.createElement("option");
    unavailable.value = selectedVoice;
    unavailable.textContent = "已移除的参考声线（请选择其他资源）";
    characterVoiceSelect.append(unavailable);
  }
  characterVoiceSelect.value = selectedVoice || "";
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
    details.textContent =
      `${voiceLanguageLabels[resource.language]} · ${resource.extension.slice(1).toUpperCase()} · 仅供参考试听`;
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
    voiceSampleName.textContent = `${pendingVoiceSample.originalName} · 已在内存中待注册`;
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
  const isGallery = workspace === "gallery";
  const isChat = !isTranslator && !isCollaboration && !isGallery;
  document.getElementById("conversation").hidden = !isChat;
  document.getElementById("composer").hidden = !isChat;
  document.getElementById("chat-notice").hidden = !isChat;
  translatorPanel.hidden = !isTranslator;
  collaborationPanel.hidden = !isCollaboration;
  galleryPanel.hidden = !isGallery;
  document.getElementById("new-chat").hidden = !isChat;
  document.getElementById("affect-indicator").hidden = !isChat;
  chatWorkspaceButton.classList.toggle("active", isChat);
  translatorWorkspaceButton.classList.toggle("active", isTranslator);
  collaborationWorkspaceButton.classList.toggle("active", isCollaboration);
  galleryWorkspaceButton.classList.toggle("active", isGallery);
  chatWorkspaceButton.setAttribute("aria-pressed", String(isChat));
  translatorWorkspaceButton.setAttribute("aria-pressed", String(isTranslator));
  collaborationWorkspaceButton.setAttribute("aria-pressed", String(isCollaboration));
  galleryWorkspaceButton.setAttribute("aria-pressed", String(isGallery));
  document.querySelector(".topbar-title strong").textContent = isTranslator
    ? "文本翻译器"
    : isCollaboration
      ? "智能体协作"
      : isGallery
        ? "墨灵的作品集"
        : `和${activeCharacterNickname}聊天`;
  if (isGallery) void refreshGallery();
}

chatWorkspaceButton.addEventListener("click", () => setWorkspace("chat"));
translatorWorkspaceButton.addEventListener("click", () =>
  setWorkspace("translator"),
);
collaborationWorkspaceButton.addEventListener("click", () =>
  setWorkspace("collaboration"),
);
galleryWorkspaceButton.addEventListener("click", () => setWorkspace("gallery"));
galleryRefresh.addEventListener("click", () => void refreshGallery());

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
    collaborationRequestActive || !collaborationModelReady || enabledCount === 0;
  collaborationSubmit.textContent = collaborationRequestActive
    ? "正在处理当前目标…"
    : !collaborationModelReady
      ? "等待本机模型就绪"
      : enabledCount
        ? `征求 ${enabledCount} 个角色的意见`
        : "至少启用一个评审角色";
  brainPlanSubmit.disabled = collaborationRequestActive || !collaborationModelReady;
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

function updateBrainStepStatus(stepIndex, state, message) {
  const status = brainStepStatusNodes[stepIndex];
  if (!status) return;
  status.dataset.state = state;
  status.textContent = message;
}

async function executeBrainStep(stepIndex) {
  const step = activeBrainPlan?.steps[stepIndex];
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
  const verifyButton = document.createElement("button");
  verifyButton.className = "icon-button brain-observation-verify";
  verifyButton.type = "button";
  verifyButton.textContent = "让墨灵核验结果";
  verifyButton.hidden = true;
  const verification = document.createElement("p");
  verification.className = "brain-verification";
  observationPanel.append(heading, status, resultNode, verifyButton, verification);
  if (!observationPanel.isConnected) brainPlanObservations.prepend(observationPanel);
  button.dataset.busy = "true";
  button.disabled = true;
  updateBrainStepStatus(
    stepIndex,
    "awaiting-approval",
    isCreate ? "等待创建审批" : "等待审批",
  );
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  try {
    const result = await window.companion.executeAgentTool(step.tool, step.arguments);
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
    button.disabled = false;
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
  conversation.replaceChildren(welcome);
  welcome.hidden = false;
  input.focus();
}

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
    characterStatus.textContent = "角色卡已切换；当前对话上下文已清空。";
    characterStatus.classList.remove("error");
  } catch (error) {
    document.getElementById("character-card-status").textContent =
      `切换角色失败：${error.message}`;
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

function updateAffect(state) {
  affectMood.value = state.mood;
  affectIndicator.textContent = `模拟状态 · ${state.label}`;
  affectIndicator.dataset.mood = state.mood;
  document.getElementById("topbar-avatar").dataset.mood = state.mood;
  document.getElementById("settings-avatar").dataset.mood = state.mood;
  affectReason.textContent = `状态线索：${state.reason}`;
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
    metadata.textContent = `来源：${memory.source} · ${created}`;

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

    actions.append(save, remove);
    entry.append(contentLabel, visibilityLabel, metadata, actions);
    memoryList.append(entry);
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
    void reflectOnConversation(currentCharacterId, conversationHistory);
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
    signature_lines: form
      .get("signature_lines")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
    avatar: avatarInput.value.trim() || null,
    voice: characterVoiceSelect.value || null,
    id: editingCharacterId,
  };
  try {
    await window.companion.saveCharacter(card);
    characterForm.dataset.dirty = "false";
    characterStatus.textContent = "角色卡资料与表现设置已保存。";
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
  refreshStatus();
  loadCharacter();
  loadCharacters();
  loadMemories();
  loadAffect();
  refreshVoiceResources();
});

characterForm.addEventListener("input", () => {
  characterForm.dataset.dirty = "true";
});

characterForm.addEventListener("change", () => {
  characterForm.dataset.dirty = "true";
});
