const CHIPS = ['Open YouTube', 'Morning setup', 'Gold news today', 'What can you do?'];

export default function EmptyState({ onPick }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 pb-16 text-center">
      <div className="select-none text-5xl font-semibold tracking-tight text-ink">
        Mot<span className="text-accent">.</span>
      </div>
      <p className="mt-3 text-[15px] text-inksoft">
        Ask anything — or tell me what to open.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-2.5">
        {CHIPS.map((chip) => (
          <button
            key={chip}
            onClick={() => onPick(chip)}
            className="rounded-full border border-line bg-surface px-4 py-2 text-sm text-inksoft transition-colors hover:border-accent/60 hover:text-ink"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}
