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
  }),
);
