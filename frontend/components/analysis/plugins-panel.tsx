"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PluginInfo } from "@/lib/types";
import { Meta } from "./themes-panel";

export function PluginsPanel({ plugins }: { plugins: PluginInfo[] }) {
  if (!plugins.length) {
    return (
      <Card>
        <CardHeader title="Plugins" />
        <p className="text-xs text-slate-500">No plugins were detected in this repository.</p>
      </Card>
    );
  }

  return (
    <div className="animate-fade-up grid gap-4 lg:grid-cols-2">
      {plugins.map((plugin) => (
        <Card key={`${plugin.slug}-${plugin.location}`}>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                {plugin.name}
                {plugin.known ? <Badge tone="ok">known plugin</Badge> : null}
              </span>
            }
            subtitle={<span className="font-mono text-[11px]">{plugin.location}</span>}
            action={
              plugin.version ? <Badge tone="neutral">v{plugin.version}</Badge> : null
            }
          />
          {plugin.description ? (
            <p className="mb-3 text-xs leading-relaxed text-slate-400">
              {plugin.description}
            </p>
          ) : null}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            <Meta label="Author" value={plugin.author} />
            <Meta label="Slug" value={plugin.slug} mono />
            <Meta label="Text domain" value={plugin.text_domain} mono />
            <Meta label="Main file" value={plugin.main_file} mono />
            <Meta label="Metadata source" value={plugin.metadata_source} />
          </dl>
        </Card>
      ))}
    </div>
  );
}
