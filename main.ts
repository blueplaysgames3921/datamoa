import { app, BrowserWindow, ipcMain, shell } from 'electron'
import * as path from 'path'
import { spawn, ChildProcess } from 'child_process'
import { registerAgentHandlers } from './ipc/agents'
import { registerConfigHandlers } from './ipc/config'
import { registerPipelineHandlers } from './ipc/pipeline'
import { registerSystemHandlers } from './ipc/system'
import { initWebSocketBridge, destroyWebSocketBridge } from './wsBridge'

let mainWindow: BrowserWindow | null = null
let pythonProcess: ChildProcess | null = null

export const PYTHON_PORT = parseInt(process.env.DATAMOA_PORT || '7532', 10)
const isDev = process.env.NODE_ENV === 'development'

// ─── Window ──────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#0a0a0f',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 16, y: 16 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: !isDev,
    },
    show: false,
    frame: process.platform !== 'darwin',
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
    // Start WS bridge after window is ready
    initWebSocketBridge(mainWindow!, PYTHON_PORT)
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ─── Python Backend ───────────────────────────────────────────────────────────

async function startPythonBackend(): Promise<void> {
  const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3'

  const scriptPath = isDev
    ? path.join(__dirname, '../../core/main.py')
    : path.join(process.resourcesPath, 'core/main.py')

  const env = {
    ...process.env,
    PYTHONPATH: isDev ? path.join(__dirname, '../..') : process.resourcesPath,
    DATAMOA_PORT: String(PYTHON_PORT),
  }

  pythonProcess = spawn(
    pythonExecutable,
    [scriptPath, '--port', String(PYTHON_PORT)],
    { stdio: ['pipe', 'pipe', 'pipe'], env }
  )

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    process.stdout.write(`[Python] ${data}`)
  })

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    process.stderr.write(`[Python ERR] ${data}`)
  })

  pythonProcess.on('close', (code) => {
    console.log(`[Python] Process exited: ${code}`)
    pythonProcess = null
  })

  pythonProcess.on('error', (err) => {
    console.error('[Python] Failed to start:', err.message)
  })

  // Wait for backend to be ready (poll /health)
  await waitForBackend(PYTHON_PORT, 30)
}

async function waitForBackend(port: number, maxAttempts: number): Promise<void> {
  const http = require('http')
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(resolve => setTimeout(resolve, 500))
    try {
      await new Promise<void>((resolve, reject) => {
        const req = http.get(`http://localhost:${port}/health`, (res: any) => {
          if (res.statusCode === 200) resolve()
          else reject(new Error(`Status ${res.statusCode}`))
        })
        req.on('error', reject)
        req.setTimeout(1000, () => { req.destroy(); reject(new Error('timeout')) })
      })
      console.log(`[Main] Backend ready after ${(i + 1) * 500}ms`)
      return
    } catch {
      // Backend not ready yet — keep polling
    }
  }
  console.warn('[Main] Backend health check timed out — proceeding anyway')
}

// ─── IPC ─────────────────────────────────────────────────────────────────────

function registerIPC() {
  registerAgentHandlers(ipcMain)
  registerConfigHandlers(ipcMain)
  registerPipelineHandlers(ipcMain)
  registerSystemHandlers(ipcMain)

  // Window controls for non-macOS
  ipcMain.on('window:minimize', () => mainWindow?.minimize())
  ipcMain.on('window:maximize', () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize()
    else mainWindow?.maximize()
  })
  ipcMain.on('window:close', () => mainWindow?.close())
  ipcMain.on('shell:openPath', (_event, path: string) => { shell.openPath(path) })
}

// ─── App Lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIPC()
  await startPythonBackend()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  destroyWebSocketBridge()
  if (pythonProcess) {
    pythonProcess.kill('SIGTERM')
    // Force kill after 3s if still running
    setTimeout(() => pythonProcess?.kill('SIGKILL'), 3000)
    pythonProcess = null
  }
})
