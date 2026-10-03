const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "companion",
  Object.freeze({
    health: () => ipcRenderer.invoke("companion:health"),
    modelStatus: () => ipcRenderer.invoke("companion:model-status"),
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
    transcribe: (audio, contentType) =>
      ipcRenderer.invoke("companion:transcribe", audio, contentType),
    synthesize: (text) => ipcRenderer.invoke("companion:synthesize", text),
    getCharacter: () => ipcRenderer.invoke("companion:get-character"),
    saveCharacter: (card) => ipcRenderer.invoke("companion:save-character", card),
    listCharacters: () => ipcRenderer.invoke("companion:list-characters"),
    createCharacter: (card) =>
      ipcRenderer.invoke("companion:create-character", card),
    selectCharacter: (characterId) =>
      ipcRenderer.invoke("companion:select-character", characterId),
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
    exploreRun: (payload) => ipcRenderer.invoke("companion:explore-run", payload),
    exploreReact: (payload) =>
      ipcRenderer.invoke("companion:explore-react", payload),
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
    executeAgentTool: (tool, arguments_) =>
      ipcRenderer.invoke("companion:execute-agent-tool", tool, arguments_),
    verifyAgentTool: (request) =>
      ipcRenderer.invoke("companion:verify-agent-tool", request),
    listMemories: () => ipcRenderer.invoke("companion:list-memories"),
    addMemory: (memory) => ipcRenderer.invoke("companion:add-memory", memory),
    updateMemory: (memoryId, memory) =>
      ipcRenderer.invoke("companion:update-memory", memoryId, memory),
    deleteMemory: (memoryId) =>
      ipcRenderer.invoke("companion:delete-memory", memoryId),
    getPrivacy: () => ipcRenderer.invoke("companion:get-privacy"),
    setPrivacy: (settings) => ipcRenderer.invoke("companion:set-privacy", settings),
    getAffect: () => ipcRenderer.invoke("companion:get-affect"),
    setAffect: (mood) => ipcRenderer.invoke("companion:set-affect", mood),
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
  }),
);
