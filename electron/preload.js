const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  selectFiles: (filters) => ipcRenderer.invoke('select-files', filters),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
});
