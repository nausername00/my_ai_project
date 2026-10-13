// K6 演出舞台 preload：帧保存与进度上报（渲染器 -> 主进程）
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("k6", {
  saveFrame: (dataURL, name) => ipcRenderer.invoke("k6:save-frame", { dataURL, name }),
  reportProgress: (info) => ipcRenderer.invoke("k6:progress", info),
  reportError: (message) => ipcRenderer.invoke("k6:error", message),
});
