"use client";

import { useMemo } from "react";
import { highlight } from "@/lib/highlight";

export function CodeBlock({
  code,
  language,
  filename,
  maxHeight = "22rem",
  highlightLines,
}: {
  code: string;
  language?: string | null;
  filename?: string;
  maxHeight?: string;
  highlightLines?: { start?: number | null; end?: number | null };
}) {
  const { html, language: lang } = useMemo(
    () => highlight(code, language),
    [code, language],
  );

  const startLine = highlightLines?.start ?? null;
  const endLine = highlightLines?.end ?? startLine;

  const lines = useMemo(() => {
    const parts = html.split("\n");
    // Trailing newline produces an empty final part; keep it only if real content.
    if (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
    return parts;
  }, [html]);

  const showLineNumbers = startLine !== null || lines.length > 1;

  return (
    <div className="code-block panel-subtle overflow-hidden">
      {filename ? (
        <div className="flex items-center justify-between border-b border-ink-700 bg-ink-850 px-3 py-1.5">
          <span className="truncate font-mono text-[11px] text-slate-400">{filename}</span>
          <span className="ml-3 shrink-0 rounded border border-ink-600 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-500">
            {lang}
          </span>
        </div>
      ) : null}
      <div className="overflow-auto" style={{ maxHeight }}>
        <pre className={`language-${lang}`}>
          <code className={`language-${lang}`}>
            {showLineNumbers
              ? lines.map((line, index) => {
                  const lineNumber = index + 1;
                  const isHighlighted =
                    startLine !== null &&
                    endLine !== null &&
                    lineNumber >= startLine &&
                    lineNumber <= endLine;
                  return (
                    <span key={index} className="block">
                      <span
                        aria-hidden
                        className={`mr-4 inline-block w-9 select-none text-right text-ink-500 ${
                          isHighlighted ? "text-warn" : ""
                        }`}
                      >
                        {lineNumber}
                      </span>
                      <span
                        className={
                          isHighlighted
                            ? "-mx-1 rounded bg-warn/10 px-1"
                            : undefined
                        }
                        dangerouslySetInnerHTML={{ __html: line || " " }}
                      />
                    </span>
                  );
                })
              : null}
          </code>
        </pre>
      </div>
    </div>
  );
}
