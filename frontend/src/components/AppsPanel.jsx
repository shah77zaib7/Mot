// Settings > Apps: preferred browser, alias list, re-scan discovery.
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Plus, Refresh, Trash } from './icons.jsx';

const BROWSERS = [
  ['default', 'System default'],
  ['chrome', 'Chrome'],
  ['brave', 'Brave'],
  ['edge', 'Edge'],
];

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

function ago(ts) {
  const seconds = Math.max(0, Date.now() / 1000 - (ts || 0));
  if (!ts) return 'never';
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

export default function AppsPanel() {
  const [data, setData] = useState({ names: [], aliases: {}, browser: 'default', scanned_at: 0 });
  const [alias, setAlias] = useState('');
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = async () => {
    try {
      setData(await api('/api/apps'));
    } catch (err) {
      setNote({ kind: 'error', text: err.message });
    }
  };

  useEffect(() => {
    load();
  }, []);

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

  const putAliases = (next) => run(async () => setData(await api('/api/apps', {
    method: 'PUT',
    body: { aliases: next },
  })));

  const addAlias = () => {
    const key = alias.trim();
    const value = target.trim();
    if (!key || !value) return;
    run(async () => {
      setData(await api('/api/apps', {
        method: 'PUT',
        body: { aliases: { ...data.aliases, [key]: value } },
      }));
      setAlias('');
      setTarget('');
    });
  };

  const entries = Object.entries(data.aliases || {}).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-5">
      {note && (
        <p
          className={`rounded-lg px-3 py-2 text-sm ${
            note.kind === 'error' ? 'bg-red-500/12 text-red-500' : 'bg-surface2 text-inksoft'
          }`}
        >
          {note.text}
        </p>
      )}

      <div>
        <div className="mb-1.5 text-xs font-medium text-inksoft">Preferred browser</div>
        <div className="flex flex-wrap gap-2">
          {BROWSERS.map(([key, label]) => (
            <button
              key={key}
              onClick={() =>
                run(async () => setData(await api('/api/apps', {
                  method: 'PUT',
                  body: { browser: key },
                })))
              }
              disabled={busy}
              className={`rounded-full border px-3 py-1.5 text-xs ${
                data.browser === key
                  ? 'border-accent/70 text-ink'
                  : 'border-line text-inksoft hover:border-accent/60 hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-[11px] text-inksoft">
          Links and searches open here. “System default” uses whatever Windows opens links with.
        </p>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-inksoft">Aliases</span>
          <span className="text-[11px] text-inksoft">
            {data.count || 0} apps found · scanned {ago(data.scanned_at)}
          </span>
        </div>

        <div className="space-y-1">
          {entries.length === 0 && (
            <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-inksoft">
              No aliases yet. An alias lets you type your own name — “wa” opens WhatsApp.
            </p>
          )}
          {entries.map(([key, value]) => (
            <div
              key={key}
              className="flex items-center gap-2 rounded-lg border border-line px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-sm text-ink">{key}</span>
              <span className="text-inksoft">→</span>
              <span className="min-w-0 flex-1 truncate text-sm text-inksoft">{value}</span>
              <button
                onClick={() => {
                  const next = { ...data.aliases };
                  delete next[key];
                  putAliases(next);
                }}
                aria-label={`Delete alias ${key}`}
                className="shrink-0 rounded p-1 text-inksoft hover:text-red-500"
              >
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-2 flex items-center gap-2">
          <input
            value={alias}
            onChange={(event) => setAlias(event.target.value)}
            placeholder="Alias, e.g. wa"
            className={`${inputClass} w-1/3`}
          />
          <input
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            list="mot-app-names"
            placeholder="App it opens, e.g. WhatsApp"
            className={inputClass}
          />
          <button
            onClick={addAlias}
            disabled={busy || !alias.trim() || !target.trim()}
            aria-label="Add alias"
            className="shrink-0 rounded-lg border border-line px-3 py-2 text-inksoft hover:border-accent/60 hover:text-ink disabled:opacity-50"
          >
            <Plus size={15} />
          </button>
        </div>
        <datalist id="mot-app-names">
          {data.names.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>

      <button
        onClick={() =>
          run(async () => {
            setData(await api('/api/apps/rescan', { method: 'POST' }));
            setNote({ kind: 'info', text: 'Apps re-scanned.' });
          })
        }
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface2 disabled:opacity-60"
      >
        <Refresh size={15} className={busy ? 'animate-spin' : ''} />
        {busy ? 'Scanning the Start Menu…' : 'Re-scan apps'}
      </button>
    </div>
  );
}
