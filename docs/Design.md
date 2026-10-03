# Design — Mot UI

Goal: a calm, modern chat-app feel. Not a terminal, not a dashboard.

## Layout
- Left sidebar (collapsible): "New chat", chat history, Settings at the bottom.
- Main area: centered message column (max ~720px) with generous whitespace.
- Bottom: large rounded auto-growing input bar with Send, Stop (while generating), a disabled mic button (voice comes later), and a model dropdown to switch model.
- Model dropdown: grouped by provider (provider name + host as the group header), search box, a tag chip on every model (Free / Paid / Local / Unknown), current model shown on the trigger button. Switching works mid-chat; a "Manage models…" entry opens Settings. A model that failed and is cooling down carries an amber **`resting 4:32`** chip that counts down live (refreshed once a second while the menu is open) — clicking it is still allowed and wakes it, because a cooldown only filters what Mot does *automatically*.
- Empty state: "Mot" wordmark (text placeholder), one-line greeting, 3-4 suggestion chips ("Open YouTube", "Morning setup", "Gold news today").

## Messages
- User: right-aligned soft bubble. Mot: plain text on the page, markdown rendered, code blocks with copy button.
- Streaming with a subtle cursor. Copy and Regenerate under Mot messages.
- **Switch notice**: when the router leaves a model, a short amber pill appears in the scroll
  area — `"fail-429 hit its limit, switched to ok-model"` — naming both models. It sits with the
  reply, is never a modal, and can appear more than once in a chat (each switch says so once).
- **When nothing answers**, one friendly block lists every model it tried and the reason for each,
  with a **Retry** button — no stack traces, no bare status codes.

## Action cards
When Mot does something (open URL, open app, install, routine, search) show a compact card: icon + short line ("Opened YouTube - searched 'lo-fi'"), status (running / done / failed), expandable details. Install shows an inline Confirm / Cancel card first.

News / web results render inside the same card as a list: headline as a real link (opens only
on click, new tab), source and age on a muted line under it, never auto-opened. A done news card
also carries a small "Summarize" button that sends exactly those headlines to the model for
4-6 short bullets with sources, and a muted footer line: `Updated HH:MM`, `· offline` when the
card came from the saved snapshot, and `· N of M sources failing` in red when the last refresh
lost some — that footer is the card's only clock, so the time never appears twice. When headlines
are on screen the "Details" toggle is dropped, because the footer already says when they are from.
A card that could not reach any source swaps its status pill for a **Retry** button (same request
again, no model call).

## Settings (modal)
- General (first tab): **"When I close the window"** — two radio cards, **Minimize to tray**
  (default) and **Quit Mot**; clicking a card saves it, no Save button. The tray card's muted
  line explains the one-time notice: the first close that only hides Mot pops a native box —
  "Mot is still running. It is in the notification area next to the clock — click its icon to
  bring the window back. Choose "Quit Mot" in that menu to close Mot for good." — recorded in
  `tray_notice_shown`, never repeated. Then **"Show / hide Mot"**: a field holding the current
  combo (Ctrl+Alt+M) with Save shortcut (Enter works too) and a muted line naming where the
  shortcut works; if the combo is taken, `hotkey_error` appears under it in red — `"Ctrl+Alt+M"
  is already used by another program. Pick a different shortcut.` — and the old shortcut stays. Then
  **"Start Mot when I sign in"**: an off-by-default checkbox whose muted line says Mot starts
  hidden in the tray and that only one entry for your own account is added. A muted footer
  points at `data/config.json` and the registry.
- Models: list of provider cards (name, host, model count, key "••••••••", active model chip) with Manage models / Edit / Delete. Delete asks for confirmation and also drops the key from keyring — **only that provider's key**: every provider owns a unique keyring ref, so removing one never touches another.
- **Auto-switch order** (below the provider cards): a plain ordered list of every saved model —
  number, checkbox, model name, provider, tag chip, and ↑/↓ to reorder — under the heading
  "When a model hits its limit, times out or goes missing, Mot tries the next ticked one down this
  list — once, then it stops. Tick a model to allow auto-switch into it; paid models stay off until
  you tick them." A muted footer spells out the rests: a few minutes (rate limit), half an hour
  (timeout or server error), 6 hours (missing), and that a resting model shows as `resting` in the
  model picker. Saves as it changes; no Save button.
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
- Feeds: a **refresh row first** — a "Refresh automatically" checkbox, an "every [2] hours" number
  field (0.25–24, saved on blur), a "Refresh now" button (busy state reads "Refreshing…"), and a
  muted line "Last updated HH:MM · all sources ok" or "· N of M sources failing". Below it, one
  card per topic in `data/feeds.json` (gold, silver, crypto, markets, forex) with its feed URLs,
  each row having an editable URL, a "Test" button (busy state reads "Testing…") and a delete;
  "Add feed" per topic and "Add topic" for a new one; then Save / Restore defaults and a muted
  line pointing at `data/feeds.json` and naming the current interval. Empty state explains what a
  feed is for. Restore defaults writes the four built-in topics over the file (see Memory.md).
- Drex: one card — a one-line explanation, a "Check connection / Checking…" button, and a single
  result line. Success is the canned `✓ Drex is reachable — 93.5% "urgent" in 0.97 s`; failure is
  a red line with the reason, and a missing key adds a link to `drex.nace.ai/dashboard/api-keys`.
- Appearance: light / dark / system, plus **Accent colour** — eight swatches and a native colour
  picker, with the line "Changes --accent: buttons, highlights and the model picker." Choosing one
  repaints the whole app immediately and saves itself.

The tab row (General / Models / Apps / Routines / Contacts / Feeds / Drex / Appearance) wraps
onto a second line instead of scrolling; the active underline stays per-button.

## Look
- Font: system UI stack (Segoe UI Variable). Radius 12-16px. Soft borders, minimal shadows.
- Light: white / near-white. Dark: near-black, not pure black.
- One accent color as CSS variable --accent (default teal #14B8A6), changeable in one place.
- Logo and brand style are placeholders until decided.

## Behavior
- Enter sends, Shift+Enter newline, Esc stops generation, Ctrl+K new chat.
- One Mot at a time: a second launch (shortcut, Start Menu, auto-start) asks the running window to
  come to the front and exits without a sound — never two windows, never two servers.
- The X closes to the tray by default (the notice above explains it once); the tray menu is
  Open Mot / Refresh news now / Quit Mot, left-click opens the window. Quit Mot ends everything:
  no pythonw left behind.
- The global shortcut (Ctrl+Alt+M) shows and hides the window from anywhere; Settings > General
  changes it, and an in-use combo is refused politely instead of stealing the old one.
- UI never freezes. Errors are friendly inline messages ("Ollama isn't running. Start it or pick another model.") with a fix button when possible.
- Rate limit / quota (429): an amber banner "<model> hit its limit" with a Retry button and one-click chips for other saved models (free ones first) — clicking a chip switches model immediately. On top of that the router now moves down the auto-switch list by itself and leaves the switch notice described above; the banner still appears when nothing in the list answers.
- Handles window resize (sensible minimum width). Keyboard accessible.
