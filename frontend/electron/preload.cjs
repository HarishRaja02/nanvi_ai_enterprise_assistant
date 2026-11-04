const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  platform: process.platform,
  selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),
  showNotification: (title, body) => ipcRenderer.invoke('app:notification', { title, body }),
  openExternal: (url) => ipcRenderer.invoke('app:openExternal', url),
  onAccountBlocked: (callback) => {
    ipcRenderer.on('account-blocked', () => callback());
  },
});

