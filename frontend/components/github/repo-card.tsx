"use client";

import { Badge } from "@/components/ui/badge";
import { languageColor, formatNumber, formatRelative } from "@/lib/format";
import type { Repository } from "@/lib/types";

export function RepoCard({
  repo,
  onAnalyze,
  analyzing,
}: {
  repo: Repository;
  onAnalyze: (repo: Repository) => void;
  analyzing?: boolean;
}) {
  return (
    <article className="panel flex flex-col p-4 transition hover:border-ink-500">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-white">
            <span className="text-slate-500">{repo.owner}/</span>
            {repo.name}
          </h3>
          <p className="mt-1 line-clamp-2 h-8 text-xs leading-relaxed text-slate-400">
            {repo.description || "No description provided."}
          </p>
        </div>
        {repo.owner_avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={repo.owner_avatar}
            alt=""
            className="h-7 w-7 shrink-0 rounded-full border border-ink-600"
          />
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {repo.language ? (
          <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-400">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: languageColor(repo.language) }}
            />
            {repo.language}
          </span>
        ) : null}
        <span className="text-[11px] text-slate-500">★ {formatNumber(repo.stargazers_count)}</span>
        <span className="text-[11px] text-slate-500">Updated {formatRelative(repo.pushed_at || repo.updated_at)}</span>
        {repo.private ? <Badge tone="warn">Private</Badge> : null}
        {repo.archived ? <Badge tone="neutral">Archived</Badge> : null}
        {repo.fork ? <Badge tone="neutral">Fork</Badge> : null}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2 border-t border-ink-700 pt-3">
        <span className="truncate font-mono text-[11px] text-ink-500">
          {repo.default_branch}
        </span>
        <button
          type="button"
          className="focus-ring h-8 rounded-lg bg-accent px-3 text-xs font-semibold text-white transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => onAnalyze(repo)}
          disabled={analyzing}
        >
          {analyzing ? "Starting…" : "Analyze Repository"}
        </button>
      </div>
    </article>
  );
}
