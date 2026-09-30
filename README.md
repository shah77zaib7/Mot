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
One-time setup (installs the backend and builds the interface):

```
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
```

Then double-click `run.pyw` — the Mot window opens with no terminal.

On first run Mot creates `data/config.json` (providers and their models) and `data/mot.db` (chats).
Open **Settings → Models** to add a provider: pick a preset (Ollama, OpenRouter, Groq, ...),
fetch its models, tick the ones Mot may use. API keys are stored in Windows Credential Manager
and never in files or logs.

### If double-clicking does nothing
Windows must open `.pyw` files with the Python launcher. If the launcher's default Python
is missing or wrong, create `%LOCALAPPDATA%\py.ini` containing:

```ini
[defaults]
python=3.13
```

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
