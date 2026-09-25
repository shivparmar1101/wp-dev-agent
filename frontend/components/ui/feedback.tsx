import { Button } from "./button";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  icon?: React.ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      {icon ? <div className="mb-1 text-ink-500">{icon}</div> : null}
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {description ? (
        <p className="max-w-md text-xs leading-relaxed text-slate-400">{description}</p>
      ) : null}
      {action ? (
        <Button variant="primary" size="sm" className="mt-3" onClick={action.onClick}>
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="panel border-danger/40 bg-danger/5 px-6 py-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-danger" aria-hidden>
          ⚠
        </span>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          {description ? (
            <p className="mt-1 break-words text-xs leading-relaxed text-slate-300">
              {description}
            </p>
          ) : null}
        </div>
        {onRetry ? (
          <Button size="sm" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}
