"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ProjectSummary } from "@/lib/types";

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.7 ? "bg-ok" : value >= 0.4 ? "bg-warn" : "bg-danger";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-400">Confidence</span>
        <span className="font-mono text-slate-200">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function WordPressPanel({ project }: { project: ProjectSummary }) {
  return (
    <div className="animate-fade-up space-y-4">
      <Card>
        <CardHeader
          title="WordPress detection"
          subtitle={
            project.is_wordpress
              ? "This repository is treated as a WordPress project."
              : "No conclusive WordPress installation was detected."
          }
          action={
            <Badge tone={project.is_wordpress ? "ok" : "neutral"}>
              {project.is_wordpress ? "WordPress" : "Not WordPress"}
            </Badge>
          }
        />
        <ConfidenceBar value={project.wordpress_confidence} />
      </Card>

      <Card>
        <CardHeader title="Indicators" subtitle="Signals that contributed to detection." />
        {project.wordpress_indicators.length ? (
          <ul className="space-y-1.5">
            {project.wordpress_indicators.map((indicator) => (
              <li key={indicator} className="flex gap-2 text-xs text-slate-300">
                <span className="text-ok">✓</span>
                <span>{indicator}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500">No WordPress indicators found.</p>
        )}
      </Card>
    </div>
  );
}
