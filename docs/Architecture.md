# Architecture — Mot

## Stack
- Backend: Python 3.11+, FastAPI (localhost only), streaming via SSE or WebSocket
- Frontend: React + Vite + Tailwind, built to static files served by FastAPI
- Shell: pywebview (native window, no browser tab, no terminal)
- Models: litellm (one interface for all providers, including Ollama / LM Studio)
- Storage: SQLite (chats), config.json (settings), keyring (API keys)
- Tray: pystray + Pillow (icon, menu) — the only new dependencies; the hotkey and the single
  instance are ctypes, no dependency
- Search/news: ddgs (DuckDuckGo, no key) + feedparser (RSS)
- YouTube: yt-dlp (`ytsearch1:` metadata lookup for play_youtube — no API key, no download)
- Phase 8A/8B: faster-whisper (local, multilingual voice) + text-to-speech

## Flow
```
User input -> Router
  A) Fast path: every segment matched by a rule/alias -> run tools directly, NO LLM
  B) LLM path (leftover segments only): model picks tool(s) via tool calling
     -> validate against the registry -> run -> one short summary line (no model)
     -> or the model just answers the question
Both paths drop a plain "open X" when a later step opens the same host anyway:
one site = one tab (drop_covered_opens).
Every tool run emits an "action" event -> UI shows an action card.
The path taken is logged as `path=fast` / `path=llm` / `path=llm->chat`.
```

## Folders
```
Mot/
├── AGENTS.md, README.md, docs/
├── run.pyw               # double-click launcher — started by the Desktop shortcut, which calls
│                         # pythonw.exe on it (Explorer's .pyw association opens IDLE);
│                         # one-instance gate + a plain-English crash box (never silence)
├── tools/                # make_shortcut.py (Desktop + Start Menu .lnk), mot_icon.py (assets/mot.ico)
├── assets/               # mot.ico: bold "M." on a dark rounded square, generated locally
├── backend/
│   ├── main.py           # FastAPI app + pywebview start (all heavy imports are lazy)
│   ├── api/              # chat, chats, providers, apps, routines, contacts, feeds, drex, actions,
│   │                     # general (Settings > General)
│   ├── core/llm.py       # litellm wrapper, model switching, streaming, timeouts, error kinds
│   ├── core/fallback.py  # Phase 6: ordered candidates, cooldowns, switch notices, routing
│   ├── core/capabilities.py # Phase 6: "Can: … / Cannot: …" built from the tool registry
│   ├── core/fetch.py     # GET {base}/models (+ /api/tags), presets, tags
│   ├── core/drex.py      # Drex client (stdlib urllib, injectable transport)
│   ├── core/feeds.py     # data/feeds.json + RSS fetch, cache, 48 h window, refresh_all/read_topic
│   ├── core/snapshot.py  # data/market_ingest/latest.json (3 h stale, per-source status)
│   ├── core/ingest.py    # background refresh thread (startup + every interval_hours)
│   ├── core/phrases.py   # data/news_phrases.json — "aj gold" etc., no model call
│   ├── core/router.py    # fast path: parse_parts -> (steps, segments it can't parse)
│   ├── core/llm_router.py # LLM path: tool calling or strict JSON, validated, retried once
│   ├── core/config.py    # config.json (providers + general) + keyring
│   ├── core/singleinstance.py # named mutex + wake event: one Mot, second launch comes to front
│   ├── core/windowctl.py # show / hide / toggle / quit, the X -> tray policy, the one-time notice
│   ├── core/tray.py       # pystray icon (lazy): Open Mot / Refresh news now / Quit Mot
│   ├── core/hotkey.py     # RegisterHotKey on a message-only window, no extra dependency
│   ├── core/autostart.py  # HKCU ...\\CurrentVersion\\Run -> pythonw run.pyw --background
│   ├── core/contacts.py  # data/contacts.json (Settings > Contacts), conservative matching
│   ├── core/db.py        # SQLite chats
│   └── tools/            # one file per tool + registry.py (news.py, websearch.py, …)
├── frontend/             # React app (src/, dist/)
├── data/                 # LEGACY first-run location — migrated into %APPDATA%\Mot, never
│                         # written to after that (gitignored)
├── .env                  # DREX_API_KEY only — gitignored, never logged (see Drex)
└── logs/                 # program-side logs next to the code (see "Where data lives")
```

