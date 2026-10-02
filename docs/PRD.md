# PRD — Mot

## Vision
Mot is a personal AI agent for Windows with a clean chat interface. Type (later: speak) what you want — "open YouTube and search lo-fi music", "open the gold chart" — and Mot does it. It also answers research questions such as market news. It is not just a chatbot: it takes actions.

## Goals
- Speed up daily start-up work: one command replaces many manual clicks.
- Free and local first (Ollama). Any cloud API key is optional and switchable in Settings. No provider lock-in.
- Look and feel like a modern chat app, not a terminal.
- Later: voice in the user's own language.

## Core use cases
1. Websites and search: "open YouTube and search X", "open Chrome and go to ...".
2. Apps: "open WhatsApp", "install VLC" (winget, asks for confirmation).
3. Routines: "start my morning setup" opens a saved list of apps/URLs (e.g. TradingView gold chart on the 1-minute timeframe via URL, Chrome, WhatsApp).
4. Research: "why is gold moving today", "crypto news today" — searches the web and news feeds, then gives a short sourced summary.
5. Normal chat with any chosen model.

## Non-goals
- No trading: Mot never places, edits, or confirms trades.
- No arbitrary shell/PowerShell execution.
- No shared branding or code with other products; Mot for Windows is its own project.
- No account, no telemetry. Data stays on the laptop except calls to the model provider the user chose.
- No screen-clicking agent until Phase 12, the final optional phase.

## Success measures
- A routine runs in under 10 seconds with no model call.
- Simple commands ("open YouTube") work with no model call.
- Chat works fully offline with a local model.
- Switching between local and cloud model takes one click.
- App window opens in under 3 seconds (excluding model load).

## Constraints
Windows 10/11. Low cost. Small RAM footprint, since a local model runs alongside.
