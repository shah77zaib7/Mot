// Settings > General: window close behaviour, the global shortcut, auto-start.
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Check } from './icons.jsx';

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

const CLOSE_CHOICES = [
  {
    key: true,
    title: 'Minimize to tray',
    detail: 'Mot keeps running in the notification area and the news keeps refreshing.',
  },
  {
    key: false,
    title: 'Quit Mot',
    detail: 'The window closes everything: tray icon, shortcut and the background refresh.',
  },
];

export default function GeneralPanel() {
  const [state, setState] = useState(null);
  const [combo, setCombo] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // {kind, text}

  const load = async () => {
    try {
      const data = await api('/api/general');
      setState(data);
      setCombo(data.hotkey_label || data.hotkey || '');
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

  // Every setting is one field at a time, so a refusal never loses the rest.
  const save = (patch, { keepText = false } = {}) =>
    run(async () => {
      const data = await api('/api/general', { method: 'PUT', body: patch });
      if (!keepText) setCombo(data.hotkey_label || data.hotkey || combo);
      setState(data);
      if (!data.ok) setNote({ kind: 'error', text: data.message });
    });

  const saveHotkey = () => save({ hotkey: combo }, { keepText: true });

  return (
    <div className="space-y-3">
      {note && (
        <p
          className={`rounded-lg px-3 py-2 text-sm ${
            note.kind === 'error' ? 'bg-red-500/12 text-red-500' : 'bg-surface2 text-inksoft'
          }`}
        >
          {note.text}
        </p>
      )}

      {/* ---- close behaviour ---- */}
      <div className="rounded-xl border border-line p-3.5">
        <p className="mb-2 text-sm font-semibold text-ink">When I close the window</p>
        <div className="space-y-2">
          {CLOSE_CHOICES.map((choice) => (
            <button
              key={String(choice.key)}
              onClick={() => save({ close_to_tray: choice.key })}
              disabled={busy}
              className={`flex w-full items-start gap-3 rounded-xl border px-3.5 py-3 text-left transition-colors disabled:opacity-60 ${
                state?.close_to_tray === choice.key
                  ? 'border-accent/60 bg-accent/10'
                  : 'border-line hover:border-accent/40'
              }`}
            >
              <span
                className={`mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full border-2 ${
                  state?.close_to_tray === choice.key
                    ? 'border-accent bg-accent'
                    : 'border-line'
                }`}
              />
              <span className="min-w-0">
                <span className="block text-sm text-ink">{choice.title}</span>
                <span className="mt-0.5 block text-[11px] text-inksoft">{choice.detail}</span>
              </span>
              {state?.close_to_tray === choice.key && (
                <Check size={15} className="ml-auto mt-0.5 shrink-0 text-accentink" />
              )}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-inksoft">
          The first time Mot goes to the tray it says so, once. After that the icon next to
          the clock is all you need — left-click it to bring the window back, or pick{' '}
          <span className="font-medium">Quit Mot</span> to end it.
        </p>
      </div>

      {/* ---- global shortcut ---- */}
      <div className="rounded-xl border border-line p-3.5">
        <p className="mb-2 text-sm font-semibold text-ink">Show / hide Mot</p>
        <div className="flex items-center gap-2">
          <input
            className={`${inputClass} w-56`}
            value={combo}
            spellCheck={false}
            onChange={(event) => setCombo(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                saveHotkey();
              }
            }}
            placeholder="Ctrl+Alt+M"
            aria-label="Global shortcut"
          />
          <button
            onClick={saveHotkey}
            disabled={busy || !combo.trim()}
            className="shrink-0 rounded-xl border border-line px-3.5 py-2 text-sm text-inksoft hover:border-accent/60 hover:text-ink disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Save shortcut'}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-inksoft">
          Press it anywhere in Windows to show Mot, and again to hide it. Use a letter,
          a number or F1–F12 with Ctrl, Alt, Shift or Win.
        </p>
        {state?.hotkey_error && (
          <p className="mt-1.5 text-[11px] text-red-500">{state.hotkey_error}</p>
        )}
      </div>

      {/* ---- auto-start ---- */}
      <div className="rounded-xl border border-line p-3.5">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={Boolean(state?.autostart)}
            disabled={busy || !state}
            onChange={(event) => save({ autostart: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-accent"
          />
          <span className="min-w-0">
            <span className="block text-sm text-ink">Start Mot when I sign in</span>
            <span className="mt-0.5 block text-[11px] text-inksoft">
              Mot starts hidden in the tray, so nothing pops up over your desktop. It only
              adds one entry for your own account — nothing else in Windows is touched.
            </span>
          </span>
        </label>
      </div>

      <p className="text-[11px] text-inksoft">
        Saved in <span className="font-mono">data/config.json</span>; the startup entry
        lives in the registry under your own account.
      </p>
    </div>
  );
}