## Where data lives
Nothing picks a data path by hand: `backend/core/paths.py` is the only place that decides.

| Kind | Comes from | Example |
|---|---|---|
| User data | `paths.data_dir()` | `%APPDATA%\Mot\mot.db`, `config.json`, `contacts.json`, `feeds.json`, `apps.json`, `routines.json`, `news_phrases.json`, `market_ingest/` |
| Logs | `paths.log_dir()` | `%APPDATA%\Mot\logs\mot.log`, `crash.log` |
| Program files (code, assets, `frontend/dist`) | `paths.program_root()` | `C:\Mot\` |

- `MOT_DATA_DIR` overrides the whole data folder. That is what the tests use — a temp
  directory per run, so no test ever touches real user data.
- **First run migrates the legacy location**: if `%APPDATA%\Mot` has no `mot.db` and
  `C:\Mot\data` does, `backend/core/migrate.py` copies only the files that are missing,
  writes `C:\Mot\data-backup-<timestamp>` next to the source, and logs
  `copied N item(s), M already there, backup at …`. It never overwrites a destination that
  already has data; when it has to leave something behind it logs a WARNING naming every
  skipped item with its source and backup path. The result is logged too (`failed: []`).
- The migration runs after the splash is up and before the window is created, so the user
  never sees an empty app on a machine that already had data.
- Everything logs through `paths.log_dir()`; `mot.log` rotates, and a traceback also lands in
  `crash.log`. Secrets are never logged. Files are written UTF-8 explicitly
  (`encoding="utf-8", errors="replace"`), so Urdu and emoji survive — covered by
  `tests/test_logs_utf8.py`.

## Providers and models (data/config.json)
```json
{
  "active": {"provider_id": "p-local-ollama", "model_id": "qwen2.5:7b"},
  "theme": "system",
  "accent": "#14b8a6",
  "fallback": [
    {"provider_id": "p-local-ollama", "model_id": "qwen2.5:7b", "auto": true},
    {"provider_id": "p-mock", "model_id": "ok-model", "auto": true}
  ],
  "providers": [
    {"id": "p-local-ollama", "name": "Local Ollama", "base_url": "http://localhost:11434",
     "key_ref": null,
     "models": [{"id": "qwen2.5:7b", "tag": "local", "tag_locked": false}]}
  ]
}
```
- One provider holds many models. `tag` is `free | paid | local | unknown`; `tag_locked`
  means the user set it by hand, so a re-fetch never overwrites it.
- API keys live in keyring under a **unique** ref, `mot-<provider id>-<random 8 hex>`; this file
  and every API response only ever carry `has_key` / a `••••••••` mask. `key_ref` is the keyring
  *account name*, not a key. Two providers can never collide, and `delete_provider()` only
  deletes the key when no other provider still shares that ref.
- `accent` is the Settings > Appearance colour (`#rrggbb`, validated by `ACCENT_RE`, default
  `#14b8a6`); the frontend paints `--accent`, `--accent-strong` and `--accent-ink` from it.
- `fallback` is the **auto-switch order** (Settings > Models): first entry is tried first, and
  `auto` is the "allow auto-switch into this model" tick. A Paid-tagged model stores `auto:false`
  unless the user ticks it, so Mot never silently spends money. Entries with no tick are still
  offered for manual picking.
- The **backend** fetches the model list (the browser never calls the provider):
  `GET {base_url}/models`, then `{origin}/models`, then `{origin}/api/tags` (Ollama).
  Presets and tag rules live in `backend/core/fetch.py`.
- Chat calls: `openai/<model>` + `api_base` + `api_key` for OpenAI-compatible providers,
  `ollama/<model>` for native Ollama (base URL port 11434).
- The old Phase 1 `profiles` list is migrated automatically on first load.

