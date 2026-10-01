// Settings > Drex: one live round trip, canned and friendly.
import { useState } from 'react';
import { api } from '../api.js';
import { Refresh } from './icons.jsx';

const DASHBOARD = 'https://drex.nace.ai/dashboard/api-keys';

function secs(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms} ms`;
}

export default function DrexPanel() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {ok, text, code}

  const check = async () => {
    setBusy(true);
    setResult(null);
    try {
      const data = await api('/api/drex/check', { method: 'POST' });
      if (data.ok) {
        const chance = Math.round((data.noul ?? 0) * 1000) / 10;
        setResult({
          ok: true,
          text: `✓ Drex is reachable — ${chance}% "urgent" in ${secs(data.ms || 0)}`,
        });
      } else {
        setResult({ ok: false, text: data.message, code: data.code });
      }
    } catch (err) {
      setResult({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line p-3.5">
        <div className="text-sm font-semibold text-ink">Drex</div>
        <p className="mt-1 text-xs leading-relaxed text-inksoft">
          Drex gives Mot calibrated probabilities — how likely a piece of text is to mean
          what it looks like it means. The key lives in the project{' '}
          <span className="font-mono">.env</span> file and is never logged or returned.
        </p>

        <button
          onClick={check}
          disabled={busy}
          className="mt-3 flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-surface2 disabled:opacity-60"
        >
          <Refresh size={15} className={busy ? 'animate-spin' : ''} />
          {busy ? 'Checking…' : 'Check connection'}
        </button>

        {result && (
          <p
            className={`mt-3 rounded-lg px-3 py-2 text-sm ${
              result.ok ? 'bg-surface2 text-ink' : 'bg-red-500/12 text-red-500'
            }`}
          >
            {result.text}
          </p>
        )}

        {result && result.code === 'no_key' && (
          <a
            href={DASHBOARD}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-2 inline-block text-xs text-accentink hover:underline"
          >
            Get a key at {DASHBOARD.replace('https://', '')}
          </a>
        )}
      </div>

      <p className="text-[11px] text-inksoft">
        Mot never places trades and never clicks order, buy or sell buttons.
      </p>
    </div>
  );
}
