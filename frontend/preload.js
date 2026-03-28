const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // Native file dialogs
    openLibraryDialog: () => ipcRenderer.invoke('dialog:openLibrary'),
    openFolderDialog: () => ipcRenderer.invoke('dialog:openFolder'),

    // Window management
    openNewWindow: (route) => ipcRenderer.send('open-new-window', route),
});
