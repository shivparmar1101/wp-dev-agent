"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fileLanguageOf, formatNumber } from "@/lib/format";
import type { FileContent } from "@/lib/types";
import { CodeBlock } from "@/components/code/code-block";
import { ErrorState } from "@/components/ui/feedback";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";

export function FileViewer({
  owner,
  repo,
  path,
  onClose,
  focusLine,
}: {
  owner: string;
  repo: string;
  path: string | null;
  onClose?: () => void;
  focusLine?: number | null;
}) {
  const [file, setFile] = useState<FileContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.file(owner, repo, path);
      setFile(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load file.");
      setFile(null);
    } finally {
      setLoading(false);
    }
  }, [owner, repo, path]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!path) {
    return (
      <div className="panel flex h-full min-h-40 items-center justify-center px-6 py-10 text-center text-xs text-ink-500">
        Select a file to preview it here.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-40 flex-col">
      <div className="flex items-center justify-between gap-3 rounded-t-xl border border-ink-700 border-b-0 bg-ink-850 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs text-slate-300">{path}</span>
          {file ? (
            <>
              <Badge tone="neutral">{file.language || "text"}</Badge>
              <span className="shrink-0 text-[11px] text-ink-500">
                {formatNumber(file.size)} B
              </span>
            </>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {file?.redacted ? (
            <Badge tone="warn" title="Sensitive values were masked before display">
              redacted
            </Badge>
          ) : null}
          <button
            type="button"
            onClick={load}
            className="focus-ring rounded p-1 text-ink-500 hover:text-slate-200"
            title="Reload file"
          >
            ⟳
          </button>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="focus-ring rounded p-1 text-ink-500 hover:text-slate-200"
              title="Close file"
            >
              ✕
            </button>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-b-xl border border-ink-700 bg-[#0a0e15]">
        {loading ? (
          <div className="flex h-40 items-center justify-center gap-2 text-xs text-slate-500">
            <Spinner /> Loading file…
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState title="Could not load file" description={error} onRetry={load} />
          </div>
        ) : file ? (
          file.truncated ? (
            <div className="max-h-full overflow-auto">
              <div className="border-b border-warn/30 bg-warn/10 px-3 py-1.5 text-[11px] text-warn">
                File truncated for display.
              </div>
              <CodeBlock
                code={file.content}
                language={fileLanguageOf(file.path, file.language)}
                highlightLines={{ start: focusLine ?? null }}
                maxHeight="none"
              />
            </div>
          ) : (
            <div className="max-h-full overflow-auto">
              <CodeBlock
                code={file.content}
                language={fileLanguageOf(file.path, file.language)}
                filename={file.path}
                highlightLines={{ start: focusLine ?? null }}
                maxHeight="none"
              />
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}
