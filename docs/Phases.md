# Phases — Mot

Prompt for each phase: "Read AGENTS.md and docs/, then build Phase N. Follow the checklist."
Tick boxes as you finish. Test before moving on.

## Phase 1 — UI, models, settings
- [x] FastAPI + React/Tailwind + pywebview shell; run.pyw launches with no terminal
- [x] Chat UI per Design.md (sidebar, input bar, streaming, markdown, dark/light)
- [x] litellm wrapper; profiles in config.json; keys in keyring
- [x] Settings modal: add/edit/delete profile, Test connection, set active; model dropdown in chat
- [x] Chats saved in SQLite
- [x] Friendly errors (Ollama down, bad key)
Done when: chat works with a local Ollama model and a cloud key; switching is instant.

## Phase 1.5 — Providers and model fetching
- [x] Replace profiles with providers: data/config.json holds providers
      [{id, name, base_url, key_ref, models[{id, tag, tag_locked}]}] + active {provider_id, model_id};
      migrate the old "Local Ollama" profile, drop the "Cloud example" placeholder
- [x] Keys stay in keyring (one per provider); API answers only ever return a masked hint
- [x] Backend fetches models: GET {base_url}/models, plus /api/tags for Ollama;
      friendly errors for 401, wrong URL, timeout, HTML/non-JSON
- [x] Tags: Ollama/LM Studio = local, OpenRouter = free/paid by pricing or ":free", else unknown;
      user can click a tag to set Free/Paid, tag_locked survives re-fetch
- [x] Settings > Models: provider cards (name, host, model count, Manage models / Edit / Delete),
      Add provider form (name, key, base URL, preset chips, Fetch models), searchable checklist
      with Select all / Select all free / Add model manually
- [x] Chat: model dropdown grouped by provider with search box + tag chips, switches mid-chat
- [x] litellm calls: openai/<model> + api_base + api_key, ollama/<model> for native Ollama
- [x] 429/quota errors show an inline "<model> hit its limit" banner with Retry and
      one-click switches to other saved models (free first)
- [x] pytest: mock servers for OpenAI /models, Ollama /api/tags, 401, timeout, HTML answer;
      preset base URLs verified
Done when: adding a provider by URL, fetching its models, tagging them and chatting all work
with no key ever written to a file. ✅ verified in the app (see Memory.md).

## Phase 2 — Tools and routines (no LLM)
- [x] Tool registry (backend/tools/registry.py) + open_url, search_in_browser, open_app,
      install_app (winget, Confirm card first), run_routine — every tool returns {ok, message, data}
- [x] App discovery: Start Menu .lnk (all users + current user) + Get-StartApps for UWP apps,
      cached in data/apps.json; fuzzy name match; aliases in Settings; UWP launches through
      `explorer.exe shell:AppsFolder\<AppID>`
- [x] Fast-path router (backend/core/router.py): "open X", "open X and search Y", "search Y on <site>",
      "go to <url>", "install X", "run <routine>"; chained with and/then; unknown input -> normal chat
- [x] Action cards: running -> done/failed, install shows Confirm/Cancel, expandable details,
      card states persisted on the message row (messages.actions)
- [x] Settings > Apps (preferred browser + aliases + Re-scan) and > Routines (name + ordered steps,
      reorder/delete); default routine "Morning setup" ships in data/routines.json
- [x] Live action events on the chat SSE stream; later updates (install progress) on GET /api/actions
- [x] pytest: router, tools, runner, install confirm, and the fast path end to end with no model
Done when: "open YouTube and search lo-fi", "open WhatsApp" and "morning setup" work with no model
at all. ✓ verified in the app (see Memory.md).

## Phase 3 — LLM router
- [x] Tool calling through litellm with the small tool set (native `tools=`; system prompt < 900
      chars, aimed at 3B-4B local models; app list never in the prompt)
- [x] Multi-step requests: several tool calls per model reply, and/then chaining kept, and mixed
      messages — fast-path segments run first, only the leftovers go to the model
