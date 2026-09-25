"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { themeTypeLabel } from "@/lib/format";
import type { ThemeInfo } from "@/lib/types";

export function ThemesPanel({ themes }: { themes: ThemeInfo[] }) {
  if (!themes.length) {
    return (
      <Card>
        <CardHeader title="Themes" />
        <p className="text-xs text-slate-500">No themes were detected in this repository.</p>
      </Card>
    );
  }

  return (
    <div className="animate-fade-up grid gap-4 lg:grid-cols-2">
      {themes.map((theme) => {
        const tone =
          theme.theme_type === "child"
            ? "accent"
            : theme.theme_type === "custom"
              ? "ok"
              : "neutral";
        return (
          <Card key={`${theme.slug}-${theme.location}`}>
            <CardHeader
              title={
                <span className="flex items-center gap-2">
                  {theme.name}
                  <Badge tone={tone}>{themeTypeLabel(theme.theme_type)}</Badge>
                  {theme.block_theme ? <Badge tone="accent">Block theme</Badge> : null}
                </span>
              }
              subtitle={
                <span className="font-mono text-[11px]">{theme.location}</span>
              }
              action={
                theme.version ? <Badge tone="neutral">v{theme.version}</Badge> : null
              }
            />
            {theme.description ? (
              <p className="mb-3 text-xs leading-relaxed text-slate-400">
                {theme.description}
              </p>
            ) : null}
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
              <Meta label="Author" value={theme.author} />
              <Meta label="Slug" value={theme.slug} mono />
              <Meta label="Text domain" value={theme.text_domain} mono />
              <Meta label="Parent" value={theme.parent_theme} mono />
              <Meta
                label="functions.php"
                value={theme.has_functions_php ? "present" : "absent"}
              />
            </dl>
          </Card>
        );
      })}
    </div>
  );
}

export function Meta({
  label,
  value,
  mono,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className={`truncate text-slate-300 ${mono ? "font-mono text-[11px]" : ""}`}>
        {value || "—"}
      </dd>
    </div>
  );
}