## Tools (only these; each returns {ok, message, data})
- open_url(url) — preferred browser (data/apps.json `browser`: default/chrome/brave/edge), else system default
- search_in_browser(site, query) — build a search URL (YouTube, Google, Bing, DuckDuckGo, Maps) and
  open it; an unknown site falls back to a Google search
- open_app(name) — discovery in data/apps.json: Start Menu .lnk (all users + current user) + UWP from
  Get-StartApps, cached at start-up and via Re-scan; fuzzy match, aliases in Settings; UWP launches
  with `explorer.exe shell:AppsFolder\<AppID>`
- install_app(name) — `winget search` first, then a Confirm card; on Confirm:
  `winget install --id <id> -e --silent --accept-package-agreements --disable-interactivity`
- play_youtube(query) — yt-dlp `ytsearch1:` metadata lookup (`--skip-download`, no API key, 25 s
  timeout), then open `watch?v=<id>`; if the lookup fails it opens the search results page and
  says so. Reads `ytdlp_command()`: the `yt-dlp` exe on PATH, else `python -m yt_dlp`
- whatsapp_message(contact, text) — resolve the contact in data/contacts.json, then stop at a
  Confirm card holding the contact and the text. Only after Confirm does `whatsapp.open_chat()`
  run: `whatsapp://send?phone=&text=` first, `https://wa.me/<number>?text=` when Windows has no
  handler for the scheme. It never presses Send
- web_search(query) — ddgs; returns titles, snippets, links (Phase 4)
- get_news(topic) — RSS feeds per topic (gold, silver, crypto, markets) from data/feeds.json (Phase 4)
- run_routine(name) — runs steps in data/routines.json (list of tool calls, no LLM)

Adding a tool = one file in tools/ + one registry entry with a short description and JSON schema.
`backend/tools/launch.py` starts apps, URLs and custom schemes; `install.py` and `play.py` run
their helper CLI (winget, yt-dlp) themselves — so tests replace four functions: `launch.open_url`,
`launch.open_scheme`, `install.run_winget`, `play.run_ytdlp`.

## Fast path
Regex/alias rules for common commands ("open X", "open X and search Y", "search Y on <site>",
"go to <url>", "install X", "play X on youtube", "run <routine>"), chained with and/then.
`router.parse_parts(text)` returns `(steps, unmatched segments)`: rules the code recognises run
with no model at all, and **only** the leftovers go to the LLM path. When every segment matched,
the model is never called.
Two Phase 3.5 guards:
- `drop_covered_opens()` removes a plain `open_url` when a later step opens the *same host*
  (a search, `play_youtube`, or another open) — one site, one tab. Hosts are compared exactly
  (minus `www.`), so a Google-fallback search never covers "open gmail".
- a bare segment only becomes `open_app` when `apps.claims()` says the name really *is* that
  app — the fuzzy matcher alone would read "whatsapp zara hi" as WhatsApp and swallow a message
  that has to reach the WhatsApp tool instead.

## LLM path (core/llm_router.py)
For the leftover segments only:
- Short system prompt (< 1000 chars, `PROMPT_BUDGET`, built for 3B-4B local models): the tool
  list is passed as native `tools=`; the prompt names only known **sites** and saved **routine**
  names — the app list is never in a prompt, the model writes the name and `open_app` resolves it
  with the same fuzzy match/aliases the fast path uses.
- The capabilities line is generated at **runtime** by `core/capabilities.py` from
  `registry.TOOLS`: a `Can:` half (one verb per registered tool) and a `Cannot:` half (fixed
  safety rules plus "confirm its own actions"). Adding or removing a tool changes the prompt on
  the next request — no prompt string is ever maintained by hand. `_fit()` truncates the
  Known websites / Saved routines lists to keep the whole `_system()` under the budget.
- Native tool calling first. If the provider rejects `tools=` (or the model just writes JSON),
  fall back to a strict `{"steps":[...]} / {"reply":"..."}` answer; that provider stays in JSON
  mode for the session (`_JSON_ONLY`).
- Every call is checked against `registry` (known tool, required args, text values). One retry
  with the reason appended to the prompt; if it is still invalid, fall back to a normal chat
  completion. Nothing here raises except `llm.LLMError`, and the reply line is the same
  deterministic `runner.summary()` the fast path uses.