- [x] Fallback when a model lacks tool calling (strict JSON prompt mode, remembered per provider)
- [x] Every call validated against the registry; one retry with the reason; then normal chat.
      Never crashes; raw tool call logged (`LLM router raw [...]`)
- [x] install_app still stops at the Confirm card — the model can't install without the user
- [x] Log which path ran: `path=fast` / `path=llm` / `path=llm->chat`
- [x] pytest: 33 new tests (LLM router, probe, parse_parts) — 96 green in total
Done when: messy commands work on a local 7B model. — Ollama isn't installed here, so it was
verified against the real opencode API instead (`space-bunny-free`): 19 of 20 phrases correct
(see Memory.md for the one fast-path limitation and the `mimo` free-tier restriction).

## Phase 3.5 — Smarter tools
- [x] One step per site: a plain "open X" is dropped when a later step opens the same host
      (search or play) — "open X and search Y" is a single results tab, in the fast path AND in
      the LLM path (drop_covered_opens, host-exact so "open gmail" is never dropped)
- [x] play_youtube(query): yt-dlp `ytsearch1:` metadata lookup (no API key, no download),
      opens the watch page; on any failure it opens the search page and says so.
      Fast rules: "play X on youtube" and "open youtube and play X" (one tab, no bare homepage).
      New dependency: yt-dlp (requirements.txt)
- [x] Settings > Contacts (name, phone number, aliases) -> data/contacts.json + /api/contacts
- [x] whatsapp_message(contact, text): whatsapp://send?phone=&text= first,
      https://wa.me/<number>?text= when Windows has no handler; always a Confirm card holding
      the contact and the text, never presses Send; an unknown contact is reported with a
      "add them in Settings > Contacts" hint and never guessed
- [x] Tool descriptions: open_app first for installed apps, open_url only for websites or when
      no app is found; bare segments must really be an app (apps.claims) before they open it
- [x] pytest: 131 green (fake launchers, fake yt-dlp, fake db), covering both Confirm paths
Done when: "open youtube and play dilbar dilbar" opens one tab with the video and
"whatsapp <name> hi" stops at a Confirm card. ✓ verified in the app (see Memory.md).

## Phase 4 — Research and news (+ Drex foundation)
- [x] Drex foundation (Option 1): backend/core/drex.py (stdlib urllib, injectable transport) +
      POST /api/drex/check + Settings > Drex button; DREX_API_KEY in gitignored .env, never logged
      or returned. Live: HTTP 200, noul=0.9349, 0.97 s
- [x] web_search(query, max_results=5) — ddgs, 5 min cache, RSS-pool fallback if ddgs is down
- [x] get_news(topic) — RSS per topic (gold, silver, crypto, markets) from data/feeds.json;
      feeds live-tested (Kitco 404 / Mining.com 403 / Yahoo stale dropped), 8 s timeout,
      parallel fetch, 10 min cache, dedupe by URL, newest first, 48 h window with a
      newest-first fallback, HTML stripped
- [x] Fast path with no model: "<topic> news", "gold news today", "crypto news" -> news card
      (headline, source, age, link that only opens on click) + Summarize button; unknown topic
      falls back to web_search; sentences that merely end in "news" still reach the model
- [x] Research path: get_news and/or web_search, then a SECOND streamed completion that turns
      the findings into 4-6 short bullets with source names + links, an "As of HH:MM" line and
      the deterministic "Context, not trading advice." footer; system prompt stays < 1000 chars
- [x] Safety: web text treated as data never instructions (system prompt + RESEARCH_SYSTEM has
      no tools), HTML stripped, snippets capped, only numbers present in the retrieved text
- [x] Settings > Feeds: per-topic feed lists, add/remove feed or topic, Test feed, Save,
      Restore defaults -> /api/feeds
- [x] Bug fix (A.1): regenerate no longer skips the fast path — the plan used to be empty, so the
      model was asked with NO tools and replaced the card with "I don't have web access".
      Re-running "Gold news today" brings the card back (live: path=fast, no new completion)
