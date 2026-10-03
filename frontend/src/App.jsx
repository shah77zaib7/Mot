import { useCallback, useEffect, useRef, useState } from 'react';
import Sidebar, { SidebarToggle } from './components/Sidebar.jsx';
import EmptyState from './components/EmptyState.jsx';
import Message from './components/Message.jsx';
import InputBar from './components/InputBar.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import { Gear, Moon, Sun } from './components/icons.jsx';
import { api, streamChat, watchActions } from './api.js';
import { applyAccent, applyTheme, watchSystemTheme } from './theme.js';
import TagChip from './components/TagChip.jsx';

const TAG_RANK = { free: 0, local: 1, paid: 2, unknown: 3 };

// Other saved models, free ones first — offered when a model hits its limit.
function otherModels(current) {
  const list = [];
  for (const provider of current.providers || []) {
    for (const model of provider.models) {
      const isActive =
        provider.id === current.active?.provider_id &&
        model.id === current.active?.model_id;
      if (!isActive) {
        list.push({ provider_id: provider.id, model_id: model.id, tag: model.tag });
      }
    }
  }
  list.sort((a, b) => (TAG_RANK[a.tag] ?? 9) - (TAG_RANK[b.tag] ?? 9));
  return list.slice(0, 6);
}

export default function App() {
  const [settings, setSettings] = useState({
    providers: [],
    active: null,
    theme: 'system',
    accent: null,
    fallback: [],
    resting: [],
    presets: [],
  });
  const [chats, setChats] = useState([]);
  const [chatId, setChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [streamText, setStreamText] = useState('');
  const [streamActions, setStreamActions] = useState([]); // live action cards
  const [notices, setNotices] = useState([]); // "X hit its limit, switched to Y"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null); // {message, fix}
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [isDark, setIsDark] = useState(false);

  const chatIdRef = useRef(null);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  const updateChatId = useCallback((id) => {
    chatIdRef.current = id;
    setChatId(id);
  }, []);

  // --- initial load -------------------------------------------------------
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await api('/api/providers');
        if (alive) setSettings(data);
      } catch (err) {
        if (alive) setError({ message: err.message });
      }
      try {
        const data = await api('/api/chats');
        if (alive) setChats(data.chats);
      } catch {
        /* sidebar stays empty */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // --- theme --------------------------------------------------------------
  useEffect(() => {
    applyTheme(settings.theme);
    setIsDark(document.documentElement.classList.contains('dark'));
    return watchSystemTheme(settings.theme);
  }, [settings.theme]);

  useEffect(() => {
    applyAccent(settings.accent); // Settings > Appearance (Phase 6)
  }, [settings.accent]);

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setIsDark(document.documentElement.classList.contains('dark'))
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observer.disconnect();
  }, []);

  // --- live action updates (install progress after the reply finished) ----
  useEffect(() => {
    const stopWatcher = watchActions((action) => {
      setMessages((prev) =>
        prev.map((message) => {
          if (!message.actions?.some((item) => item.id === action.id)) return message;
          return {
            ...message,
            actions: message.actions.map((item) =>
              item.id === action.id ? { ...item, ...action } : item
            ),
          };
        })
      );
    });
    return stopWatcher;
  }, []);

  const confirmAction = useCallback(async (actionId, confirm) => {
    try {
      await api(`/api/actions/${actionId}`, { method: 'POST', body: { confirm } });
    } catch (err) {
      setError({ message: err.message });
    }
  }, []);

  // --- scroll follow ------------------------------------------------------
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance < 260) el.scrollTop = el.scrollHeight;
  }, [messages, streamText, streamActions]);

  const refreshChats = useCallback(async () => {
    try {
      const data = await api('/api/chats');
      setChats(data.chats);
    } catch {
      /* ignore */
    }
  }, []);

  const loadChat = useCallback(
    async (id) => {
      const data = await api(`/api/chats/${id}`);
      updateChatId(id);
      setMessages(data.messages);
      setStreamText('');
      setError(null);
      setNotices([]);
    },
    [updateChatId]
  );

  // --- chat actions -------------------------------------------------------
  const stop = useCallback(() => {
    const id = chatIdRef.current;
    if (id) {
      // Loopback sockets drop silently — tell the server explicitly.
      api('/api/chat/stop', { method: 'POST', body: { chat_id: id } }).catch(() => {});
    }
    abortRef.current?.abort();
  }, []);

  const newChat = useCallback(() => {
    stop();
    updateChatId(null);
    setMessages([]);
    setStreamText('');
    setStreamActions([]);
    setNotices([]);
    setError(null);
    setInput('');
  }, [stop, updateChatId]);

  const selectChat = useCallback(
    async (id) => {
      stop();
      if (id === chatIdRef.current) return;
      try {
        await loadChat(id);
      } catch (err) {
        setError({ message: err.message });
      }
    },
    [loadChat, stop]
  );

  const deleteChat = useCallback(
    async (id) => {
      try {
        await api(`/api/chats/${id}`, { method: 'DELETE' });
        if (id === chatIdRef.current) newChat();
        await refreshChats();
      } catch (err) {
        setError({ message: err.message });
      }
    },
    [newChat, refreshChats]
  );

  const send = useCallback(
    async (rawText, { regenerate = false, findings = null } = {}) => {
      const text = (rawText ?? input).trim();
      if (busy) return;
      if (!regenerate && !text) return;

      setError(null);
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;

      if (regenerate) {
        setMessages((prev) => {
          const next = [...prev];
          while (next.length && next[next.length - 1].role === 'assistant') next.pop();
          return next;
        });
      } else {
        setMessages((prev) => [
          ...prev,
          { id: `local-${Date.now()}`, role: 'user', content: text, findings },
        ]);
        setInput('');
      }

      let cid = chatIdRef.current;
      let acc = '';
      let acts = []; // action cards for this reply (fast path has no deltas)

      try {
        const payload = {
          message: text,
          chat_id: cid,
          provider_id: settings.active?.provider_id,
          model_id: settings.active?.model_id,
          regenerate,
          findings,
        };
        for await (const event of streamChat(payload, controller.signal)) {
          if (event.type === 'start') {
            if (event.chat_id !== cid) {
              cid = event.chat_id;
              updateChatId(cid);
            }
            refreshChats(); // new chat + title show up immediately
          } else if (event.type === 'delta') {
            acc += event.text;
            setStreamText(acc);
          } else if (event.type === 'action') {
            const incoming = event.action;
            const at = acts.findIndex((item) => item.id === incoming.id);
            if (at >= 0) acts = acts.map((item, i) => (i === at ? { ...item, ...incoming } : item));
            else acts = [...acts, incoming];
            setStreamActions([...acts]);
          } else if (event.type === 'done') {
            const doneActions = event.actions || acts;
            setMessages((prev) => [
              ...prev,
              {
                id: event.message_id,
                role: 'assistant',
                content: event.text ?? acc, // fast path has no deltas
                profile: event.profile,
                actions: doneActions,
              },
            ]);
            setStreamText('');
            setStreamActions([]);
            await refreshChats();
          } else if (event.type === 'switch') {
            // The router moved to another model: say so, and refresh the
            // "resting" markers now that a cooldown has started.
            setNotices((prev) => [...prev, event.text]);
            api('/api/providers').then(setSettings).catch(() => {});
          } else if (event.type === 'error') {
            setStreamText('');
            setError({
              message: event.message,
              fix: event.fix,
              code: event.code,
              model: event.model,
              models: event.models,
            });
            if (!acc && !regenerate) setInput(text); // nothing replied — easy retry
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          // Stop was pressed: keep the partial reply the server saved.
          setStreamText('');
          setStreamActions([]);
          if (cid) {
            await new Promise((resolve) => setTimeout(resolve, 250));
            if (chatIdRef.current === cid) {
              try {
                await loadChat(cid);
              } catch {
                /* ignore */
              }
            }
            await refreshChats();
          }
        } else {
          setStreamText('');
          setStreamActions([]);
          // A message about a missing model/provider should offer Settings.
          const fix = /model|provider|settings/i.test(err.message) ? 'settings' : undefined;
          setError({ message: err.message, fix });
          if (!acc && !regenerate && !input.trim()) setInput(text);
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [input, busy, loadChat, refreshChats, settings, updateChatId]
  );

  const regenerate = useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) send(lastUser.content, { regenerate: true, findings: lastUser.findings });
  }, [messages, send]);

  // Summarize button on a news card: send those exact headlines to the model.
  const summarize = useCallback(
    (items, topic) => send(`Summarize these ${topic || 'news'} headlines`, { findings: items }),
    [send]
  );

  const retry = useCallback(() => {
    setError(null);
    if (input.trim()) send();
    else regenerate();
  }, [input, regenerate, send]);

  const changeModel = useCallback((selection) => {
    // Switch instantly, then persist in the background. Picking a resting
    // model by hand wakes it up: the cooldown only filters automatic moves.
    setSettings((prev) => ({ ...prev, active: selection }));
    api('/api/providers/wake', { method: 'POST', body: selection }).catch(() => {});
    api('/api/providers/active', { method: 'PUT', body: selection }).catch((err) =>
      setError({ message: err.message })
    );
  }, []);

  const toggleTheme = useCallback(() => {
    const next = isDark ? 'light' : 'dark';
    api('/api/settings', { method: 'PUT', body: { theme: next } })
      .then(() => setSettings((prev) => ({ ...prev, theme: next })))
      .catch((err) => setError({ message: err.message }));
  }, [isDark]);

  // --- keyboard shortcuts -------------------------------------------------
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        if (settingsOpen) setSettingsOpen(false);
        else if (busy) stop();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        newChat();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [busy, newChat, settingsOpen, stop]);

  // --- derived ------------------------------------------------------------
  const activeChat = chats.find((chat) => chat.id === chatId);
  const limitAlternates = error?.code === 'rate_limit' ? otherModels(settings) : [];
  const streamMessage =
    streamText || streamActions.length
      ? { id: 'streaming', role: 'assistant', content: streamText, actions: streamActions }
      : null;
  const visible = streamMessage ? [...messages, streamMessage] : messages;

  return (
    <div className="flex h-full overflow-hidden bg-canvas text-ink">
      <Sidebar
        open={sidebarOpen}
        chats={chats}
        activeId={chatId}
        onSelect={selectChat}
        onNew={newChat}
        onDelete={deleteChat}
        onSettings={() => setSettingsOpen(true)}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-line px-3 py-2.5">
          {!sidebarOpen && <SidebarToggle onClick={() => setSidebarOpen(true)} />}
          <span className="truncate text-sm font-medium text-ink">
            {activeChat?.title || 'New chat'}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
            >
              {isDark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              aria-label="Open settings"
              className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
            >
              <Gear size={17} />
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          {messages.length === 0 && !streamText && !streamActions.length ? (
            <EmptyState onPick={(text) => setInput(text)} />
          ) : (
            <div className="mx-auto w-full max-w-[760px] space-y-1 px-4 py-6">
              {visible.map((message, index) => (
                <Message
                  key={message.id}
                  message={message}
                  streaming={message.id === 'streaming'}
                  canRegenerate={
                    !busy &&
                    message.role === 'assistant' &&
                    index === visible.length - 1
                  }
                  onRegenerate={regenerate}
                  onAction={confirmAction}
                  onSummarize={summarize}
                />
              ))}
              {notices.map((text, index) => (
                <p
                  key={`switch-${index}`}
                  className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300"
                >
                  {text}
                </p>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="mx-auto w-full max-w-[760px] px-4 pb-1">
            {error.code === 'rate_limit' || error.code === 'fallback_exhausted' ? (
              <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1 leading-relaxed">
                    <p className="font-semibold text-amber-600 dark:text-amber-400">
                      {error.code === 'fallback_exhausted'
                        ? 'No model answered'
                        : `${error.model || 'This model'} hit its limit`}
                    </p>
                    <p className="mt-0.5 text-inksoft">{error.message}</p>
                    {error.models?.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {error.models.map((item) => (
                          <li
                            key={item.label}
                            className="flex items-baseline gap-1.5 text-[12px] text-inksoft"
                          >
                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500/70" />
                            <span className="text-ink">{item.label}</span>
                            <span>— {item.why}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <button
                    onClick={retry}
                    disabled={busy}
                    className="shrink-0 rounded-lg bg-amber-500/20 px-2.5 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-500/30 dark:text-amber-300 disabled:opacity-50"
                  >
                    Retry
                  </button>
                  <button
                    onClick={() => setError(null)}
                    aria-label="Dismiss"
                    className="shrink-0 rounded-lg px-1.5 py-1 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
                  >
                    ✕
                  </button>
                </div>
                {limitAlternates.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] text-inksoft">Switch to:</span>
                    {limitAlternates.map((option) => (
                      <button
                        key={`${option.provider_id}:${option.model_id}`}
                        onClick={() => changeModel(option)}
                        className="flex max-w-[220px] items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-1 text-[11px] text-ink hover:border-accent/60"
                      >
                        <span className="truncate">{option.model_id}</span>
                        <TagChip tag={option.tag} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
                <span className="min-w-0 flex-1 leading-relaxed">{error.message}</span>
                {error.fix === 'settings' && (
                  <button
                    onClick={() => setSettingsOpen(true)}
                    className="shrink-0 rounded-lg bg-red-500/15 px-2.5 py-1.5 text-xs font-medium hover:bg-red-500/25"
                  >
                    Open Settings
                  </button>
                )}
                <button
                  onClick={() => setError(null)}
                  aria-label="Dismiss"
                  className="shrink-0 rounded-lg px-1.5 py-1 hover:bg-red-500/15"
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        )}

        <InputBar
          value={input}
          onChange={setInput}
          onSend={() => send()}
          onStop={stop}
          busy={busy}
          providers={settings.providers}
          active={settings.active}
          resting={settings.resting}
          onModelChange={changeModel}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      </main>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onChanged={(data) => setSettings(data)}
      />
    </div>
  );
}