- `install_app` and `whatsapp_message` stop at the Confirm card exactly as on the fast path —
  the model can never install or send without confirmation.
- Model steps go through `router.drop_covered_opens()` too, so a model that says "open youtube"
  *and* "search on youtube" still produces one tab.
- The raw model reply (`content` + `tool_calls`) is logged as `LLM router raw [...]`.

## Model fallback and timeouts (core/fallback.py, core/llm.py)
Every LLM call is routed through `fallback`, so a sick model costs one attempt, not a hang:
- **Timeouts.** `llm.timeout()` = `max(MIN_TIMEOUT = 10.0 s, REQUEST_TIMEOUT)` and is enforced
  with `asyncio.wait_for` around both the first chunk and every later chunk (`_await_call`,
  `_first_chunk`). A model that never answers is a friendly error, never a stuck UI.
- **Error kinds.** `llm.friendly()` classifies the failure into
  `rate_limit | timeout | server | not_found | key_invalid` (carried on `LLMError.kind`);
  connection refused / unreachable and anything else stays `kind=None` and is shown as before.
- **Cooldowns** (`fallback.COOLDOWN`, in-memory only, cleared on restart):
  429 → 300 s, timeout and 5xx → 1800 s, 404 → 21600 s, 401/403 → `key_invalid` with **0 s**
  (switch immediately but do not rest it — the key may be fixed any second).
- **`candidates(target)`** puts the requested model first (unless it is cooling), then walks
  `config.fallback_list()` skipping unticked, cooling and duplicate entries — the list is walked
  **once**, so a request can never loop. An empty list falls back to `[target]`.
- **`route()`** returns `{decision, profile, notices}`; a switch appends a notice built by
  `fallback.notice()` — `"fail-429 hit its limit, switched to ok-model"` — which `api/chat.py`
  emits as an SSE `switch` event above the reply. When every candidate fails,
  `fallback.exhausted()` produces a friendly list of each model and why it failed, plus a Retry
  (`fallback_exhausted` on the error event).
- **`fallback.stream()`** yields `("notice", text)` then `("delta", text)`. It only switches
  **before** the first delta; once text is on screen it re-raises rather than splicing two
  models' replies together.
- **Manual switching always works**: picking a resting model in the picker calls
  `POST /api/providers/wake` → `fallback.wake()`, which clears just that model's cooldown.
  Cooldowns only ever filter *automatic* moves, and they are reported to the UI as
  `resting: [{model_id, left}]` so the picker can show `resting m:ss`.
- **Paid models** are never switched into unless their `auto` tick is set.

## Research (news / "why is X moving")
`backend/core/feeds.py` owns `data/feeds.json` (`{topic: [url, …]}`): 8 s per request, feeds for
a topic fetched in parallel (ThreadPoolExecutor, max 8), 10 min cache per topic (5 min for
searches), dedupe by URL, newest first, last 48 h with a newest-first fallback when the window
is empty. `feedparser` is imported lazily inside the fetch so a run that never reads news costs
nothing. Topics are whatever the file holds — gold, silver, crypto, markets, forex — and
`topic_key()` checks the saved keys **before** `ALIASES`, so a real `forex` topic beats the alias
that used to fold it into markets.

### The saved snapshot (backend/core/snapshot.py)
`refresh_all()` reads every URL of every topic in one `_fetch_map()` (per-source status logged as
`ingest <host>: …`; one dead feed never fails the run) and writes
`data/market_ingest/latest.json` — headlines and links only (title, url, source, published_at,
fetched_at, topic), never article text — plus the per-source error map. `STALE_AFTER = 3 h`.

`feeds.read_topic(topic)` answers in this order: hot in-memory cache → saved snapshot (if it is
younger than 3 h) → **one** bounded live read → the snapshot again with `offline: True`.
`feeds.mixed_items()` runs that for gold + crypto + markets and returns the newest `limit`
together, which is how an ambiguous request gets one card instead of three.