- [x] (A.2) matching tolerates case, punctuation, spacing and trailing filler — "Gold news today?",
      "gold-news!", "news about gold", "latest gold news", "market news", "forex news" all reach
      the same card; the chip texts are tested exactly as the UI sends them
- [x] (A.3) failure ladder: snapshot -> one bounded live read -> snapshot labelled offline ->
      web_search -> "Couldn't reach the news sources." + Retry. Never a plain model reply
- [x] (A.4) safety net `router.news_steps()` for a clear news request nothing else matched, plus
      the prompt line "You have live tools for that - never say you have no web access"
      (_system() = 994 chars)
- [x] (B) data/feeds.json re-curated (the only file this touches): gold / silver / crypto /
      markets / forex, 17 live-tested sources; dropped news.goldseek.com (newest item 2254 days
      old) and cryptocurrency.cv (HTTP 404); gold queries tightened to gold+price / XAU /
      gold+price+OR+XAU+bullion so "gold medal" stories stay out. No paid APIs, no keys
- [x] (C) 2-hour refresh: core/snapshot.py (data/market_ingest/latest.json, 3 h stale) +
      core/ingest.py (plain thread from main(): startup pass, then interval; no APScheduler);
      Settings > Feeds gains the interval (default 2 h), an on/off toggle, "Refresh now" and
      last_ingest_at; every run fetches all topics in parallel, dedupes, keeps the 48 h window,
      writes headlines + links only, logs per-source status, and never dies with one dead feed;
      the card footer shows "Updated HH:MM" + the failed-source count
- [x] (D) editable data/news_phrases.json + core/phrases.py: "aj update", "aaj news", "aj gold",
      "aj crypto", "market update today", "gold aur bitcoin", "aj market kya hua" -> the same
      news card with no model; a bare "aj" never fires; an ambiguous topic -> ONE mixed card
      (gold + crypto + markets, newest first, max 12)
- [x] pytest: 193 -> 238 green (job, snapshot/stale/offline, case + phrase variants, regenerate,
      prompt length; an autouse fixture points the snapshot/phrase/settings paths at tmp_path and
      neuters the web-search fallback, so no test touches a real network)
Done when: "crypto news today" and "why is gold moving today" return a short sourced summary.
✓ verified live on a running server (see Memory.md): instant card with no model call, 4 sourced
bullets + footer, Summarize button, Drex check. Explanations are context, not advice.
✓ verified through the Desktop shortcut (see Memory.md): startup refresh 5 topics / 17 sources /
0 failed; "Gold news today" -> instant card + Regenerate -> the same card with the completion
count unchanged; "aj gold aur bitcoin pe kya update hai" -> one 12-item mixed card;
"why is gold moving today" -> 4 sourced bullets + footer; Refresh now moved Last updated to
03:07 PM.

## Phase 5 — Polish and auto-start

### 5A — Window behaviour (done)
- [x] One Mot at a time — a second launch wakes the running window (from the tray or minimised)
      to the front and exits silently; `--background` never pops a window
- [x] Tray icon — Open Mot / Refresh news now / Quit Mot; left-click opens the window
- [x] Settings > General — "When I close the window: minimize to tray (default) / quit", with a
      one-time first-use notice; Quit Mot leaves zero pythonw processes
- [x] Global hotkey Ctrl+Alt+M shows/hides from anywhere, changeable in Settings > General;
      an in-use combo is refused politely and the old one stays
- [x] Start with Windows toggle (default OFF) — HKCU Run key, pythonw + run.pyw + `--background`
- [x] Startup stays light: lazy imports, window on screen in 3.1 s (measured)
- [x] 23 tests with fakes for the registry / tray / hotkey (no test touches real Windows
      settings); 261 green. Verified live through the Desktop shortcut.

### 5B-1 — Foundations (current)
- [x] Single data root: user data lives in `%APPDATA%\Mot`, program files come from
      `paths.program_root()`, `MOT_DATA_DIR` points tests at a temp folder
