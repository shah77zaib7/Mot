import { useState } from 'react';
import { Gear, Menu, Plus, Trash } from './icons.jsx';

function ChatRow({ chat, active, onSelect, onDelete }) {
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <div className="flex items-center gap-1.5 rounded-lg bg-surface2 px-2.5 py-2 text-xs">
        <span className="min-w-0 flex-1 truncate text-ink">Delete chat?</span>
        <button
          onClick={() => onDelete(chat.id)}
          className="rounded-md bg-red-500/15 px-2 py-1 font-medium text-red-500 hover:bg-red-500/25"
        >
          Delete
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="rounded-md px-2 py-1 text-inksoft hover:bg-surface"
        >
          Keep
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelect(chat.id)}
      className={`group flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
        active ? 'bg-surface2 text-ink' : 'text-inksoft hover:bg-surface2 hover:text-ink'
      }`}
      title={chat.title}
    >
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          active ? 'bg-accent' : 'bg-line group-hover:bg-inksoft'
        }`}
      />
      <span className="min-w-0 flex-1 truncate">{chat.title}</span>
      <span
        role="button"
        tabIndex={0}
        aria-label="Delete chat"
        onClick={(event) => {
          event.stopPropagation();
          setConfirming(true);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.stopPropagation();
            setConfirming(true);
          }
        }}
        className="hidden shrink-0 rounded p-1 text-inksoft hover:bg-surface hover:text-red-500 group-hover:block"
      >
        <Trash size={14} />
      </span>
    </button>
  );
}

export default function Sidebar({
  open,
  chats,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onSettings,
  onClose,
}) {
  return (
    <aside
      className={`${
        open ? 'w-[264px]' : 'w-0'
      } flex h-full shrink-0 flex-col overflow-hidden border-r border-line bg-surface transition-[width] duration-200`}
    >
      <div className="flex items-center justify-between px-3 pt-3">
        <span className="select-none px-1 text-[15px] font-semibold tracking-tight text-ink">
          Mot<span className="text-accent">.</span>
        </span>
        <button
          onClick={onClose}
          aria-label="Hide sidebar"
          className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
        >
          <Menu size={18} />
        </button>
      </div>

      <div className="px-3 pt-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/60 hover:bg-surface2"
        >
          <Plus size={16} />
          New chat
          <span className="ml-auto text-[11px] font-normal text-inksoft">Ctrl+K</span>
        </button>
      </div>

      <div className="px-4 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-wider text-inksoft">
        Chats
      </div>

      <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
        {chats.length === 0 ? (
          <p className="px-2 py-1 text-xs text-inksoft">No chats yet.</p>
        ) : (
          chats.map((chat) => (
            <ChatRow
              key={chat.id}
              chat={chat}
              active={chat.id === activeId}
              onSelect={onSelect}
              onDelete={onDelete}
            />
          ))
        )}
      </nav>

      <div className="border-t border-line p-3">
        <button
          onClick={onSettings}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-inksoft transition-colors hover:bg-surface2 hover:text-ink"
        >
          <Gear size={17} />
          Settings
        </button>
      </div>
    </aside>
  );
}

export function SidebarToggle({ onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label="Show sidebar"
      className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
    >
      <Menu size={18} />
    </button>
  );
}
