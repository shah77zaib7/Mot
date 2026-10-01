// Settings > Feeds: the RSS sources behind "gold news" and friends.
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Plus, Trash } from './icons.jsx';

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

function host(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

// "14:03" for the last refresh, "never" when it hasn't run yet.
function stamp(ts) {
  if (!ts) return 'never';
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function FeedsPanel() {
  const [topics, setTopics] = useState({}); // {topic: [url, ...]}
  const [defaults, setDefaults] = useState({});
  const [ingest, setIngest] = useState(null); // interval, toggle, last refresh
  const [hours, setHours] = useState('2');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // {kind, text}
  const [testUrl, setTestUrl] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const data = await api('/api/feeds');
        setTopics(data.topics || {});
        setDefaults(data.defaults || {});
        setIngest(data.ingest || null);
        setHours(String(data.ingest?.interval_hours ?? 2));
      } catch (err) {
        setNote({ kind: 'error', text: err.message });
      }
    })();
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

  const save = () =>
    run(async () => {
      const data = await api('/api/feeds', { method: 'PUT', body: { topics } });
      if (!data.ok) {
        setNote({ kind: 'error', text: data.message });
        return;
      }
      setTopics(data.topics);
      setNote({ kind: 'info', text: data.message });
    });

  const restore = () =>
    run(async () => {
      const data = await api('/api/feeds', { method: 'PUT', body: { topics: defaults } });
      if (data.ok) {
        setTopics(data.topics);
        setNote({ kind: 'info', text: 'Back to the built-in feed list.' });
      } else {
        setNote({ kind: 'error', text: data.message });
      }
    });

  const applyIngest = (patch) =>
    run(async () => {
      const data = await api('/api/feeds/ingest', { method: 'PUT', body: patch });
      setIngest(data.ingest);
    });

  const refreshNow = () =>
    run(async () => {
      const data = await api('/api/feeds/refresh', { method: 'POST' });
      if (data.ingest) setIngest(data.ingest);
      if (data.busy) {
        setNote({ kind: 'info', text: 'A refresh is already running.' });
      } else if (data.ok) {
        const failed = data.ingest?.failed || 0;
        setNote({
          kind: 'info',
          text: `Refreshed at ${stamp(data.ingest?.last_ingest_at)}${
            failed
              ? ` — ${failed} of ${data.ingest.sources} sources failing.`
              : ' — all sources answered.'
          }`,
        });
      } else {
        setNote({ kind: 'error', text: 'Refresh failed. The reason is in logs/mot.log.' });
      }
    });

  const edit = (topic, index, value) =>
    setTopics((prev) => ({
      ...prev,
      [topic]: prev[topic].map((url, i) => (i === index ? value : url)),
    }));

  const removeUrl = (topic, index) =>
    setTopics((prev) => {
      const next = { ...prev, [topic]: prev[topic].filter((_, i) => i !== index) };
      if (!next[topic].length) delete next[topic];
      return next;
    });

  const addUrl = (topic) =>
    setTopics((prev) => ({ ...prev, [topic]: [...(prev[topic] || []), ''] }));

  const addTopic = () =>
    setTopics((prev) => ({ ...prev, [`topic-${Date.now()}`]: [''] }));

  const testOne = (url) =>
    run(async () => {
      setTestUrl(url);
      const data = await api('/api/feeds/test', { method: 'POST', body: { url } });
      setNote({ kind: data.ok ? 'info' : 'error', text: data.message });
      setTestUrl('');
    });

  const topicList = Object.entries(topics);

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

      <div className="rounded-xl border border-line p-3.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={ingest?.enabled ?? true}
              onChange={(event) => applyIngest({ enabled: event.target.checked })}
              className="h-4 w-4 accent-accent"
            />
            Refresh automatically
          </label>

          <label className="flex items-center gap-1.5 text-sm text-inksoft">
            every
            <input
              type="number"
              min="0.25"
              max="24"
              step="0.25"
              value={hours}
              onChange={(event) => setHours(event.target.value)}
              onBlur={() => applyIngest({ interval_hours: Number(hours) })}
              className={`${inputClass} w-20`}
            />
            hours
          </label>

          <button
            onClick={refreshNow}
            disabled={busy}
            className="ml-auto rounded-lg border border-line px-3 py-1.5 text-sm text-inksoft hover:border-accent/60 hover:text-ink disabled:opacity-50"
          >
            {busy ? 'Refreshing…' : 'Refresh now'}
          </button>
        </div>

        <p className="mt-2 text-[11px] text-inksoft">
          Last updated {stamp(ingest?.last_ingest_at)}
          {ingest?.failed
            ? ` · ${ingest.failed} of ${ingest.sources} sources failing`
            : ingest?.sources
              ? ' · all sources ok'
              : ''}
        </p>
      </div>

      {topicList.length === 0 && (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-inksoft">
          No feeds yet. Add one and “gold news” will use it.
        </p>
      )}

      {topicList.map(([topic, urls]) => (
        <div key={topic} className="rounded-xl border border-line p-3.5">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-sm font-semibold text-ink">{topic}</span>
            <span className="text-[11px] text-inksoft">
              {urls.length} {urls.length === 1 ? 'feed' : 'feeds'}
            </span>
          </div>

          <div className="space-y-2">
            {urls.map((url, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  className={`${inputClass} flex-1`}
                  value={url}
                  spellCheck={false}
                  onChange={(event) => edit(topic, index, event.target.value)}
                  placeholder="https://example.com/rss"
                />
                <button
                  onClick={() => testOne(url)}
                  disabled={busy || !url.trim()}
                  className="shrink-0 rounded-lg border border-line px-2.5 py-1.5 text-xs text-inksoft hover:border-accent/60 hover:text-ink disabled:opacity-50"
                >
                  {busy && testUrl === url ? 'Testing…' : 'Test'}
                </button>
                <button
                  onClick={() => removeUrl(topic, index)}
                  aria-label={`Remove ${host(url)}`}
                  className="shrink-0 rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-red-500"
                >
                  <Trash size={14} />
                </button>
              </div>
            ))}
          </div>

          <button
            onClick={() => addUrl(topic)}
            className="mt-2 flex items-center gap-1.5 text-xs text-inksoft hover:text-ink"
          >
            <Plus size={13} /> Add feed
          </button>
        </div>
      ))}

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          onClick={addTopic}
          className="flex items-center gap-1.5 rounded-xl border border-dashed border-line px-3.5 py-2 text-sm text-inksoft hover:border-accent/60 hover:text-ink"
        >
          <Plus size={15} /> Add topic
        </button>
        <button
          onClick={save}
          disabled={busy}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentstrong disabled:opacity-50"
        >
          Save
        </button>
        <button
          onClick={restore}
          disabled={busy}
          className="ml-auto rounded-xl px-3 py-2 text-sm text-inksoft hover:text-ink disabled:opacity-50"
        >
          Restore defaults
        </button>
      </div>

      <p className="text-[11px] text-inksoft">
        Saved to <span className="font-mono">data/feeds.json</span>. Refreshed in the
        background every {ingest?.interval_hours ?? 2} h; headlines older than 48 hours drop
        off.
      </p>
    </div>
  );
}
