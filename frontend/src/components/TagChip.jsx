const TAG_STYLES = {
  free: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  paid: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  local: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  unknown: 'bg-surface2 text-inksoft',
};

const TAG_LABELS = { free: 'Free', paid: 'Paid', local: 'Local', unknown: 'Unknown' };

export default function TagChip({ tag, onClick, title }) {
  const known = TAG_STYLES[tag] ? tag : 'unknown';
  const className = `inline-flex shrink-0 items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none ${TAG_STYLES[known]}`;
  const label = TAG_LABELS[known];
  if (!onClick) {
    return (
      <span className={className} title={title}>
        {label}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title={title || 'Click to set this model as Free or Paid'}
      className={`${className} hover:brightness-110`}
    >
      {label}
    </button>
  );
}