- [x] First-run migration out of the legacy `C:\Mot\data` — copies only what is missing,
      writes a backup next to the source, reports `failed: []`
- [x] Migration never overwrites; a destination that already has data is called out loud in
      the log with the source and backup paths
- [x] Friendly errors: backend `errors.py` codes, frontend `report.js` / `ErrorBoundary` /
      `api.js` show a sentence instead of a traceback
- [x] Rotating `logs/mot.log` + a crash log, and `api/log.py` so the browser can report too
- [x] Splash on screen early (538 ms warm, 1385 ms first run), WebView2 detected with a
      friendly failure instead of a silent one
- [x] `db.close()` last in shutdown; the log ends `Mot is closing down` -> `Mot has stopped`
- [x] `tests/test_paths.py` (28 tests) including the migration "already has data" regression;
      suite 289 green
- [x] Verified live through the Desktop shortcut with the migrated data: chat list, news card,
      WhatsApp Confirm card then **Cancel** ("Cancelled — nothing was sent"), hotkey Ctrl+Alt+M
      show *and* hide, close-to-tray keeps the process alive, graceful quit leaves zero
      pythonw and no crash.log
- [ ] docs/Architecture.md documents the new paths and the new data location
- [ ] Done when: a first run moves old data safely, every failure shows a friendly sentence,
      and Quit leaves nothing running

## Execution order

`5B-1 -> 6 -> 7 -> 8A -> 8B -> 9 -> 10A -> 10B -> 11 -> 12`

Numbers are new; the old number is in brackets. Stop at the end of a phase and wait for the
user's explicit go-ahead before starting the next one.

## Phase 6 — Reliability
- [x] Ordered fallback list in Settings > Models — reorder the list the router should try
      (↑/↓ buttons instead of drag: works without a pointer and needs no drag library)
- [x] On 429 / timeout / 5xx / 404 the router moves to the next model and cools the failed one
      down (~5 min for quota, ~30 min for 5xx and timeouts, ~6 h for 404)
- [x] Every LLM call has a timeout of at least 10 s
- [x] A small notice in the chat when the model switched, and why
- [x] Manual switching still works, and the existing limit banner still works
- [x] The capabilities line inside the ~1000-char prompt is generated at runtime from the
      current model — never hard-coded
- [x] Logs are UTF-8, tested with Urdu and roman-Urdu plus emoji
- [x] A model can never confirm its own install or WhatsApp card — Confirm only ever comes
      from the UI
- [x] Accent picker in Settings > Appearance that changes `--accent`
- Done when: the first model in the list is forced to fail, the next one answers, and the
  failed one stays skipped for its cooldown.
  **Verified live through the Desktop shortcut** (temp data dir, mock provider): `fail-429`
  returned 429 → `cooldown fail-429 for 300s (rate_limit)` → notice
  "fail-429 hit its limit, switched to ok-model" → `ok-model` answered; the next request logged
  `model fail-429 is resting -> skipped this request` and `route chose ok-model after 0 failed
  attempt(s)`; the model picker showed `resting 0:35` counting down.

## Phase 7 — Memory
- [ ] `facts(key, value, category, updated_at)` plus FTS5 over past messages
- [ ] Prompt core (~1000 chars of identity and recent facts) plus a key index
- [ ] `recall_memory(query)` tool
- [ ] Save facts only from the user's own messages, with a "Saved: …" chip and Undo
- [ ] Never save passwords, API keys or card numbers
- [ ] Settings > Memory: list with date, edit, delete one, delete all, and "forget X" in chat
- [ ] Optional end-of-chat summary plus a rolling summary for long chats
- [ ] Stays local — document where it lives
- Done when: a fact saved in one chat is recalled in a new chat, and deleting it makes Mot
  forget it.

## Phase 8A — Hear [old 6]
- [ ] Push-to-talk, default Ctrl+Space, changeable
- [ ] STT providers in Settings > Voice: local faster-whisper (tiny/base/small, int8, CPU)
      with the real measured speed, or an OpenAI-compatible endpoint with the key in keyring
