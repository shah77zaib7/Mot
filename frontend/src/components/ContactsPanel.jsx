// Settings > Contacts: who Mot may open a WhatsApp chat for (never sends by itself).
import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Pencil, Plus, Trash, X } from './icons.jsx';

const inputClass =
  'w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm text-ink outline-none placeholder:text-inksoft focus:border-accent';

const EMPTY = { id: null, name: '', phone: '', aliases: '' };

export default function ContactsPanel() {
  const [contacts, setContacts] = useState([]);
  const [form, setForm] = useState(null); // null = list view
  const [confirmId, setConfirmId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = async () => {
    try {
      const data = await api('/api/contacts');
      setContacts(data.contacts || []);
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

  const save = () =>
    run(async () => {
      const data = await api('/api/contacts', {
        method: 'POST',
        body: {
          id: form.id,
          name: form.name,
          phone: form.phone,
          aliases: form.aliases,
        },
      });
      setContacts(data.contacts);
      setForm(null);
    });

  const remove = (id) =>
    run(async () => {
      const data = await api(`/api/contacts?id=${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      setContacts(data.contacts);
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
        /* ---- contact editor ---- */
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-inksoft">Name</span>
            <input
              className={inputClass}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Mom"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-inksoft">
              Phone number
            </span>
            <input
              className={inputClass}
              value={form.phone}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
              placeholder="+91 98765 43210"
              type="tel"
            />
            <span className="mt-1 block text-[11px] text-inksoft">
              Include the country code — WhatsApp needs it.
            </span>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-inksoft">
              Aliases (optional)
            </span>
            <input
              className={inputClass}
              value={form.aliases}
              onChange={(event) => setForm({ ...form, aliases: event.target.value })}
              placeholder="mother, maa"
            />
            <span className="mt-1 block text-[11px] text-inksoft">
              Other names you call them, separated by commas.
            </span>
          </label>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              onClick={save}
              disabled={busy || !form.name.trim() || !form.phone.trim()}
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
        /* ---- contact list ---- */
        <div className="space-y-3">
          {contacts.length === 0 && (
            <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-inksoft">
              No contacts yet. Add the people you WhatsApp, then say
              “whatsapp Mom hi mom” in the chat.
            </p>
          )}

          {contacts.map((contact) => (
            <div key={contact.id} className="rounded-xl border border-line p-3.5">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-ink">{contact.name}</div>
                  <div className="mt-0.5 truncate text-xs text-inksoft">
                    {contact.phone}
                    {contact.aliases?.length ? ` · ${contact.aliases.join(', ')}` : ''}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() =>
                      setForm({
                        id: contact.id,
                        name: contact.name,
                        phone: contact.phone,
                        aliases: (contact.aliases || []).join(', '),
                      })
                    }
                    aria-label={`Edit ${contact.name}`}
                    className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-ink"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => setConfirmId(contact.id)}
                    aria-label={`Delete ${contact.name}`}
                    className="rounded-lg p-1.5 text-inksoft hover:bg-surface2 hover:text-red-500"
                  >
                    <Trash size={15} />
                  </button>
                </div>
              </div>
            </div>
          ))}

          <button
            onClick={() => setForm({ ...EMPTY })}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm text-inksoft hover:border-accent/60 hover:text-ink"
          >
            <Plus size={16} />
            Add contact
          </button>

          <p className="pt-1 text-[11px] text-inksoft">
            Mot opens the chat with your message already typed in. It never presses Send
            and it never messages anyone who is not on this list.
          </p>
        </div>
      )}

      {confirmId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-2xl">
            <h3 className="text-sm font-semibold text-ink">Delete this contact?</h3>
            <p className="mt-1.5 text-sm text-inksoft">
              Mot will no longer open chats for them. You can add them again later.
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
