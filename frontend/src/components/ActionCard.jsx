// Action card: one step Mot took ("Opened YouTube"), with live status.
// status: running | done | failed | needs_confirm | cancelled

import { useState } from 'react';

const TONES = {
  running: 'text-accentink',
  done: 'text-accentink',
  failed: 'text-red-500',
  needs_confirm: 'text-amber-600 dark:text-amber-400',
  cancelled: 'text-inksoft',
};

const LABELS = {
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  needs_confirm: 'Confirm',
  cancelled: 'Cancelled',
};

const MARKS = {
  running: '⋯',
  done: '✓',
  failed: '!',
  needs_confirm: '?',
  cancelled: '×',
};

// A news card: headline, source, age, and a link that only opens on click.
function Headline({ item }) {
  return (
    <li className="flex items-start gap-2">
      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-accent" />
      <span className="min-w-0 flex-1">
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-[13px] leading-snug text-ink hover:text-accentink hover:underline"
        >
          {item.title}
        </a>
        <span className="block truncate text-[11px] text-inksoft">
          {item.source}
          {item.when ? ` · ${item.when}` : ''}
        </span>
      </span>
    </li>
  );
}

export default function ActionCard({
  id,
  title,
  detail,
  status = 'done',
  steps,
  data,
  onConfirm,
  onSummarize,
  onRetry,
}) {
  const [open, setOpen] = useState(false);
  const tone = TONES[status] ?? TONES.done;
  const list = Array.isArray(steps) && steps.length ? steps : null;
  const items = Array.isArray(data?.items) && data.items.length ? data.items : null;
  // With headlines on screen the detail line already says what it would expand to.
  const expandable = Boolean(list || (detail && !items));

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex items-start gap-3 px-3.5 py-3">
        <span
          className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-surface2 text-[13px] ${tone}`}
        >
          {MARKS[status] ?? '✓'}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-ink">{title}</div>
          {detail && !open ? (
            <div className="mt-0.5 truncate text-xs text-inksoft">{detail}</div>
          ) : null}
        </div>

        {status === 'needs_confirm' && onConfirm ? (
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={() => onConfirm(id, true)}
              className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accentstrong"
            >
              Confirm
            </button>
            <button
              onClick={() => onConfirm(id, false)}
              className="rounded-lg border border-line px-2.5 py-1 text-xs text-inksoft hover:text-ink"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex shrink-0 items-center gap-1.5">
            {status === 'failed' && data?.retry && onRetry ? (
              <button
                onClick={onRetry}
                className="rounded-lg border border-accent/60 px-2.5 py-0.5 text-[11px] font-medium text-ink hover:bg-surface2"
              >
                Retry
              </button>
            ) : null}
            <span
              className={`shrink-0 rounded-full bg-surface2 px-2 py-0.5 text-[11px] font-medium ${tone}`}
            >
              {LABELS[status] ?? 'Done'}
            </span>
          </div>
        )}
      </div>

      {items && (
        <div className="border-t border-line/70 px-3.5 py-2.5">
          <ul className="space-y-2">
            {items.map((item, index) => (
              <Headline key={item.url || index} item={item} />
            ))}
          </ul>
          {status === 'done' && onSummarize ? (
            <button
              onClick={() =>
                onSummarize(items, data?.topic || (data?.query || '').replace(/\s*news$/i, ''))
              }
              className="mt-2.5 rounded-lg border border-line px-2.5 py-1 text-xs text-inksoft hover:border-accent/60 hover:text-ink"
            >
              Summarize
            </button>
          ) : null}
          {data?.updated || data?.failed ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-inksoft">
              <span>Updated {data.updated || '—'}</span>
              {data.offline ? <span>· offline</span> : null}
              {data.failed ? (
                <span className="text-red-500/80">
                  · {data.failed}
                  {data.sources ? ` of ${data.sources}` : ''} source
                  {data.failed === 1 && !data.sources ? '' : 's'} failed
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      {expandable && (
        <button
          onClick={() => setOpen((value) => !value)}
          aria-label={open ? 'Hide details' : 'Show details'}
          className="flex w-full items-center gap-1.5 border-t border-line/70 px-3.5 py-1.5 text-[11px] text-inksoft hover:bg-surface2 hover:text-ink"
        >
          <span className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
          {open ? 'Hide details' : 'Details'}
        </button>
      )}

      {open && expandable && (
        <div className="border-t border-line/70 px-3.5 py-2.5 text-xs text-inksoft">
          {list ? (
            <ul className="space-y-1.5">
              {list.map((step, index) => (
                <li key={index} className="flex items-start gap-2">
                  <span
                    className={
                      step.status === 'failed'
                        ? 'text-red-500'
                        : step.status === 'running'
                          ? 'text-accentink'
                          : 'text-accentink/80'
                    }
                  >
                    {step.status === 'failed' ? '×' : step.status === 'running' ? '⋯' : '✓'}
                  </span>
                  <span className="min-w-0 flex-1">
                    {step.title}
                    {step.detail ? (
                      <span className="block truncate text-[11px] opacity-80">{step.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="break-words">{detail}</div>
          )}
        </div>
      )}
    </div>
  );
}
