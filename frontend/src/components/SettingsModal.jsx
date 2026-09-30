import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Check, Eye, EyeOff, Pencil, Plus, Refresh, Search, Trash, X } from './icons.jsx';
import TagChip from './TagChip.jsx';
import AppsPanel from './AppsPanel.jsx';
import ContactsPanel from './ContactsPanel.jsx';
import RoutinesPanel from './RoutinesPanel.jsx';

const EMPTY_FORM = {
  id: null,
  name: '',
  base_url: '',
  api_key: '',
  showKey: false,
  nameTouched: false,
};

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-inksoft">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-inksoft">{hint}</span>}
    </label>
  );
}

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

function hostnameOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

export default function SettingsModal({ open, onClose, settings, onChanged }) {
  const [tab, setTab] = useState('models');
  const [view, setView] = useState('list'); // 'list' | 'form'
  const [form, setForm] = useState(null);
  const [step, setStep] = useState('details'); // 'details' | 'models'
  const [rows, setRows] = useState([]); // {id, tag, tag_locked, on, manual}
  const [search, setSearch] = useState('');
  const [manual, setManual] = useState('');
  const [fetching, setFetching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // {kind: 'error' | 'info', text}
  const [confirmId, setConfirmId] = useState(null);

  useEffect(() => {
    if (!open) {
      setTab('models');
      setView('list');
      setForm(null);
      setStep('details');
      setRows([]);
      setSearch('');
      setManual('');
      setNote(null);
      setConfirmId(null);
    }
  }, [open]);

  if (!open) return null;

  const presets = settings.presets || [];
  const providers = settings.providers || [];
  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const refresh = async () => {
    const data = await api('/api/providers');
    onChanged(data);
    return data;
  };

  const run = async (fn) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
    } catch (err) {
      setNote({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  // --- open the form -------------------------------------------------------
  const openAdd = () => {
    setForm({ ...EMPTY_FORM });
    setRows([]);
    setStep('details');
    setNote(null);
    setView('form');
  };

  const openProvider = (provider, startStep) => {
    setForm({
      id: provider.id,
      name: provider.name,
      base_url: provider.base_url || '',
      api_key: '',
      showKey: false,
      nameTouched: true,
    });
    setRows(provider.models.map((m) => ({ ...m, on: true })));
    setStep(startStep);
    setNote(null);
    setSearch('');
    setView('form');
    if (startStep === 'models') doFetch(provider.base_url, '', provider.models);
  };

  const closeForm = () => {
    setView('list');
    setForm(null);
    setRows([]);
    setNote(null);
    setFetching(false);
  };

  // --- name auto-fill ------------------------------------------------------
  const onBaseUrl = (value) => {
    setForm((prev) => {
      const next = { ...prev, base_url: value };
      if (!prev.nameTouched) {
        const host = hostnameOf(value);
        if (host || prev.name === '') next.name = host || prev.name;
      }
      return next;
    });
  };

  const applyPreset = (preset) => {
    setForm((prev) => ({
      ...prev,
      base_url: preset.base_url || prev.base_url,
      name: !prev.nameTouched && preset.name ? preset.name : prev.name,
      nameTouched: preset.name ? false : prev.nameTouched,
    }));
    setNote(null);
  };

  // --- fetch models --------------------------------------------------------
  const mergeRows = (previous, fetched) => {
    const ids = new Set(fetched.map((m) => m.id));
    const keptManual = previous.filter((row) => row.manual && !ids.has(row.id));
    const merged = fetched.map((model) => {
      const prev = previous.find((row) => row.id === model.id);
      if (!prev) return { ...model, tag_locked: false, on: false };
      return {
        id: model.id,
        tag: prev.tag_locked ? prev.tag : model.tag,
        tag_locked: prev.tag_locked,
        on: prev.on,
        manual: prev.manual,
      };
    });
    return [...merged, ...keptManual];
  };

  const doFetch = async (baseUrl, apiKey, seedRows) => {
    const url = (baseUrl ?? form.base_url).trim();
    if (!url) {
      setNote({ kind: 'error', text: 'Enter a base URL first.' });
      return;
    }
    setFetching(true);
    setNote(null);
    try {
      const data = await api('/api/providers/fetch', {
        method: 'POST',
        body: { base_url: url, api_key: (apiKey ?? form.api_key) || null },
      });
      if (!data.ok) {
        if (data.code === 'not_found' || data.code === 'empty') {
          // No /models endpoint: let the user type the models in by hand.
          setRows((prev) => (seedRows ? seedRows.map((m) => ({ ...m, on: true })) : prev));
          setStep('models');
          setNote({ kind: 'info', text: `${data.message} Add the models by hand below.` });
        } else {
          setNote({ kind: 'error', text: data.message });
        }
        return;
      }
      setRows((prev) => mergeRows(seedRows ? seedRows.map((m) => ({ ...m, on: true })) : prev, data.models));
      setStep('models');
    } catch (err) {
      setNote({ kind: 'error', text: err.message });
    } finally {
      setFetching(false);
    }
  };

  // --- checklist actions ---------------------------------------------------
  const toggleRow = (id) =>
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, on: !row.on } : row)));

  const cycleTag = (id) =>
    setRows((prev) =>
      prev.map((row) =>
        row.id === id
          ? { ...row, tag: row.tag === 'free' ? 'paid' : 'free', tag_locked: true }
          : row
      )
    );

  const selectAll = (onlyFree) =>
    setRows((prev) =>
      prev.map((row) => ({ ...row, on: onlyFree ? row.tag === 'free' : true }))
    );

  const addManual = () => {
    const id = manual.trim();
    if (!id) return;
    setRows((prev) => {
      const existing = prev.find((row) => row.id === id);
      if (existing) return prev.map((row) => (row.id === id ? { ...row, on: true } : row));
      return [...prev, { id, tag: 'unknown', tag_locked: false, on: true, manual: true }];
    });
    setManual('');
  };

  const saveForm = () =>
    run(async () => {
      const selected = rows.filter((row) => row.on);
      if (selected.length === 0) {
        setNote({
          kind: 'error',
          text: 'Select at least one model — or add one with “Add model manually”.',
        });
        return;
      }
      await api('/api/providers', {
        method: 'POST',
        body: {
          id: form.id,
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          api_key: form.api_key || null,
          models: selected.map(({ id, tag, tag_locked }) => ({ id, tag, tag_locked })),
        },
      });
      await refresh();
      closeForm();
    });

  const removeProvider = (pid) =>
    run(async () => {
      await api(`/api/providers?pid=${encodeURIComponent(pid)}`, { method: 'DELETE' });
      await refresh();
      setConfirmId(null);
    });

  const setTheme = (theme) =>
    run(async () => {
      await api('/api/settings', { method: 'PUT', body: { theme } });
      await refresh();
    });

  const visibleRows = search.trim()
    ? rows.filter((row) => row.id.toLowerCase().includes(search.trim().toLowerCase()))
    : rows;
  const selectedCount = rows.filter((row) => row.on).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[86vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">Settings</h2>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex gap-1 border-b border-line px-4 pt-2">
          {[
            ['models', 'Models'],
            ['apps', 'Apps'],
            ['routines', 'Routines'],
            ['contacts', 'Contacts'],
            ['appearance', 'Appearance'],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => {
                setTab(key);
                if (key === 'models' && view === 'form') closeForm();
              }}
              className={`-mb-px border-b-2 px-3 py-2.5 text-sm transition-colors ${
                tab === key
                  ? 'border-accent font-medium text-ink'
                  : 'border-transparent text-inksoft hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {note && (
            <p
              className={`mb-3 rounded-lg px-3 py-2 text-sm ${
                note.kind === 'error'
                  ? 'bg-red-500/12 text-red-500'
                  : 'bg-surface2 text-inksoft'
              }`}
            >
              {note.text}
            </p>
          )}

          {tab === 'models' &&
            (view === 'form' ? (
              /* ---- add / edit provider ---- */
              <div className="space-y-4">
                <Field label="Provider name">
                  <input
                    className={inputClass}
                    value={form.name}
                    onChange={(event) => {
                      setForm((prev) => ({
                        ...prev,
                        name: event.target.value,
                        nameTouched: true,
                      }));
                    }}
                    placeholder="OpenRouter"
                  />
                </Field>

                <Field
                  label="API key"
                  hint="Stored in Windows Credential Manager — never in files, logs or replies."
                >
                  <div className="relative">
                    <input
                      type={form.showKey ? 'text' : 'password'}
                      className={`${inputClass} pr-10`}
                      value={form.api_key}
                      onChange={(event) => set('api_key', event.target.value)}
                      placeholder={
                        form.id
                          ? '••••••••  (saved — type to replace)'
                          : 'sk-…  (leave empty if none needed)'
                      }
                      autoComplete="off"
                    />
                    <button
                      type="button"
                      onClick={() => set('showKey', !form.showKey)}
                      aria-label={form.showKey ? 'Hide key' : 'Show key'}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-inksoft hover:text-ink"
                    >
                      {form.showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </Field>

                <Field label="Base URL" hint="The API root — for example https://api.openai.com/v1">
                  <input
                    className={inputClass}
                    value={form.base_url}
                    onChange={(event) => onBaseUrl(event.target.value)}
                    placeholder="http://localhost:11434"
                    spellCheck={false}
                  />
                </Field>

                <div className="flex flex-wrap gap-2">
                  {presets.map((preset) => (
                    <button
                      key={preset.label}
                      onClick={() => applyPreset(preset)}
                      className={`rounded-full border px-3 py-1.5 text-xs ${
                        form.base_url && form.base_url === preset.base_url
                          ? 'border-accent/70 text-ink'
                          : 'border-line text-inksoft hover:border-accent/60 hover:text-ink'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => doFetch()}
                  disabled={fetching}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface2 disabled:opacity-60"
                >
                  <Refresh size={15} className={fetching ? 'animate-spin' : ''} />
                  {fetching ? 'Fetching models…' : 'Fetch models'}
                </button>

                {step === 'models' && (
                  <div className="space-y-3 rounded-xl border border-line p-3.5">
                    <div className="flex items-center gap-2">
                      <Search size={14} className="shrink-0 text-inksoft" />
                      <input
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Filter models…"
                        className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-inksoft"
                      />
                      <span className="shrink-0 text-[11px] text-inksoft">
                        {selectedCount}/{rows.length} picked
                      </span>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => selectAll(false)}
                        className="rounded-lg border border-line px-2.5 py-1 text-xs text-inksoft hover:border-accent/60 hover:text-ink"
                      >
                        Select all
                      </button>
                      <button
                        onClick={() => selectAll(true)}
                        className="rounded-lg border border-line px-2.5 py-1 text-xs text-inksoft hover:border-accent/60 hover:text-ink"
                      >
                        Select all free
                      </button>
                      <button
                        onClick={() => doFetch()}
                        disabled={fetching}
                        className="rounded-lg border border-line px-2.5 py-1 text-xs text-inksoft hover:border-accent/60 hover:text-ink disabled:opacity-60"
                      >
                        {fetching ? 'Re-fetching…' : 'Re-fetch'}
                      </button>
                    </div>

                    <div className="max-h-[240px] space-y-1 overflow-y-auto">
                      {visibleRows.length === 0 && (
                        <p className="py-4 text-center text-xs text-inksoft">
                          {rows.length === 0
                            ? 'No models yet — fetch them or add one by hand.'
                            : 'Nothing matches that filter.'}
                        </p>
                      )}
                      {visibleRows.map((row) => (
                        <div
                          key={row.id}
                          className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 hover:bg-surface2"
                        >
                          <input
                            type="checkbox"
                            checked={row.on}
                            onChange={() => toggleRow(row.id)}
                            aria-label={`Use ${row.id}`}
                            className="h-3.5 w-3.5 accent-[var(--accent)]"
                          />
                          <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                            {row.id}
                          </span>
                          <TagChip
                            tag={row.tag}
                            onClick={() => cycleTag(row.id)}
                            title={
                              row.tag_locked
                                ? 'Locked — a re-fetch will not change it. Click to switch.'
                                : 'Click to set Free or Paid'
                            }
                          />
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        value={manual}
                        onChange={(event) => setManual(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            addManual();
                          }
                        }}
                        placeholder="Add model manually, e.g. gpt-4o-mini"
                        className={inputClass}
                      />
                      <button
                        onClick={addManual}
                        className="shrink-0 rounded-lg border border-line px-3 py-2 text-xs text-inksoft hover:border-accent/60 hover:text-ink"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <button
                    onClick={saveForm}
                    disabled={busy || fetching || !form.name.trim()}
                    className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentstrong disabled:opacity-40"
                  >
                    Save
                  </button>
                  {step === 'details' && (
                    <span className="text-[11px] text-inksoft">
                      Fetch models, pick the ones Mot may use, then save.
                    </span>
                  )}
                  <button
                    onClick={closeForm}
                    className="ml-auto rounded-xl px-3 py-2 text-sm text-inksoft hover:text-ink"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              /* ---- provider list ---- */
              <div className="space-y-3">
                {providers.length === 0 && (
                  <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-inksoft">
                    No providers yet. Add one — the Ollama preset works out of the box.
                  </p>
                )}

                {providers.map((provider) => {
                  const isActive = settings.active?.provider_id === provider.id;
                  const activeModel = isActive
                    ? provider.models.find((m) => m.id === settings.active?.model_id)
                    : null;
                  return (
                    <div
                      key={provider.id}
                      className={`rounded-xl border p-3.5 ${
                        isActive ? 'border-accent/60' : 'border-line'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-ink">
                              {provider.name}
                            </span>
                            {activeModel && (
                              <span className="flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[10.5px] font-medium text-accentink">
                                <Check size={11} /> {activeModel.id}
                              </span>
                            )}
                            {provider.has_key && (
                              <span className="text-[11px] text-inksoft">
                                key {provider.key_masked}
                              </span>
                            )}
                          </div>
                          <div className="mt-0.5 truncate text-xs text-inksoft">
                            {provider.base_url || 'default host'} · {provider.model_count}{' '}
                            {provider.model_count === 1 ? 'model' : 'models'}
                          </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            onClick={() => openProvider(provider, 'models')}
                            disabled={busy}
                            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-accentink hover:bg-surface2"
                          >
                            Manage models
                          </button>
                          <button
                            onClick={() => openProvider(provider, 'details')}
                            aria-label={`Edit ${provider.name}`}
                            className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            onClick={() => setConfirmId(provider.id)}
                            aria-label={`Delete ${provider.name}`}
                            className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-red-500"
                          >
                            <Trash size={15} />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                <button
                  onClick={openAdd}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm text-inksoft hover:border-accent/60 hover:text-ink"
                >
                  <Plus size={16} />
                  Add provider
                </button>
              </div>
            ))}

          {tab === 'apps' && <AppsPanel />}

          {tab === 'routines' && <RoutinesPanel />}

          {tab === 'contacts' && <ContactsPanel />}

          {tab === 'appearance' && (
            <div className="space-y-2">
              {[
                ['light', 'Light'],
                ['dark', 'Dark'],
                ['system', 'System'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTheme(key)}
                  className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors ${
                    settings.theme === key
                      ? 'border-accent/60 bg-accent/10 text-ink'
                      : 'border-line text-inksoft hover:text-ink'
                  }`}
                >
                  <span
                    className={`h-3.5 w-3.5 rounded-full border-2 ${
                      settings.theme === key ? 'border-accent bg-accent' : 'border-line'
                    }`}
                  />
                  {label}
                  {settings.theme === key && (
                    <Check size={15} className="ml-auto text-accentink" />
                  )}
                </button>
              ))}
              <p className="pt-2 text-[11px] text-inksoft">
                Keys are stored in Windows Credential Manager, not in this app's files.
              </p>
            </div>
          )}
        </div>
      </div>

      {confirmId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-2xl">
            <h3 className="text-sm font-semibold text-ink">Delete this provider?</h3>
            <p className="mt-1.5 text-sm text-inksoft">
              Its saved models and its API key (from Windows Credential Manager) are removed
              too. Chats you already saved keep their history.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmId(null)}
                className="rounded-xl px-3.5 py-2 text-sm text-inksoft hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={() => removeProvider(confirmId)}
                disabled={busy}
                className="rounded-xl bg-red-500/15 px-3.5 py-2 text-sm font-medium text-red-500 hover:bg-red-500/25 disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
