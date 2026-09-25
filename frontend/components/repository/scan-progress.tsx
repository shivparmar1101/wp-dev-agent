"use client";

import { Spinner } from "@/components/ui/spinner";
import type { ScanStatus } from "@/lib/types";

const ORDER: { id: string; label: string }[] = [
  { id: "connecting", label: "Connecting to GitHub" },
  { id: "reading_tree", label: "Reading repository tree" },
  { id: "detecting_wordpress", label: "Detecting WordPress" },
  { id: "detecting_themes", label: "Detecting themes" },
  { id: "detecting_plugins", label: "Detecting plugins" },
  { id: "detecting_elementor", label: "Detecting Elementor" },
  { id: "indexing_php", label: "Indexing PHP" },
  { id: "indexing_css", label: "Indexing CSS" },
  { id: "indexing_javascript", label: "Indexing JavaScript" },
  { id: "building_index", label: "Building search index" },
];

export function ScanProgress({
  scan,
  onCancel,
}: {
  scan: ScanStatus;
  onCancel?: () => void;
}) {
  const stages = scan.stages?.length
    ? scan.stages
    : ORDER.map((s) => ({ ...s, status: "pending" as const, detail: null }));

  const doneCount = stages.filter(
    (s) => s.status === "done" || s.status === "skipped",
  ).length;
  const pct = scan.status === "completed" ? 100 : Math.round(scan.progress * 100);

  return (
    <div className="panel animate-fade-up p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          {scan.status === "failed" ? (
            <span className="text-danger" aria-hidden>
              ⚠
            </span>
          ) : (
            <Spinner />
          )}
          <div>
            <h3 className="text-sm font-semibold text-white">
              {scan.status === "failed"
                ? "Scan failed"
                : scan.status === "completed"
                  ? "Scan complete"
                  : "Analyzing repository…"}
            </h3>
            <p className="text-xs text-slate-400">
              {scan.status === "failed"
                ? scan.error || "An unexpected error occurred."
                : `${doneCount} of ${stages.length} stages · branch ${scan.branch || "default"}`}
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-white">{pct}%</div>
          <div className="text-[11px] text-ink-500">progress</div>
        </div>
      </div>

      <div className="mb-5 h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            scan.status === "failed" ? "bg-danger" : "bg-accent"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <ol className="grid gap-1.5 sm:grid-cols-2">
        {stages.map((stage) => (
          <li
            key={stage.id}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs"
            style={{
              background: stage.status === "running" ? "rgba(109,139,255,0.08)" : undefined,
            }}
          >
            <StageDot status={stage.status} />
            <span
              className={
                stage.status === "running"
                  ? "font-medium text-accent-soft"
                  : stage.status === "error"
                    ? "text-danger"
                    : stage.status === "done"
                      ? "text-slate-200"
                      : "text-ink-500"
              }
            >
              {stage.label}
            </span>
            {stage.detail ? (
              <span className="ml-auto truncate text-[10px] text-ink-500" title={stage.detail}>
                {stage.detail}
              </span>
            ) : null}
          </li>
        ))}
      </ol>

      {scan.status === "failed" ? (
        <div className="mt-4">
          {scan.error_details ? (
            <pre className="mb-3 max-h-40 overflow-auto rounded-lg border border-danger/30 bg-danger/5 p-3 text-[11px] text-danger/90">
              {scan.error_details}
            </pre>
          ) : null}
          {onCancel ? (
            <button
              type="button"
              className="focus-ring h-8 rounded-lg border border-ink-600 px-3 text-xs font-medium text-slate-300 hover:bg-ink-800"
              onClick={onCancel}
            >
              Back to repository
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function StageDot({ status }: { status: string }) {
  if (status === "done") {
    return (
      <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-ok/20 text-[10px] text-ok">
        ✓
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-danger/20 text-[10px] text-danger">
        ✕
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="h-3 w-3 animate-pulse rounded-full bg-accent" aria-hidden />
    );
  }
  if (status === "skipped") {
    return <span className="h-3 w-3 rounded-full border border-ink-600" aria-hidden />;
  }
  return <span className="h-3 w-3 rounded-full bg-ink-700" aria-hidden />;
}