### The background refresh (backend/core/ingest.py)
A plain daemon `threading.Thread` started from `main()` (never from `create_app()`, so TestClient
never reaches the network): run once at startup, then every `interval_hours` (default 2). The loop
wakes every 30 s, so the interval/toggle in Settings > Feeds applies without waiting out the old
value; `refresh_now()` takes a busy lock and `POST /api/feeds/refresh` runs it with
`asyncio.to_thread`. Settings live next to the snapshot in `data/market_ingest/settings.json`;
`last_ingest_at` comes from the snapshot itself, so it survives a restart.

### Phrases (backend/core/phrases.py)
`data/news_phrases.json` (editable, no restart) maps wording like "aj gold", "aaj news",
"market update today" or "gold aur bitcoin" straight onto a `get_news` step — `topic: "mixed"`
means gold + crypto + markets, newest first, max 12. Every phrase also needs a word from
`require_any`, which is what stops a bare "aj" from firing. Phrases are tried before the
`<topic> news` rule and skipped when the segment starts with an explicit verb (`open`, `search`, …).

The model's tool calls never see their own results, so research is a **second completion**:
1. Fast path first — `"<topic> news"` / `"gold news today"` runs `get_news` with NO model and
   renders a news card (headlines + Summarize button). Matching ignores case, punctuation,
   spacing and trailing filler, so `gold-news!` and `Gold news today?` land on the same card.
   An unresolvable topic becomes `web_search`; a sentence that merely ends in "news"
   ("good news") falls through to the model. Regenerate parses too, so re-running a news message
   brings the card back instead of a plain reply.
   If feeds and the snapshot both fail, `get_news` tries a plain `web_search` and only then
   returns `"Couldn't reach the news sources."` + `data.retry` → the card's **Retry** button.
2. **Safety net** — when no rule matched but the whole message is clearly a news request
   (`router.news_steps()`: a known topic word plus a news/headline word), `api/chat.py` runs that
   card instead of asking the model, so a clear news request can never end as plain chat. A
   question about *why* something moves has no headline word and stays with the model on purpose.
3. `api/chat.py` runs the normal loop, then collects `llm_router.findings_from(actions)`
   (title, source, age, URL per item; HTML stripped, 24 items max) and streams a second
   completion built by `llm_router.research_messages()` with `RESEARCH_SYSTEM` — **tools are
   never offered there**, so retrieved web text can never trigger an action, and the reply is
   written in the question's language when the model can.
4. `llm_router.research_footer()` appends `*As of HH:MM*` and `*Context, not trading advice.*`
   deterministically; the model never has to remember them. When a research reply exists the
   `runner.summary()` prefix is suppressed (`chat.compose()` returns the reply alone).
5. The Summarize button posts `ChatIn.findings` — fast path and router are both skipped and
   the research completion runs on exactly those headlines.

## Drex (backend/core/drex.py)
`POST {base}/v1/systemone` with `Authorization: Bearer $DREX_API_KEY` → a calibrated
probability per question (`answers.<id>.noul`). Stdlib urllib only, `transport` injectable for
tests, `DrexError(message, code)` with codes `no_key auth busy timeout unreachable
bad_request bad_response`. The key comes from the process env or a hand-rolled `.env` parser —
**the one documented exception to keyring-only**: `C:\Mot\.env` is gitignored (`.env*`), never
logged, never returned by an API, and only ever copied into the Authorization header.
`POST /api/drex/check` is one canned round trip for the Settings > Drex button; a missing key
points at `https://drex.nace.ai/dashboard/api-keys`.

## Window, tray and startup (backend/core/…)
- **Startup** must stay light: `run.pyw` sets a timestamp, gates on the single instance, and
  `backend/main.py` lazy-imports everything heavy inside functions (litellm ~10 s is only touched
  when a model is actually called; pystray +PIL only for the icon; webview only for the window).
  Two costs are irreducible: `import fastapi, uvicorn` (2.6 s measured, ~0.9 s with warm caches —
  the server must answer before the window can load a page) and WebView2 starting (~2.5 s).
  Measured end to end from the Desktop shortcut: **3.10 s warm, 8.78 s cold** (`--background`
  12.42 s once on a loaded machine). The app logs its own number as
  `startup: window on screen after N s`, and a broken path is obvious there — the hotkey thread
  used to burn its whole 10 s timeout and pushed this to 14.08 s.
