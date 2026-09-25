"use client";

import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/format";
import type { ProjectSummary } from "@/lib/types";

export function RepoHeader({
  project,
  scanning,
  onRescan,
}: {
  project: ProjectSummary;
  scanning?: boolean;
  onRescan?: () => void;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-ink-700 pb-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="truncate text-lg font-semibold text-white">
            <span className="text-slate-500">{project.owner}/</span>
            {project.repo}
          </h1>
          <Badge tone="neutral" title="Branch used for analysis">
            ⎇ {project.branch}
          </Badge>
          {project.is_wordpress ? (
            <Badge tone="ok">WordPress</Badge>
          ) : (
            <Badge tone="neutral">No WordPress</Badge>
          )}
          {project.elementor.elementor === "detected" ? (
            <Badge tone="accent">Elementor</Badge>
          ) : null}
          {project.elementor.elementor_pro === "detected" ? (
            <Badge tone="accent">Elementor Pro</Badge>
          ) : null}
          {project.themes.filter((t) => t.theme_type === "child").length ? (
            <Badge tone="accent">Child theme</Badge>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-slate-400">
          {project.description || "No repository description."} · Last scan{" "}
          {formatRelative(project.scanned_at)}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <a
          href={`https://github.com/${project.owner}/${project.repo}`}
          target="_blank"
          rel="noreferrer"
          className="focus-ring h-8 rounded-lg border border-ink-600 px-3 text-xs font-medium text-slate-300 transition hover:bg-ink-800"
        >
          Open on GitHub ↗
        </a>
        {onRescan ? (
          <button
            type="button"
            onClick={onRescan}
            disabled={scanning}
            className="focus-ring h-8 rounded-lg bg-accent px-3 text-xs font-semibold text-white transition hover:bg-accent-soft disabled:opacity-60"
          >
            {scanning ? "Scanning…" : "Re-scan"}
          </button>
        ) : null}
      </div>
    </header>
  );
}
