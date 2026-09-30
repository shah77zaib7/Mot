// Settings > Routines: name + ordered steps (open website / open app).
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Pencil, Plus, Trash, X } from './icons.jsx';

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

const EMPTY = { id: null, name: '', steps: [{ action: 'open_url', url: '' }] };

function describe(step) {
  if (step.action === 'open_app') return `Open ${step.name || '…'}`;
  return `Open ${step.url || '…'}`;
}

export default function RoutinesPanel() {
  const [routines, setRoutines] = useState([]);
  const [names, setNames] = useState([]);
  const [form, setForm] = useState(null); // null = list view
  const [confirmId, setConfirmId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = async () => {
    try {
      const data = await api('/api/routines');
      setRoutines(data.routines);
      const apps = await api('/api/apps');
      setNames(apps.names || []);
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

  const setStep = (index, patch) =>
    setForm((prev) => ({
      ...prev,
      steps: prev.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    }));

  const move = (index, delta) =>
    setForm((prev) => {
      const steps = [...prev.steps];
      const to = index + delta;
      if (to < 0 || to >= steps.length) return prev;
      [steps[index], steps[to]] = [steps[to], steps[index]];
      return { ...prev, steps };
    });

  const save = () =>
    run(async () => {
      const data = await api('/api/routines', { method: 'POST', body: form });
      setRoutines(data.routines);
      setForm(null);
    });

  const remove = (id) =>
    run(async () => {
      const data = await api(`/api/routines?id=${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      setRoutines(data.routines);
      setConfirmId(null);
    });

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

      {form ? (
        /* ---- routine editor ---- */
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-inksoft">Routine name</span>
            <input
              className={inputClass}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Morning setup"
            />
          </label>

          <div className="space-y-2">
            <span className="block text-xs font-medium text-inksoft">Steps (in order)</span>
            {form.steps.map((step, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="w-4 shrink-0 text-right text-[11px] text-inksoft">
                  {index + 1}
                </span>
                <select
                  value={step.action}
                  onChange={(event) =>
                    setStep(
                      index,
                      event.target.value === 'open_app'
                        ? { action: 'open_app', name: step.name || '', url: undefined }
                        : { action: 'open_url', url: step.url || '', name: undefined }
                    )
                  }
                  className={`${inputClass} w-36 shrink-0`}
                >
                  <option value="open_url">Open website</option>
                  <option value="open_app">Open app</option>
                </select>
                <input
                  className={inputClass}
                  value={step.action === 'open_app' ? step.name || '' : step.url || ''}
                  list={step.action === 'open_app' ? 'mot-app-names' : undefined}
                  placeholder={step.action === 'open_app' ? 'WhatsApp' : 'https://…'}
                  spellCheck={false}
                  onChange={(event) =>
                    setStep(
                      index,
                      step.action === 'open_app'
                        ? { name: event.target.value }
                        : { url: event.target.value }
                    )
                  }
                />
                <div className="flex shrink-0 flex-col">
                  <button
                    onClick={() => move(index, -1)}
                    aria-label="Move step up"
                    className="px-1 text-[10px] leading-3 text-inksoft hover:text-ink"
                  >
                    ▲
                  </button>
                  <button
                    onClick={() => move(index, 1)}
                    aria-label="Move step down"
                    className="px-1 text-[10px] leading-3 text-inksoft hover:text-ink"
                  >
                    ▼
                  </button>
                </div>
                <button
                  onClick={() =>
                    setForm((prev) => ({ ...prev, steps: prev.steps.filter((_, i) => i !== index) }))
                  }
                  aria-label="Delete step"
                  className="shrink-0 rounded p-1 text-inksoft hover:text-red-500"
                >
                  <Trash size={14} />
                </button>
              </div>
            ))}
            {form.steps.length === 0 && (
              <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-inksoft">
                Add at least one step.
              </p>
            )}
          </div>

          <datalist id="mot-app-names">
            {names.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              onClick={() =>
                setForm({ ...form, steps: [...form.steps, { action: 'open_url', url: '' }] })
              }
              className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs text-inksoft hover:border-accent/60 hover:text-ink"
            >
              <Plus size={14} /> Add step
            </button>
            <button
              onClick={save}
              disabled={busy || !form.name.trim() || form.steps.length === 0}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentstrong disabled:opacity-40"
            >
              Save
            </button>
            <button
              onClick={() => setForm(null)}
              className="ml-auto rounded-xl px-3 py-2 text-sm text-inksoft hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        /* ---- routine list ---- */
        <div className="space-y-3">
          {routines.length === 0 && (
            <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-inksoft">
              No routines yet.
            </p>
          )}

          {routines.map((routine) => (
            <div key={routine.id} className="rounded-xl border border-line p-3.5">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-ink">{routine.name}</div>
                  <div className="mt-1 space-y-0.5">
                    {routine.steps.map((step, index) => (
                      <div key={index} className="truncate text-xs text-inksoft">
                        {index + 1}. {describe(step)}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => setForm(JSON.parse(JSON.stringify(routine)))}
                    aria-label={`Edit ${routine.name}`}
                    className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => setConfirmId(routine.id)}
                    aria-label={`Delete ${routine.name}`}
                    className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-red-500"
                  >
                    <Trash size={15} />
                  </button>
                </div>
              </div>
            </div>
          ))}

          <button
            onClick={() => setForm({ ...EMPTY, steps: [{ action: 'open_url', url: '' }] })}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm text-inksoft hover:border-accent/60 hover:text-ink"
          >
            <Plus size={16} />
            Add routine
          </button>
        </div>
      )}

      {confirmId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-2xl">
            <h3 className="text-sm font-semibold text-ink">Delete this routine?</h3>
            <p className="mt-1.5 text-sm text-inksoft">
              Its steps are removed. You can add it again later.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmId(null)}
                className="rounded-xl px-3.5 py-2 text-sm text-inksoft hover:text-ink"
              >
                <X size={14} className="mr-1 inline" />
                Cancel
              </button>
              <button
                onClick={() => remove(confirmId)}
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
