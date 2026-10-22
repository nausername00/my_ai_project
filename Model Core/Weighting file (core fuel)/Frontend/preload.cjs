const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "companion",
  Object.freeze({
    health: () => ipcRenderer.invoke("companion:health"),
    modelStatus: () => ipcRenderer.invoke("companion:model-status"),
    // 墨灵生活状态机
    getLifeState: () => ipcRenderer.invoke("companion:life-state"),
    lifeWake: () => ipcRenderer.invoke("companion:life-wake"),
    onLifeEvent: (callback) => {
      if (typeof callback !== "function") {
        throw new TypeError("life event callback must be a function");
      }
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("companion:life-event", listener);
      return () => ipcRenderer.removeListener("companion:life-event", listener);
    },
    pullModel: () => ipcRenderer.invoke("companion:pull-model"),
    openOllamaDownload: () =>
      ipcRenderer.invoke("companion:open-ollama-download"),
    onModelProgress: (callback) => {
      if (typeof callback !== "function") {
        throw new TypeError("model progress callback must be a function");
      }
      const listener = (_event, progress) => callback(progress);
      ipcRenderer.on("companion:model-progress", listener);
      return () => ipcRenderer.removeListener("companion:model-progress", listener);
    },
    speechStatus: () => ipcRenderer.invoke("companion:speech-status"),
    speechVoices: () => ipcRenderer.invoke("companion:speech-voices"),
    transcribe: (audio, contentType) =>
      ipcRenderer.invoke("companion:transcribe", audio, contentType),
    synthesize: (text, voice, speakerId) =>
      ipcRenderer.invoke("companion:synthesize", text, voice, speakerId),
    voiceWakeSet: (enabled) =>
      ipcRenderer.invoke("companion:voicewake-set", enabled === true),
    voiceWakePause: () => ipcRenderer.invoke("companion:voicewake-pause"),
    voiceWakeResume: () => ipcRenderer.invoke("companion:voicewake-resume"),
    voiceWakeStatus: () => ipcRenderer.invoke("companion:voicewake-status"),
    onVoiceWakeEvent: (callback) => {
      if (typeof callback !== "function") {
        throw new TypeError("voice wake callback must be a function");
      }
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("companion:voicewake-event", listener);
      return () => ipcRenderer.removeListener("companion:voicewake-event", listener);
    },
    getCharacter: () => ipcRenderer.invoke("companion:get-character"),
    notifySpeechState: (speaking) =>
      ipcRenderer.invoke("companion:speech-state", speaking === true),
    saveCharacter: (card) => ipcRenderer.invoke("companion:save-character", card),
    listCharacters: () => ipcRenderer.invoke("companion:list-characters"),
    createCharacter: (card) =>
      ipcRenderer.invoke("companion:create-character", card),
    selectCharacter: (characterId) =>
      ipcRenderer.invoke("companion:select-character", characterId),
    deleteCharacter: (characterId) =>
      ipcRenderer.invoke("companion:delete-character", characterId),
    chooseAvatar: () => ipcRenderer.invoke("companion:choose-avatar"),
    getAvatar: (fileName) => ipcRenderer.invoke("companion:get-avatar", fileName),
    importModelAssets: () =>
      ipcRenderer.invoke("companion:import-model-assets"),
    getModelPreview: (assetName) =>
      ipcRenderer.invoke("companion:get-model-preview", assetName),
    listVoiceResources: () =>
      ipcRenderer.invoke("companion:list-voice-resources"),
    chooseVoiceReference: () =>
      ipcRenderer.invoke("companion:choose-voice-reference"),
    registerVoiceReference: (metadata, sample) =>
      ipcRenderer.invoke(
        "companion:register-voice-reference",
        metadata,
        sample,
      ),
    getVoiceReference: (id) =>
      ipcRenderer.invoke("companion:get-voice-reference", id),
    deleteVoiceReference: (id) =>
      ipcRenderer.invoke("companion:delete-voice-reference", id),
    generate: (prompt, history) =>
      ipcRenderer.invoke("companion:generate", prompt, history),
    analyzeImage: () => ipcRenderer.invoke("companion:analyze-image"),
    ocrAnalyze: () => ipcRenderer.invoke("companion:ocr-analyze"),
    discoverFile: () => ipcRenderer.invoke("companion:discover-file"),
    discoverContext: () => ipcRenderer.invoke("companion:discover-context"),
    partnersStatus: () => ipcRenderer.invoke("companion:partners-status"),
    fashionStatus: () => ipcRenderer.invoke("companion:fashion-status"),
    fashionOutfit: (outfitId, toneId) =>
      ipcRenderer.invoke("companion:fashion-outfit", outfitId, toneId),
    partnersPreview: (scope, partnerIds) =>
      ipcRenderer.invoke("companion:partners-preview", scope, partnerIds),
    partnersEvaluate: (scope, partnerIds, externalConsent) =>
      ipcRenderer.invoke(
        "companion:partners-evaluate",
        scope,
        partnerIds,
        externalConsent,
      ),
    exploreRun: (payload) => ipcRenderer.invoke("companion:explore-run", payload),
    exploreReact: (payload) =>
      ipcRenderer.invoke("companion:explore-react", payload),
    exploreSave: (payload) => ipcRenderer.invoke("companion:explore-save", payload),
    exploreWorks: () => ipcRenderer.invoke("companion:explore-works"),
    exploreWork: (payload) => ipcRenderer.invoke("companion:explore-work", payload),
    floatingToggle: () => ipcRenderer.invoke("companion:floating-toggle"),
    translate: (request) =>
      ipcRenderer.invoke("companion:translate", request),
    reflectAgent: (characterId, history) =>
      ipcRenderer.invoke("companion:reflect-agent", characterId, history),
    collaborateAgents: (task, roles) =>
      ipcRenderer.invoke("companion:collaborate-agents", task, roles),
    listAgentRoles: () => ipcRenderer.invoke("companion:list-agent-roles"),
    getSocialStatus: () => ipcRenderer.invoke("companion:social-status"),
    listSocialPartners: () =>
      ipcRenderer.invoke("companion:list-social-partners"),
    collaborateSocial: (task, roles) =>
      ipcRenderer.invoke("companion:collaborate-social", task, roles),
    createBrainPlan: (task, context) =>
      ipcRenderer.invoke("companion:create-brain-plan", task, context),
    listAgentTools: () => ipcRenderer.invoke("companion:list-agent-tools"),
    executeAgentTool: (tool, arguments_, traceId) =>
      ipcRenderer.invoke("companion:execute-agent-tool", tool, arguments_, traceId),
    cancelAgentTrace: (traceId) =>
      ipcRenderer.invoke("companion:cancel-agent-trace", traceId),
    listAgentTraces: (limit) =>
      ipcRenderer.invoke("companion:list-agent-traces", limit),
    createAgentTrace: (task, scope) =>
      ipcRenderer.invoke("companion:create-agent-trace", task, scope),
    miniGameExists: () => ipcRenderer.invoke("companion:mini-game-exists"),
    openMiniGame: () => ipcRenderer.invoke("companion:open-mini-game"),
    miniGameDraftStatus: () => ipcRenderer.invoke("companion:mini-game-draft-status"),
    miniGameDraftRead: () => ipcRenderer.invoke("companion:mini-game-draft-read"),
    miniGameDraftWrite: (content) =>
      ipcRenderer.invoke("companion:mini-game-draft-write", content),
    miniGameDraftReset: () => ipcRenderer.invoke("companion:mini-game-draft-reset"),
    miniGameDraftDiscard: () => ipcRenderer.invoke("companion:mini-game-draft-discard"),
    miniGameDraftPromote: () => ipcRenderer.invoke("companion:mini-game-draft-promote"),
    verifyAgentTool: (request) =>
      ipcRenderer.invoke("companion:verify-agent-tool", request),
    listMemories: () => ipcRenderer.invoke("companion:list-memories"),
    addMemory: (memory) => ipcRenderer.invoke("companion:add-memory", memory),
    updateMemory: (memoryId, memory) =>
      ipcRenderer.invoke("companion:update-memory", memoryId, memory),
    deleteMemory: (memoryId) =>
      ipcRenderer.invoke("companion:delete-memory", memoryId),
    memoryUsage: () => ipcRenderer.invoke("companion:memory-usage"),
    statusMetrics: () => ipcRenderer.invoke("companion:status-metrics"),
    getPerformanceRules: () =>
      ipcRenderer.invoke("companion:get-performance-rules"),
    savePerformanceRules: (rules) =>
      ipcRenderer.invoke("companion:save-performance-rules", rules),
    classifyCue: (text) =>
      ipcRenderer.invoke("companion:classify-cue", text),
    backupCreate: () => ipcRenderer.invoke("companion:backup-create"),
    exportMemories: () => ipcRenderer.invoke("companion:export-memories"),
    importMemories: () => ipcRenderer.invoke("companion:import-memories"),
    k6ExportStart: (payload) =>
      ipcRenderer.invoke("companion:k6-export-start", payload),
    k6ExportCancel: () => ipcRenderer.invoke("companion:k6-export-cancel"),
    k6ExportStatus: () => ipcRenderer.invoke("companion:k6-export-status"),
    getPrivacy: () => ipcRenderer.invoke("companion:get-privacy"),
    setPrivacy: (settings) => ipcRenderer.invoke("companion:set-privacy", settings),
    getProposals: () => ipcRenderer.invoke("companion:get-proposals"),
    updateProposalSettings: (settings) =>
      ipcRenderer.invoke("companion:update-proposal-settings", settings),
    respondProposal: (goalId, action) =>
      ipcRenderer.invoke("companion:respond-proposal", goalId, action),
    addGoal: (goal) => ipcRenderer.invoke("companion:add-goal", goal),
    updateGoal: (goalId, payload) =>
      ipcRenderer.invoke("companion:update-goal", goalId, payload),
    deleteGoal: (goalId) => ipcRenderer.invoke("companion:delete-goal", goalId),
    getAffect: () => ipcRenderer.invoke("companion:get-affect"),
    setAffect: (mood) => ipcRenderer.invoke("companion:set-affect", mood),
    avatarStatus: () => ipcRenderer.invoke("companion:avatar-status"),
    avatarAssess: (message) =>
      ipcRenderer.invoke("companion:avatar-assess", message),
    avatarAwaken: (avatarIds, confirmed, reason) =>
      ipcRenderer.invoke("companion:avatar-awaken", avatarIds, confirmed, reason),
    trioRoles: () => ipcRenderer.invoke("companion:trio-roles"),
    trioRun: (message, maxRounds) =>
      ipcRenderer.invoke("companion:trio-run", message, maxRounds),
    setAvatarDisplayMode: (mode) =>
      ipcRenderer.invoke("companion:set-avatar-display-mode", mode),
    exportMemories: () => ipcRenderer.invoke("companion:export-memories"),
    importMemories: () => ipcRenderer.invoke("companion:import-memories"),
    onNotificationAction: (callback) => {
      if (typeof callback !== "function") {
        throw new TypeError("notification action callback must be a function");
      }
      const listener = (_event, action) => callback(action);
      ipcRenderer.on("companion:notification-action", listener);
      return () =>
        ipcRenderer.removeListener("companion:notification-action", listener);
    },
    onFloatingChat: (callback) => {
      if (typeof callback !== "function") {
        throw new TypeError("floating chat callback must be a function");
      }
      const listener = (_event, text) => callback(text);
      ipcRenderer.on("companion:floating-chat", listener);
      return () =>
        ipcRenderer.removeListener("companion:floating-chat", listener);
    },
  }),
);
