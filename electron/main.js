const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let mainWindow;
let backendProcess;

const isDev = !app.isPackaged;

function startBackend() {
  const backendDir = path.join(__dirname, '..', 'backend');
  const pythonPath = process.platform === 'win32' ? 'python' : 'python3';

  backendProcess = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--port', '8765'], {
    cwd: backendDir,
    env: { ...process.env },
  });

  backendProcess.stdout.on('data', (data) => console.log(`[backend] ${data}`));
  backendProcess.stderr.on('data', (data) => console.error(`[backend] ${data}`));
  backendProcess.on('close', (code) => console.log(`[backend] exited with code ${code}`));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: 'SpendIQ',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const url = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, '..', 'frontend', 'dist', 'index.html')}`;
  mainWindow.loadURL(url);
  if (isDev) mainWindow.webContents.openDevTools();
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(() => {
  startBackend();
  // Wait for backend to start
  setTimeout(createWindow, 2000);
});

app.on('window-all-closed', () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill();
});
