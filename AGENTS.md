# AGENTS.md — Rules for coding agents working on Mot

Mot is a Windows desktop AI agent with a chat UI. It opens apps and websites, installs apps, runs routines, and answers research/news questions.

Read these before coding:
- docs/Memory.md — current status, decisions, known issues (read FIRST every session)
- docs/Phases.md — the build plan (find the current phase)
- docs/PRD.md — what Mot does and does not do
- docs/Architecture.md — stack, folders, tool design (read before backend work)
- docs/Design.md — UI rules (read before frontend work)

## Workflow
1. Read docs/Memory.md, then the current phase in docs/Phases.md.
2. Build only the current phase. Do not add features from later phases.
3. Never start the next phase until the user explicitly confirms.
4. Run the app and test it before saying a task is done. Fix errors yourself.
5. At the end, update docs/Memory.md (done, next, decisions, bugs).
6. If something is unclear, pick the simplest option, note it in Memory.md, and continue. Ask only when blocked.

## Code rules
- Python 3.11+, type hints, small functions, small files. Simple over clever.
- **Never hardcode a data or log path.** User data lives in `%APPDATA%\Mot` and
  everything goes through `backend/core/paths.py` (`paths.data_dir()`,
  `paths.log_dir()`); `MOT_DATA_DIR` overrides the whole folder — that is what
  the tests use. Program files (code, assets, frontend/dist) come from
  `paths.program_root()`.
- Frontend: React + Vite + Tailwind. No heavy UI libraries unless truly needed.
- Add a dependency only if necessary. Record it in requirements.txt / package.json and in Memory.md.
- Never copy code from third-party repositories; their licenses may restrict Mot. Implement from
  the specs in docs/ in your own words.
- Windows first: use pathlib, no Linux-only commands.
- Log to logs/mot.log. Never log secrets.

## Speed and cost rules
- Prefer plain code over LLM calls. Anything deterministic (open URL, open app, routines) must work with no model.
- Keep prompts and tool descriptions short. Keep the tool list small.
- Stream model responses. Never block the UI thread.
- Must work with local models (Ollama) and cloud APIs. Never hardcode a provider.

## Safety rules
- API keys only in Windows Credential Manager (keyring). Never in files, logs, or git.
- Ask the user to confirm before installing apps or any action that changes the system.
- No arbitrary shell/PowerShell execution from model output. Only the tools defined in docs/Architecture.md.
- Mot never places trades and never clicks order/buy/sell buttons.
- Create .gitignore with: .env, data/, logs/, node_modules/, dist/, __pycache__/, *.db

## Definition of done (every phase)
- App launches by double-clicking the **Desktop shortcut** (pythonw.exe on run.pyw) with no
  terminal window. Do not rely on Explorer's .pyw association — it may open IDLE instead.
- Everything in the phase checklist works.
- No crashes on bad input; errors are friendly.
- docs/Memory.md updated.
- At the end of every phase, tell the user how to launch Mot themselves (the Desktop shortcut),
  verify that exact route, close anything you started, and never leave test data or windows behind.
