const { app, BrowserWindow, ipcMain, dialog, shell, Notification } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;
let backendProcess = null;

function isBackendReachable(port = 8000) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/health/live`, (res) => {
      resolve(res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function findPythonAndProject() {
  const candidateDirs = [
    path.resolve(__dirname, '../../'),
    path.resolve(process.cwd()),
    path.resolve(process.cwd(), '../'),
    path.resolve(process.resourcesPath, '../../../../'),
    'C:\\Users\\haris\\Desktop\\nanvi_ai_enterprise_assistant',
  ];

  for (const dir of candidateDirs) {
    const venvPython = path.join(dir, 'venv', 'Scripts', 'python.exe');
    const mainPy = path.join(dir, 'backend', 'main.py');
    if (fs.existsSync(venvPython) && fs.existsSync(mainPy)) {
      return { pythonExe: venvPython, projectDir: dir };
    }
  }
  return null;
}

async function ensureBackendStarted() {
  const online = await isBackendReachable();
  if (online) return;

  const found = findPythonAndProject();
  if (!found) return;

  try {
    backendProcess = spawn(
      found.pythonExe,
      ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'],
      {
        cwd: found.projectDir,
        detached: false,
        stdio: 'ignore',
        windowsHide: true,
      }
    );

    backendProcess.on('error', (err) => {
      console.error('Failed to spawn backend:', err);
    });

    // Wait up to 6 seconds for backend to become reachable
    for (let i = 0; i < 12; i++) {
      await new Promise((r) => setTimeout(r, 500));
      if (await isBackendReachable()) break;
    }
  } catch (err) {
    console.error('Error starting backend:', err);
  }
}

async function createWindow() {
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 1024,
    minHeight: 680,
    title: 'Nanvi AI Enterprise Assistant',
    backgroundColor: '#0a0d14',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false, // Allows cross-origin fetch to localhost:8000 from file://
    },
    show: false,
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    const indexPath = path.join(__dirname, '../dist/index.html');
    mainWindow.loadFile(indexPath);
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http:') || url.startsWith('https:')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Handlers
ipcMain.handle('dialog:selectFolder', async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Select Company Folder for Nanvi Assistant',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

ipcMain.handle('app:notification', (_event, { title, body }) => {
  if (Notification.isSupported()) {
    new Notification({ title: title || 'Nanvi AI', body }).show();
    return true;
  }
  return false;
});

ipcMain.handle('app:openExternal', (_event, url) => {
  if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
    shell.openExternal(url);
  }
});

// App Lifecycle
app.whenReady().then(async () => {
  await ensureBackendStarted();
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('will-quit', () => {
  if (backendProcess) {
    try {
      backendProcess.kill();
    } catch (_) {}
    backendProcess = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
