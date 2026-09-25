"use client";

import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";
import { Input, Select } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState, EmptyState } from "@/components/ui/feedback";
import { Spinner } from "@/components/ui/spinner";

const MODES = [
  { value: "hybrid", label: "Hybrid (recommended)" },
  { value: "keyword", label: "Keyword (BM25)" },
  { value: "exact", label: "Exact phrase" },
  { value: "file", label: "File path" },
  { value: "semantic", label: "Semantic" },
] as const;

export function SearchPanel({
  owner,
  repo,
  onOpenFile,
}: {
  owner: string;
  repo: string;
  onOpenFile?: (path: string, line?: number | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<string>("hybrid");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.search(owner, repo, trimmed, mode, 15);
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="animate-fade-up flex h-full min-h-0 flex-col gap-4">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div className="min-w-56 flex-1">
          <Input
            label="Search the repository"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="sticky header, elementor_enqueue_styles, wp_enqueue_script…"
          />
        </div>
        <div className="w-48">
          <Select label="Mode" value={mode} onChange={(event) => setMode(event.target.value)}>
            {MODES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" variant="primary" disabled={loading || !query.trim()}>
          {loading ? <Spinner /> : null} Search
        </Button>
      </form>

      {error ? <ErrorState description={error} onRetry={() => setError(null)} /> : null}

      {result ? (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>
              {result.total} result{result.total === 1 ? "" : "s"} in {result.took_ms} ms
            </span>
            <Badge tone="neutral">{result.mode_used}</Badge>
            {result.index ? <Badge tone="neutral">{result.index.chunks} chunks</Badge> : null}
          </div>
          {result.notes.length ? (
            <ul className="space-y-1 text-[11px] text-warn/90">
              {result.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          ) : null}

          {result.hits.length ? (
            <ul className="space-y-2">
              {result.hits.map((hit, index) => (
                <li key={`${hit.file_path}-${hit.start_line ?? index}`}>
                  <button
                    type="button"
                    className="focus-ring panel w-full px-3 py-2.5 text-left transition hover:border-ink-500"
                    onClick={() => onOpenFile?.(hit.file_path, hit.start_line)}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="truncate font-mono text-xs text-accent-soft">
                        {hit.file_path}
                        {hit.start_line ? `:${hit.start_line}` : ""}
                      </span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        <Badge tone="neutral">{hit.match_type}</Badge>
                        <span className="font-mono text-[11px] text-ink-500">
                          {hit.score.toFixed(2)}
                        </span>
                      </span>
                    </div>
                    <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-400">
                      {hit.snippet}
                    </pre>
                    {hit.matched_terms.length ? (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {hit.matched_terms.slice(0, 6).map((term) => (
                          <span
                            key={term}
                            className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent-soft"
                          >
                            {term}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No matches"
              description="Try a different query or switch the search mode."
            />
          )}
        </div>
      ) : !error ? (
        <EmptyState
          title="Search the indexed code"
          description="Run a query to find functions, classes, hooks, templates, and Elementor widgets across the repository."
        />
      ) : null}
    </div>
  );
}
