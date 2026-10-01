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
- [x] pytest: 193 green (mocked RSS + ddgs + fake Drex transport, no real network)
Done when: "crypto news today" and "why is gold moving today" return a short sourced summary.
✓ verified live on a running server (see Memory.md): instant card with no model call, 4 sourced
bullets + footer, Summarize button, Drex check. Explanations are context, not advice.

## Phase 5 — Polish and auto-start
- [ ] Optional auto-start with Windows (toggle in Settings)
- [ ] Tray icon and hotkey to open Mot
- [ ] Packaging (PyInstaller or similar)
- [ ] Error-handling pass

## Phase 6 — Voice (user's language)
- [ ] Mic button -> faster-whisper local, language selectable or auto
- [ ] Voice goes through the same router
- [ ] Optional text-to-speech

## Phase 7 — Screen control (optional)
- [ ] Screenshot-based control only as a fallback for things tools can't do
- [ ] Always confirm before acting; big Stop button
