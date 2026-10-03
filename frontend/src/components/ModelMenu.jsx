import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Gear, Search } from './icons.jsx';
import TagChip from './TagChip.jsx';

function clock(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

// Model picker: grouped by provider, searchable, tag chips on every model.
// Models on cooldown show a "resting" chip with the time left (Phase 6).
export default function ModelMenu({ providers, active, resting = [], onPick, onOpenSettings }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const rootRef = useRef(null);
  const inputRef = useRef(null);

  const current = useMemo(() => {
    const provider = providers.find((p) => p.id === active?.provider_id);
    const model = provider?.models.find((m) => m.id === active?.model_id);
    return provider && model ? { provider, model } : null;
  }, [providers, active]);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return providers
      .map((provider) => ({
        provider,
        models: needle
          ? provider.models.filter((m) => m.id.toLowerCase().includes(needle))
          : provider.models,
      }))
      .filter((group) => group.models.length > 0);
  }, [providers, query]);

  const total = providers.reduce((count, p) => count + p.models.length, 0);

  // When each resting model becomes usable again — the clock starts on arrival.
  const restingUntil = useMemo(() => {
    const map = new Map();
    (resting || []).forEach((entry) => {
      map.set(
        `${entry.provider_id}|${entry.model_id}`,
        Date.now() + Math.max(0, entry.seconds || 0) * 1000
      );
    });
    return map;
  }, [resting]);

  const restLeft = (providerId, modelId) => {
    const until = restingUntil.get(`${providerId}|${modelId}`);
    if (!until) return null;
    const left = Math.ceil((until - now) / 1000);
    return left > 0 ? left : null;
  };

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Tick only while the list is open: the countdown costs nothing when closed.
  useEffect(() => {
    if (!open || restingUntil.size === 0) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [open, restingUntil]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey, true);
    };
  }, [open]);

  const pick = (providerId, modelId) => {
    onPick({ provider_id: providerId, model_id: modelId });
    setOpen(false);
    setQuery('');
  };

  return (
    <div ref={rootRef} className="relative flex min-w-0 items-center">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-label="Choose model"
        aria-expanded={open}
        className="flex max-w-[240px] items-center gap-1.5 rounded-lg border border-line bg-surface2 py-1.5 pl-2.5 pr-2 text-xs font-medium text-ink outline-none hover:border-accent/60"
      >
        <span className="truncate">{current ? current.model.id : 'No models'}</span>
        {current && <TagChip tag={current.model.tag} />}
        <ChevronDown size={14} />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-2 flex w-[320px] flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-2xl">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <Search size={14} className="shrink-0 text-inksoft" />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search models…"
              className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-inksoft"
            />
          </div>

          <div className="max-h-[280px] overflow-y-auto p-1.5">
            {total === 0 && (
              <p className="px-3 py-6 text-center text-sm text-inksoft">
                No models yet.
              </p>
            )}
            {groups.map(({ provider, models }) => (
              <div key={provider.id} className="mb-1.5">
                <div className="flex items-baseline justify-between px-2 py-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-inksoft">
                    {provider.name}
                  </span>
                  <span className="truncate pl-2 text-[10px] text-inksoft/70">
                    {provider.base_url || 'default host'}
                  </span>
                </div>
                {models.map((model) => {
                  const isActive =
                    active?.provider_id === provider.id && active?.model_id === model.id;
                  return (
                    <button
                      key={model.id}
                      onClick={() => pick(provider.id, model.id)}
                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-surface2 ${
                        isActive ? 'bg-accent/10 text-ink' : 'text-ink'
                      }`}
                    >
                      <span className="min-w-0 flex-1 truncate">{model.id}</span>
                      {restLeft(provider.id, model.id) !== null && (
                        <span
                          className="shrink-0 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400"
                          title="Resting after an error — skipped for now"
                        >
                          resting {clock(restLeft(provider.id, model.id))}
                        </span>
                      )}
                      <TagChip tag={model.tag} />
                    </button>
                  );
                })}
              </div>
            ))}
            {groups.length === 0 && total > 0 && (
              <p className="px-3 py-4 text-center text-sm text-inksoft">
                Nothing matches “{query}”.
              </p>
            )}
          </div>

          <button
            onClick={() => {
              setOpen(false);
              onOpenSettings();
            }}
            className="flex items-center gap-2 border-t border-line px-3 py-2.5 text-xs text-inksoft hover:bg-surface2 hover:text-ink"
          >
            <Gear size={14} />
            Manage models…
          </button>
        </div>
      )}
    </div>
  );
}
