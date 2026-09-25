"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import type { ProjectSummary } from "@/lib/types";

export function OverviewPanel({ project }: { project: ProjectSummary }) {
  const stats: { label: string; value: string; hint?: string }[] = [
    { label: "Files scanned", value: formatNumber(project.total_files) },
    { label: "Source files", value: formatNumber(project.source_files) },
    { label: "Indexed files", value: formatNumber(project.index?.files_indexed ?? 0) },
    { label: "Code chunks", value: formatNumber(project.index?.chunks ?? 0) },
    { label: "Languages", value: String(project.languages.length) },
    {
      label: "WP confidence",
      value: `${Math.round(project.wordpress_confidence * 100)}%`,
    },
  ];

  const fileEntries = Object.entries(project.file_counts)
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="animate-fade-up space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {stats.map((stat) => (
          <div key={stat.label} className="panel px-3 py-3">
            <div className="text-lg font-semibold text-white">{stat.value}</div>
            <div className="mt-0.5 text-[11px] uppercase tracking-wide text-ink-500">
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      <Card>
        <CardHeader
          title="Project types"
          subtitle="How the repository was classified."
        />
        <div className="flex flex-wrap gap-2">
          {project.project_types.length ? (
            project.project_types.map((type) => (
              <Badge key={type} tone="accent">
                {type}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-slate-500">No project type detected.</span>
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="File categories" subtitle="Detected by extension and path." />
          <ul className="space-y-1.5">
            {fileEntries.length ? (
              fileEntries.map(([category, count]) => (
                <li key={category} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{category}</span>
                  <span className="font-mono text-slate-200">{formatNumber(count)}</span>
                </li>
              ))
            ) : (
              <li className="text-xs text-slate-500">No file counts available.</li>
            )}
          </ul>
        </Card>

        <Card>
          <CardHeader title="Technology signals" subtitle="Feature flags found during the scan." />
          <div className="flex flex-wrap gap-2">
            {Object.entries(project.tech)
              .filter(([, on]) => on)
              .map(([key]) => (
                <Badge key={key} tone="ok">
                  {key}
                </Badge>
              ))}
            {Object.values(project.tech).every((v) => !v) ? (
              <span className="text-xs text-slate-500">No technology signals detected.</span>
            ) : null}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Scan notes" />
        {project.notes.length ? (
          <ul className="space-y-1.5">
            {project.notes.map((note) => (
              <li key={note} className="flex gap-2 text-xs text-slate-400">
                <span className="text-ink-500">•</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500">No notes.</p>
        )}
      </Card>
    </div>
  );
}
