import { useState } from 'react';
import Markdown from './Markdown.jsx';
import ActionCard from './ActionCard.jsx';
import { Check, Copy, Refresh } from './icons.jsx';

function UserMessage({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-bubble px-4 py-2.5 text-[15px] leading-relaxed text-ink">
        {text}
      </div>
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-inksoft transition-colors hover:bg-surface2 hover:text-ink"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export default function Message({
  message,
  streaming = false,
  canRegenerate = false,
  onRegenerate,
  onAction,
}) {
  if (message.role === 'user') {
    return (
      <div className="py-2">
        <UserMessage text={message.content} />
      </div>
    );
  }

  const actions = message.actions || [];

  return (
    <div className="group/msg py-2">
      {actions.map((action) => (
        <ActionCard key={action.id} {...action} onConfirm={onAction} />
      ))}
      <div className={streaming ? 'stream-cursor' : undefined}>
        <Markdown>{message.content}</Markdown>
      </div>
      {!streaming && (
        <div className="mt-1.5 flex items-center gap-1 opacity-0 transition-opacity group-hover/msg:opacity-100 focus-within:opacity-100">
          <CopyButton text={message.content} />
          {canRegenerate && (
            <button
              onClick={onRegenerate}
              className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-inksoft transition-colors hover:bg-surface2 hover:text-ink"
            >
              <Refresh size={14} />
              Regenerate
            </button>
          )}
          {message.profile && (
            <span className="ml-auto text-[11px] text-inksoft/70">{message.profile}</span>
          )}
        </div>
      )}
    </div>
  );
}
