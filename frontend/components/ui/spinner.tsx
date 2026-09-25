export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/25 border-t-accent ${className}`}
    />
  );
}

export function LoadingState({
  label = "Loading…",
  className = "",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={`flex items-center justify-center gap-3 rounded-xl border border-ink-700 bg-ink-850 py-10 text-sm text-slate-400 ${className}`}
    >
      <Spinner />
      {label}
    </div>
  );
}
