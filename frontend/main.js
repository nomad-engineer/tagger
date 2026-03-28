const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Disable Hardware Acceleration to prevent Linux GPU sandbox crashes
app.disableHardwareAcceleration();

let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
        title: 'Image Tagger',
        autoHideMenuBar: false
    });

    // In development, load from Vite dev server. In production, load built index.html.
    if (process.env.NODE_ENV === 'development') {
        mainWindow.loadURL('http://localhost:3000');
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
    }

    mainWindow.on('closed', function () {
        mainWindow = null;
    });
}

function startPythonBackend() {
    // Determine path to python executable in virtualenv
    const isWin = process.platform === "win32";
    const pythonPath = isWin
        ? path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe')
        : path.join(__dirname, '..', 'venv', 'bin', 'python');

    console.log('Starting Python backend using:', pythonPath);

    // Need to run from correct working directory so it finds src module
    const backendCwd = path.join(__dirname, '..');

    pythonProcess = spawn(pythonPath, ['-m', 'uvicorn', 'src.main:app', '--port', '8000'], {
        cwd: backendCwd
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`Backend stdout: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Backend stderr: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Backend process exited with code ${code}`);
    });
}

app.whenReady().then(() => {
    startPythonBackend();
    // Give it a brief moment to start before trying to fetch initial data
    setTimeout(createWindow, 1500);

    app.on('activate', function () {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', function () {
    if (process.platform !== 'darwin') app.quit();
});

// Clean up python process when electron quits
app.on('quit', () => {
    if (pythonProcess) {
        if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
        } else {
            // Send SIGTERM
            pythonProcess.kill();
        }
    }
});

// ==========================================
// IPC Handlers
// ==========================================

// Open a native file dialog to pick a library.json file
ipcMain.handle('dialog:openLibrary', async () => {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: 'Open Image Library',
        filters: [
            { name: 'Library Files', extensions: ['json'] },
            { name: 'All Files', extensions: ['*'] }
        ],
        properties: ['openFile']
    });
    if (canceled || filePaths.length === 0) return null;
    return filePaths[0];
});

// Open a native folder dialog to create a new library
ipcMain.handle('dialog:openFolder', async () => {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: 'Select Folder for New Library',
        properties: ['openDirectory', 'createDirectory']
    });
    if (canceled || filePaths.length === 0) return null;
    return filePaths[0];
});

// Open new window for a pop-out panel (e.g., Tag Editor)
ipcMain.on('open-new-window', (event, route) => {
    let newWin = new BrowserWindow({
        width: 400,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
        title: 'Tag Editor'
    });

    if (process.env.NODE_ENV === 'development') {
        newWin.loadURL(`http://localhost:3000/#${route}`);
    } else {
        newWin.loadFile(path.join(__dirname, 'dist', 'index.html'), { hash: route });
    }
});
