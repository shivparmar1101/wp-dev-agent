"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { api, ApiError } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";
import type { ProjectSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/spinner";
import { formatRelative, formatNumber } from "@/lib/format";

export default function DashboardPage() {
  const { authorized, loading, user, health } = useAuthGuard();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authorized) return;
    let cancelled = false;
    api
      .projects()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load projects.");
      });
    return () => {
      cancelled = true;
    };
  }, [authorized]);

  if (loading || !authorized) {
    return (
      <AppShell>
        <LoadingState label="Loading dashboard…" />
      </AppShell>
    );
  }

  const wpCount = projects?.filter((p) => p.is_wordpress).length ?? 0;
  const elementorCount =
    projects?.filter((p) => p.elementor.elementor === "detected").length ?? 0;
  const filesIndexed = projects?.reduce((sum, p) => sum + (p.index?.files_indexed ?? 0), 0) ?? 0;

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-white">
          Welcome back{user?.name || user?.login ? `, ${user.name || user.login}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Analyze WordPress and Elementor repositories with grounded, read-only AI answers.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Repositories analyzed" value={formatNumber(projects?.length ?? 0)} />
        <Stat label="WordPress projects" value={formatNumber(wpCount)} tone="ok" />
        <Stat label="Elementor projects" value={formatNumber(elementorCount)} tone="accent" />
        <Stat label="Files indexed" value={formatNumber(filesIndexed)} />
      </div>

      {health && !health.ai_configured ? (
        <div className="mb-6 rounded-xl border border-warn/40 bg-warn/5 px-4 py-3 text-xs leading-relaxed text-warn">
          No AI provider is configured, so answers will be limited to the offline mock
          provider. Set <code className="font-mono">AI_PROVIDER</code> and an API key in{" "}
          <code className="font-mono">.env</code> to enable real analysis.
        </div>
      ) : null}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Recently analyzed</h2>
        <Link
          href="/repositories"
          className="focus-ring rounded-lg px-2 py-1 text-xs font-medium text-accent-soft hover:underline"
        >
          Analyze a repository →
        </Link>
      </div>

      {error ? (
        <ErrorState description={error} />
      ) : projects === null ? (
        <LoadingState label="Loading projects…" />
      ) : projects.length === 0 ? (
        <div className="panel px-6 py-10 text-center">
          <h3 className="text-sm font-semibold text-white">No repositories analyzed yet</h3>
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-slate-400">
            Connect a repository to scan it for WordPress, themes, plugins, and Elementor,
            then ask the agent about its code.
          </p>
          <Link
            href="/repositories"
            className="focus-ring mt-4 inline-flex h-9 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-soft"
          >
            Browse repositories
          </Link>
        </div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {projects.slice(0, 8).map((project) => (
            <li key={`${project.owner}/${project.repo}`}>
              <Link
                href={`/workspace/${project.owner}/${project.repo}`}
                className="panel block px-4 py-3.5 transition hover:border-ink-500"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm font-semibold text-white">
                    <span className="text-slate-500">{project.owner}/</span>
                    {project.repo}
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-500">
                    {formatRelative(project.scanned_at)}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {project.is_wordpress ? <Badge tone="ok">WordPress</Badge> : null}
                  {project.elementor.elementor === "detected" ? (
                    <Badge tone="accent">Elementor</Badge>
                  ) : null}
                  <Badge tone="neutral">{project.branch}</Badge>
                  <Badge tone="neutral">{formatNumber(project.total_files)} files</Badge>
                  {project.themes.map((theme) => (
                    <Badge key={theme.slug} tone="neutral">
                      {theme.name}
                    </Badge>
                  ))}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "accent";
}) {
  return (
    <div className="panel px-4 py-3.5">
      <div
        className={`text-2xl font-semibold ${
          tone === "ok" ? "text-ok" : tone === "accent" ? "text-accent-soft" : "text-white"
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-ink-500">{label}</div>
    </div>
  );
}
