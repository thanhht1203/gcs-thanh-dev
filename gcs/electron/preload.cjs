const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("eoDesktop", {
  platform: process.platform,
});