- **One instance** (`singleinstance.py`, ctypes only): a named mutex plus an auto-reset event and
  a daemon listener. The first `acquire()` wins and starts listening; a second launch opens the
  event (so the first wakes and shows its window), steps aside and exits 0 — no second window, no
  second server. `--background` acquires with `wake=False`, so auto-start never pops a window over
  the one you are using. The gate runs in `run.pyw` before `check_frontend()`.
- **Tray** (`tray.py`, pystray + Pillow — the only new dependencies, recorded in requirements.txt):
  icon `assets/mot.ico`, left-click = Open Mot (the menu's `default=True` item), menu =
  Open Mot / Refresh news now / Quit Mot. pystray's setup thread is non-daemon, so a failed start
  releases its queue rather than hanging the process. Started after the window so the tray never
  delays it; a tray failure is a warning, never a crash.
- **The X** (`windowctl.py`): the pywebview `closing` event is cancellable — the handler named
  `window` returns `False` to cancel. With `close_to_tray=true` (default) the close is cancelled
  and the window hides to the tray; `tray_notice_shown` makes the one-time notice fire once.
  `close_to_tray=false` lets the close through, which is the same path as the tray's Quit.
  `hide()` is never called from the closing handler (it marshals with `Invoke` and would deadlock);
  it runs on a short-lived daemon thread after the cancel.
- **Hotkey** (`hotkey.py`, RegisterHotKey/UnregisterHotKey via ctypes — no new dependency):
  a daemon thread prepares its thread id, creates a `STATIC` window on `HWND_MESSAGE`, registers,
  then pumps messages. Because the window is message-only, `set()` can be called from any thread
  (the API and the tray) and re-register in place. Taken → `WM_HOTKEY` is never received, the old
  registration stays, and `GET /api/general` reports `hotkey_active=false` with `hotkey_error`
  for the Settings line. `loop()` is guarded so a dead thread always wakes `start()`.
- **Auto-start** (`autostart.py`): HKCU `...\CurrentVersion\Run` value `Mot` =
  `"…\pythonw.exe" "C:\Mot\run.pyw" --background`. The registry is the source of truth (not
  config.json), so an entry deleted by hand is reported as off. Turning it off removes that value
  and touches nothing else; the default is off. Logging never prints a key — there is none here.
- **Quit** (`windowctl.quit()`): sets `_quitting` so the next `closing` is accepted, then destroys
  the window. `webview.start()` returning is the single shutdown point — `_shutdown()` stops the
  shortcut, hides the tray, `ingest.stop()`s the feed thread, releases the single instance, then
  stops the server. Order matters: the tray holds the UI thread, so it goes before the window.
- **Config**: `config.json` keeps `close_to_tray`, `tray_notice_shown`, `hotkey` only.

## API (localhost)
POST /api/chat (stream) · GET/POST/DELETE /api/chats · GET/POST/DELETE /api/providers ·
PUT /api/providers/active · POST /api/providers/fetch · PUT /api/settings (theme + accent) ·
PUT /api/fallback (the auto-switch order and its ticks) · POST /api/providers/wake (clear one
model's cooldown — how picking a resting model by hand still works) ·
GET /api/actions (events) · POST /api/actions/{id} (confirm/cancel an install or a WhatsApp) ·
GET/PUT /api/apps (+ POST /api/apps/rescan) · GET/POST/DELETE /api/routines ·
GET/POST/DELETE /api/contacts (Settings > Contacts) ·
GET/PUT /api/feeds + POST /api/feeds/test · PUT /api/feeds/ingest · POST /api/feeds/refresh
(Settings > Feeds: feed lists, the background refresh interval/on-off and "Refresh now") ·
GET/PUT /api/general (Settings > General: close-to-tray, the global shortcut — including
`hotkey_active` / `hotkey_error` — and the auto-start toggle) ·
POST /api/drex/check (Settings > Drex)

## Voice (Phase 8A / 8B)
Mic -> faster-whisper (local, any language) -> text -> same router. Text-to-speech optional. No router change needed.