- [ ] Language auto-detect plus a manual choice
- [ ] Mic picker by device name with a live level meter
- [ ] Orb states: idle / listening / thinking
- Done when: speaking in the user's language fills the input box and the fast path runs it.

## Phase 8B — Speak [old 6]
- [ ] TTS providers: Windows voices, Piper offline if a voice exists, Edge-TTS — each tested
      live for the user's language, and failures dropped
- [ ] Echo guard: the mic closes while Mot is speaking
- [ ] Stop button plus a "stop" voice command
- [ ] Short spoken acknowledgement for slow tasks
- [ ] Speaker picker by name; orb "speaking"
- [ ] Wake word optional/later, local only (openWakeWord), off by default
- Done when: Mot speaks the user's language back and "stop" ends it.

## Phase 9 — Packaging [old 5B-2]
- [ ] One PyInstaller (or similar) build into `build/`, never shipped from the source tree
- [ ] The build script must be re-runnable — a second run works without hand-cleaning
- [ ] Report size, startup time and every blocker found
- [ ] Desktop shortcut + `pythonw.exe run.pyw` still work from the built app
- Done when: a build runs twice in a row from scratch and the report is written up.

## Phase 10A — Smart news ranking [old 8]
- [ ] Keep the existing Drex spec: score and order headlines so the useful ones come first
- [ ] Ranking is deterministic — no model call on the hot path
- [ ] Explainable: a headline can say why it ranked where it did
- Done when: the same snapshot always ranks the same way, and the top of the list is the part
  the user would have scrolled to.

## Phase 10B — Alerts and briefing [old 8]
- [ ] One Windows toast helper used everywhere
- [ ] Toast on a high-importance headline as it lands
- [ ] Keyword watchlist the user edits in Settings
- [ ] Morning briefing card built from the news snapshot (no extra fetching)
- [ ] Timers and reminders ("remind me in 20 minutes") on the same helper
- Done when: a matching headline raises a toast and "remind me in 20 minutes" comes back in
  20 minutes.

## Phase 11 — Research providers (TinyFish, Firecrawl) [old 9]
- [ ] Provider tools behind the same tool interface as `web_search`
- [ ] Keys in keyring only; a provider the user has no key for is simply not offered
- [ ] Falls back to what Phase 4 already does when a provider is missing or fails
- [ ] No new hard dependency on any one provider
- Done when: research runs the same shape of answer with a provider configured, and without one.

## Phase 12 — Screen control [old 7]
- [ ] browser-use (MIT) as a pip dependency, run in a separate helper process with its own
      venv, talking to Mot over localhost. Never copy its source into Mot; keep its licence
      notice.
- [ ] Spike first: 3 saved models x 5 simple tasks, reporting success rate / steps / tokens /
      time. A local 3B model is expected to fail — that result is part of the report.
- [ ] Map Mot's provider profiles onto its wrappers; no provider-specific code in Mot
- [ ] Dedicated Mot browser profile by default; real Chrome/Brave only on opt-in, with a warning
- [ ] The Confirm card is issued by the UI, never by the model, before submit / send / post /
      purchase / login. Domain deny-list covering trading, brokerage and exchange sites, plus
      an optional allow-list. Page content is untrusted and no credentials ever go in prompts.
- [ ] Max steps / minutes / token-cost caps in Settings > Browser agent, a live step log card
      with Stop, and everything written to `logs/`
- [ ] Entry only via an explicit `browse: …` message — never automatic, and the fast path is
      tried first
- [ ] Feature flag off by default; the helper is removable without touching the rest of Mot
- Done when: the spike report exists, a browse task completes under its caps with a working
  Confirm/Stop, and turning the flag off leaves no trace in the UI.

## Version 2.0 — parked ideas

Not scheduled. Listed so they are not lost.
- Clipboard assistant: copy text → translate / summarise / explain / fix
- Drop-in plugins
- Undo, once file tools exist
- Optional Playwright browser automation
- Phone remote
- Anything else we park along the way
