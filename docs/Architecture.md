# Architecture — Mot

## Stack
- Backend: Python 3.11+, FastAPI (localhost only), streaming via SSE or WebSocket
- Frontend: React + Vite + Tailwind, built to static files served by FastAPI
- Shell: pywebview (native window, no browser tab, no terminal)
- Models: litellm (one interface for all providers, including Ollama / LM Studio)
- Storage: SQLite (chats), config.json (settings), keyring (API keys)
- Search/news: ddgs (DuckDuckGo, no key) + feedparser (RSS)
- YouTube: yt-dlp (`ytsearch1:` metadata lookup for play_youtube — no API key, no download)
- Later: faster-whisper (local, multilingual voice)

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
├── run.pyw               # double-click launcher
├── backend/
│   ├── main.py           # FastAPI app + pywebview start
│   ├── api/              # chat, chats, providers, apps, routines, contacts, feeds, drex, actions
│   ├── core/llm.py       # litellm wrapper, model switching, streaming
│   ├── core/fetch.py     # GET {base}/models (+ /api/tags), presets, tags
│   ├── core/drex.py      # Drex client (stdlib urllib, injectable transport)
│   ├── core/feeds.py     # data/feeds.json + RSS fetch, cache, 48 h window
│   ├── core/router.py    # fast path: parse_parts -> (steps, segments it can't parse)
│   ├── core/llm_router.py # LLM path: tool calling or strict JSON, validated, retried once
│   ├── core/config.py    # config.json (providers) + keyring
│   ├── core/contacts.py  # data/contacts.json (Settings > Contacts), conservative matching
│   ├── core/db.py        # SQLite chats
│   └── tools/            # one file per tool + registry.py (news.py, websearch.py, …)
├── frontend/             # React app (src/, dist/)
├── data/                 # mot.db, config.json, apps.json, routines.json, contacts.json,
│                         # feeds.json (gitignored)
├── .env                  # DREX_API_KEY only — gitignored, never logged (see Drex)
└── logs/
```

## Providers and models (data/config.json)
```json
{
  "active": {"provider_id": "p-local-ollama", "model_id": "qwen2.5:7b"},
  "theme": "system",
  "providers": [
    {"id": "p-local-ollama", "name": "Local Ollama", "base_url": "http://localhost:11434",
     "key_ref": null,
     "models": [{"id": "qwen2.5:7b", "tag": "local", "tag_locked": false}]}
  ]
}
```
- One provider holds many models. `tag` is `free | paid | local | unknown`; `tag_locked`
  means the user set it by hand, so a re-fetch never overwrites it.
- API keys live in keyring under `mot-<provider id>`; this file and every API response only
  ever carry `has_key` / a `••••••••` mask. `key_ref` is the keyring *account name*, not a key.
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
- Short system prompt (< 1000 chars, built for 3B-4B local models): the tool list is passed as
  native `tools=`; the prompt names only known **sites** and saved **routine** names — the app
  list is never in a prompt, the model writes the name and `open_app` resolves it with the same
  fuzzy match/aliases the fast path uses.
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

## Research (news / "why is X moving")
`backend/core/feeds.py` owns `data/feeds.json` (`{topic: [url, …]}`): 8 s per request, feeds for
a topic fetched in parallel (ThreadPoolExecutor, max 8), 10 min cache per topic (5 min for
searches), dedupe by URL, newest first, last 48 h with a newest-first fallback when the window
is empty. `feedparser` is imported lazily inside the fetch so a run that never reads news costs
nothing.

The model's tool calls never see their own results, so research is a **second completion**:
1. Fast path first — `"<topic> news"` / `"gold news today"` runs `get_news` with NO model and
   renders a news card (headlines + Summarize button). An unresolvable topic becomes
   `web_search`; a sentence that merely ends in "news" ("good news") falls through to the model.
2. `api/chat.py` runs the normal loop, then collects `llm_router.findings_from(actions)`
   (title, source, age, URL per item; HTML stripped, 24 items max) and streams a second
   completion built by `llm_router.research_messages()` with `RESEARCH_SYSTEM` — **tools are
   never offered there**, so retrieved web text can never trigger an action.
3. `llm_router.research_footer()` appends `*As of HH:MM*` and `*Context, not trading advice.*`
   deterministically; the model never has to remember them. When a research reply exists the
   `runner.summary()` prefix is suppressed (`chat.compose()` returns the reply alone).
4. The Summarize button posts `ChatIn.findings` — fast path and router are both skipped and
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

## API (localhost)
POST /api/chat (stream) · GET/POST/DELETE /api/chats · GET/POST/DELETE /api/providers ·
PUT /api/providers/active · POST /api/providers/fetch · PUT /api/settings ·
GET /api/actions (events) · POST /api/actions/{id} (confirm/cancel an install or a WhatsApp) ·
GET/PUT /api/apps (+ POST /api/apps/rescan) · GET/POST/DELETE /api/routines ·
GET/POST/DELETE /api/contacts (Settings > Contacts) ·
GET/PUT /api/feeds + POST /api/feeds/test (Settings > Feeds) ·
POST /api/drex/check (Settings > Drex)

## Voice (later)
Mic -> faster-whisper (local, any language) -> text -> same router. Text-to-speech optional. No router change needed.
