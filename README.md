# Mot

Mot is a personal AI agent for Windows with a chat interface. Tell it what you want — "open YouTube and search lo-fi", "start my morning setup", "crypto news today" — and it does it. It runs on free local models (Ollama) or any API key you add.

Status: in development. See docs/Phases.md.

## Requirements
Windows 10/11, Python 3.11+, Node.js LTS. Optional: Ollama for local models.

```
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
winget install Ollama.Ollama
ollama pull qwen2.5:7b
```

## Run
One-time setup (installs the backend, builds the interface, creates the shortcuts):

```
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python tools\make_shortcut.py
```

Then double-click **Desktop → Mot**. The window opens with no terminal: the shortcut runs
`pythonw.exe` on `run.pyw`, so it never depends on how Windows happens to open `.pyw` files.
`tools\make_shortcut.py` writes the Desktop and Start Menu shortcuts (icon: `assets\mot.ico`)
and does not touch any file association. Re-run it if a shortcut goes missing.

On first run Mot creates `data/config.json` (providers and their models) and `data/mot.db` (chats).
Open **Settings → Models** to add a provider: pick a preset (Ollama, OpenRouter, Groq, ...),
fetch its models, tick the ones Mot may use. API keys are stored in Windows Credential Manager
and never in files or logs.

### If Mot cannot start
Nothing fails silently. A missing interface build, a missing Python package, a port already in
use or any other startup error appends the traceback to `logs/crash.log` **and** opens a
"Mot could not start" message box that says what to do about it.

### If double-clicking run.pyw opens IDLE
That is Windows' `.pyw` file association, not Mot — Explorer hands the file to whatever program
owns it. Mot does not change file associations. Use the Desktop shortcut, or start it from a
terminal with `pythonw run.pyw`.

### Development
```
python -m backend.main --serve --port 8747     # server only: http://127.0.0.1:8747
cd frontend && npm run dev                     # Vite dev server, proxies /api to :8747
```
Logs go to `logs/mot.log`; startup failures are appended to `logs/crash.log`.

## Project docs
- AGENTS.md — rules for coding agents
- docs/PRD.md, Architecture.md, Design.md, Phases.md, Memory.md

## Building with opencode
Open this folder in opencode and prompt:

> Read AGENTS.md and docs/, then build Phase 2.
