"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { statusLabel } from "@/lib/format";
import type { DetectionStatus, ElementorDetection } from "@/lib/types";

const statusTone: Record<DetectionStatus, BadgeTone> = {
  detected: "ok",
  not_detected: "neutral",
  unknown: "warn",
};

export function ElementorPanel({ elementor }: { elementor: ElementorDetection }) {
  const signals = Object.entries(elementor.signals).sort((a, b) => b[1] - a[1]);
  const pct = Math.round(elementor.confidence * 100);

  return (
    <div className="animate-fade-up space-y-4">
      <Card>
        <CardHeader
          title="Elementor detection"
          subtitle="Based on plugin directories, markup, and CSS class signals."
          action={
            <div className="flex gap-2">
              <Badge tone={statusTone[elementor.elementor]}>
                Elementor: {statusLabel(elementor.elementor)}
              </Badge>
              <Badge tone={statusTone[elementor.elementor_pro]}>
                Pro: {statusLabel(elementor.elementor_pro)}
              </Badge>
            </div>
          }
        />
        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-slate-400">Confidence</span>
            <span className="font-mono text-slate-200">{pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
            <div
              className={`h-full rounded-full ${
                pct >= 70 ? "bg-ok" : pct >= 35 ? "bg-warn" : "bg-danger"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        {elementor.evidence.length ? (
          <ul className="space-y-1.5">
            {elementor.evidence.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-slate-300">
                <span className="text-accent">›</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500">No Elementor evidence found.</p>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Indicators" subtitle="Paths and strings matched." />
          {elementor.indicators.length ? (
            <div className="flex flex-wrap gap-2">
              {elementor.indicators.map((indicator) => (
                <Badge key={indicator} tone="accent">
                  {indicator}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">No indicators found.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Signals" subtitle="Weighted signal contributions." />
          {signals.length ? (
            <ul className="space-y-1.5">
              {signals.map(([signal, value]) => (
                <li key={signal} className="flex items-center gap-2 text-xs">
                  <span className="w-40 truncate font-mono text-[11px] text-slate-400">
                    {signal}
                  </span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-800">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.min(100, value * 100)}%` }}
                    />
                  </div>
                  <span className="w-8 text-right font-mono text-[11px] text-slate-300">
                    {value.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-500">No signals recorded.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
