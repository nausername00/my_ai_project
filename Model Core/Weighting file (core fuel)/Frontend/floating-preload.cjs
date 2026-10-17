const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "floating",
  Object.freeze({
    onNotification(callback) {
      if (typeof callback !== "function") {
        throw new TypeError("notification callback must be a function");
      }
      const listener = (_event, notification) => callback(notification);
      ipcRenderer.on("companion:notification", listener);
      return () =>
        ipcRenderer.removeListener("companion:notification", listener);
    },
    sendNotificationAction(notificationId, actionIndex) {
      return ipcRenderer.invoke(
        "companion:notify-action",
        notificationId,
        actionIndex,
      );
    },
    showMainWindow: () => ipcRenderer.invoke("companion:main-window-show"),
    hideFloating: () => ipcRenderer.invoke("companion:floating-hide"),
    expandFloating: () => ipcRenderer.invoke("companion:floating-expand"),
    collapseFloating: () => ipcRenderer.invoke("companion:floating-collapse"),
    sendChat: (text) => ipcRenderer.invoke("companion:floating-send-chat", text),
    onCharacterUpdated(callback) {
      if (typeof callback !== "function") {
        throw new TypeError("character update callback must be a function");
      }
      const listener = (_event, character) => callback(character);
      ipcRenderer.on("companion:character-updated", listener);
      return () =>
        ipcRenderer.removeListener("companion:character-updated", listener);
    },
    onSpeechState(callback) {
      if (typeof callback !== "function") {
        throw new TypeError("speech state callback must be a function");
      }
      const listener = (_event, speaking) => callback(speaking === true);
      ipcRenderer.on("companion:speech-state", listener);
      return () =>
        ipcRenderer.removeListener("companion:speech-state", listener);
    },
  }),
);
