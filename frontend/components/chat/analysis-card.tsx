"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/code/code-block";
import { fileLanguageOf } from "@/lib/format";
import type { AnalysisResponse, ChatMessageDto } from "@/lib/types";

const confidenceTone = {
  High: "ok",
  Medium: "warn",
  Low: "danger",
  Unknown: "neutral",
} as const;

export function ChatTranscript({
  messages,
  thinking,
}: {
  messages: ChatMessageDto[];
  thinking?: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, thinking]);

  if (!messages.length && !thinking) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <div className="text-3xl" aria-hidden>
          ✦
        </div>
        <h3 className="text-sm font-semibold text-white">Ask about this repository</h3>
        <p className="max-w-md text-xs leading-relaxed text-slate-400">
          The agent searches the indexed code, then answers with analysis, relevant
          files, and a suggested fix. Try: &ldquo;Why is the header not sticky on the
          blog page?&rdquo;
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
        >
          {message.role === "user" ? (
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent/15 px-4 py-2.5 text-sm leading-relaxed text-slate-100">
              <span className="whitespace-pre-wrap break-words">{message.content}</span>
            </div>
          ) : (
            <AnalysisCard raw={message.content} />
          )}
        </div>
      ))}
      {thinking ? (
        <div className="flex justify-start">
          <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3 text-xs text-slate-400">
            <span className="flex gap-1" aria-hidden>
              <span className="h-1.5 w-1.5 animate-blink rounded-full bg-accent" />
              <span
                className="h-1.5 w-1.5 animate-blink rounded-full bg-accent"
                style={{ animationDelay: "0.2s" }}
              />
              <span
                className="h-1.5 w-1.5 animate-blink rounded-full bg-accent"
                style={{ animationDelay: "0.4s" }}
              />
            </span>
            Searching the repository and preparing an answer…
          </div>
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  );
}

export function AnalysisCard({
  analysis,
  raw,
  onOpenFile,
}: {
  analysis?: AnalysisResponse;
  raw?: string;
  onOpenFile?: (path: string, line?: number | null) => void;
}) {
  // Assistant messages are stored as raw markdown when no structured analysis exists.
  if (!analysis) {
    return (
      <div className="markdown max-w-[92%] rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3 text-sm text-slate-200">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{raw || ""}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="max-w-[96%] space-y-3 rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold leading-snug text-white">
          {analysis.issue || "Analysis"}
        </h4>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone={confidenceTone[analysis.confidence] || "neutral"}>
            {analysis.confidence} confidence
          </Badge>
        </div>
      </div>

      <div className="text-xs leading-relaxed text-slate-400">
        <span className="font-medium text-slate-300">Cause: </span>
        {analysis.cause}
      </div>

      <div>
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-500">
          Relevant files
        </div>
        <div className="space-y-2">
          {analysis.relevant_files.length ? (
            analysis.relevant_files.map((ref, index) => (
              <div key={`${ref.file_path}-${index}`} className="panel-subtle overflow-hidden">
                <div className="flex items-center justify-between gap-2 border-b border-ink-700 bg-ink-850 px-2.5 py-1.5">
                  <button
                    type="button"
                    className="focus-ring truncate font-mono text-[11px] text-accent-soft hover:underline"
                    onClick={() => onOpenFile?.(ref.file_path, ref.start_line)}
                    title={ref.file_path}
                  >
                    {ref.file_path}
                    {ref.start_line ? `:${ref.start_line}` : ""}
                  </button>
                  <span className="shrink-0 text-[10px] text-ink-500">
                    {ref.start_line && ref.end_line
                      ? `lines ${ref.start_line}–${ref.end_line}`
                      : ref.start_line
                        ? `line ${ref.start_line}`
                        : ""}
                  </span>
                </div>
                {ref.snippet ? (
                  <div className="max-h-52 overflow-auto">
                    <CodeBlock
                      code={ref.snippet}
                      language={ref.language || fileLanguageOf(ref.file_path)}
                      highlightLines={{ start: ref.start_line ?? null, end: ref.end_line ?? null }}
                      maxHeight="13rem"
                    />
                  </div>
                ) : null}
                {ref.note ? (
                  <div className="px-2.5 py-1.5 text-[11px] text-slate-500">{ref.note}</div>
                ) : null}
              </div>
            ))
          ) : (
            <p className="text-[11px] text-slate-500">No specific files were referenced.</p>
          )}
        </div>
      </div>

      <div>
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-500">
          Suggested solution
        </div>
        <div className="markdown rounded-lg border border-ink-700 bg-ink-900 px-3.5 py-2.5 text-sm text-slate-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {analysis.suggested_solution || analysis.explanation || "—"}
          </ReactMarkdown>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ink-700 pt-2.5 text-[10px] text-ink-500">
        <span>mode: {analysis.mode_used}</span>
        <span>searches: {analysis.search_terms.slice(0, 4).join(", ") || "—"}</span>
        <span>files consulted: {analysis.files_consulted.length}</span>
        <span>provider: {analysis.provider}</span>
      </div>

      {analysis.warnings.length ? (
        <ul className="space-y-1 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
          {analysis.warnings.map((warning) => (
            <li key={warning} className="text-[11px] leading-relaxed text-warn">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
