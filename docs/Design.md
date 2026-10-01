# Design — Mot UI

Goal: a calm, modern chat-app feel. Not a terminal, not a dashboard.

## Layout
- Left sidebar (collapsible): "New chat", chat history, Settings at the bottom.
- Main area: centered message column (max ~720px) with generous whitespace.
- Bottom: large rounded auto-growing input bar with Send, Stop (while generating), a disabled mic button (voice comes later), and a model dropdown to switch model.
- Model dropdown: grouped by provider (provider name + host as the group header), search box, a tag chip on every model (Free / Paid / Local / Unknown), current model shown on the trigger button. Switching works mid-chat; a "Manage models…" entry opens Settings.
- Empty state: "Mot" wordmark (text placeholder), one-line greeting, 3-4 suggestion chips ("Open YouTube", "Morning setup", "Gold news today").

## Messages
- User: right-aligned soft bubble. Mot: plain text on the page, markdown rendered, code blocks with copy button.
- Streaming with a subtle cursor. Copy and Regenerate under Mot messages.

## Action cards
When Mot does something (open URL, open app, install, routine, search) show a compact card: icon + short line ("Opened YouTube - searched 'lo-fi'"), status (running / done / failed), expandable details. Install shows an inline Confirm / Cancel card first.

News / web results render inside the same card as a list: headline as a real link (opens only
on click, new tab), source and age on a muted line under it, never auto-opened. A done news card
also carries a small "Summarize" button that sends exactly those headlines to the model for
4-6 short bullets with sources. When headlines are on screen the "Details" toggle is dropped —
the "as of HH:MM" line already says it.

## Settings (modal)
- Models: list of provider cards (name, host, model count, key "••••••••", active model chip) with Manage models / Edit / Delete. Delete asks for confirmation and also drops the key from keyring.
- Add / Edit provider form, in order: provider name (auto-filled from the base URL host or a preset, editable) → API key (masked, show/hide) → base URL → preset chips (Ollama, LM Studio, OpenRouter, Groq, DeepSeek, NVIDIA, OpenAI, Custom) → Fetch models.
- Fetch models shows a loading state, then a searchable checklist of models, each with a clickable tag chip (click sets Free or Paid and locks it), plus Select all / Select all free / Re-fetch / "Add model manually". No /models endpoint? The form offers manual entry instead.
- Routines: list of saved routines (name + numbered steps) with Add / Edit / Delete; the editor is a
  name field plus ordered step rows (Open website / Open app + value), move up / down, delete, save.
- Apps: preferred browser chips (System default / Chrome / Brave / Edge), the alias list (alias →
  app name, with a datalist of discovered apps), and a Re-scan button showing "N apps found · scanned …".
- Contacts: list of saved contacts (name · phone number · aliases) with Add / Edit / Delete; the
  editor is a name field, a phone number with a "include the country code" hint, and
  comma-separated aliases. Empty state suggests the phrase to try ("whatsapp Mom hi mom"), and the
  panel states the rule: Mot opens the chat with the message typed in — it never presses Send and
  never messages anyone who is not on this list.
- Feeds: one card per topic (gold, silver, crypto, markets) with its feed URLs, each row having
  an editable URL, a "Test" button (busy state reads "Testing…") and a delete; "Add feed" per
  topic and "Add topic" for a new one; then Save / Restore defaults and a muted line pointing at
  `data/feeds.json`. Empty state explains what a feed is for.
- Drex: one card — a one-line explanation, a "Check connection / Checking…" button, and a single
  result line. Success is the canned `✓ Drex is reachable — 93.5% "urgent" in 0.97 s`; failure is
  a red line with the reason, and a missing key adds a link to `drex.nace.ai/dashboard/api-keys`.
- Appearance: light / dark / system.

The tab row (Models / Apps / Routines / Contacts / Feeds / Drex / Appearance) wraps onto a
second line instead of scrolling; the active underline stays per-button.

## Look
- Font: system UI stack (Segoe UI Variable). Radius 12-16px. Soft borders, minimal shadows.
- Light: white / near-white. Dark: near-black, not pure black.
- One accent color as CSS variable --accent (default teal #14B8A6), changeable in one place.
- Logo and brand style are placeholders until decided.

## Behavior
- Enter sends, Shift+Enter newline, Esc stops generation, Ctrl+K new chat.
- UI never freezes. Errors are friendly inline messages ("Ollama isn't running. Start it or pick another model.") with a fix button when possible.
- Rate limit / quota (429): an amber banner "<model> hit its limit" with a Retry button and one-click chips for other saved models (free ones first) — clicking a chip switches model immediately.
- Handles window resize (sensible minimum width). Keyboard accessible.
