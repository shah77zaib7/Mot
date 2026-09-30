import { useEffect, useRef } from 'react';
import { ArrowUp, Gear, Mic, Square } from './icons.jsx';
import ModelMenu from './ModelMenu.jsx';

export default function InputBar({
  value,
  onChange,
  onSend,
  onStop,
  busy,
  providers,
  active,
  onModelChange,
  onOpenSettings,
}) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  const hasModels = providers.some((provider) => provider.models.length > 0);

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!busy) onSend();
    }
  };

  return (
    <div className="mx-auto w-full max-w-[760px] px-4 pb-4">
      <div className="rounded-2xl border border-line bg-surface p-2 shadow-sm transition-colors focus-within:border-accent/70">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={hasModels ? 'Message Mot…' : 'Add a provider in Settings to start…'}
          className="block max-h-[220px] w-full resize-none bg-transparent px-2.5 py-2 text-[15px] leading-relaxed text-ink outline-none placeholder:text-inksoft"
        />

        <div className="mt-1 flex items-center gap-2 px-1">
          <ModelMenu
            providers={providers}
            active={active}
            onPick={onModelChange}
            onOpenSettings={onOpenSettings}
          />

          <button
            onClick={onOpenSettings}
            aria-label="Open settings"
            title="Model settings"
            className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
          >
            <Gear size={16} />
          </button>

          {/* Voice comes in a later phase */}
          <button
            disabled
            aria-label="Voice input (coming later)"
            title="Voice is coming later"
            className="rounded-lg p-1.5 text-inksoft opacity-40"
          >
            <Mic size={17} />
          </button>

          <div className="ml-auto flex items-center gap-2">
            {busy ? (
              <button
                onClick={onStop}
                className="flex items-center gap-1.5 rounded-xl border border-line bg-surface2 px-3.5 py-2 text-[13px] font-medium text-ink hover:border-red-500/50 hover:text-red-500"
              >
                <Square size={13} />
                Stop
              </button>
            ) : (
              <button
                onClick={onSend}
                disabled={!value.trim() || !hasModels}
                aria-label="Send"
                className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-white transition-opacity hover:bg-accentstrong disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
      </div>

      <p className="mt-2 text-center text-[11px] text-inksoft/80">
        Enter to send · Shift+Enter for a new line · Esc to stop
      </p>
    </div>
  );
}
