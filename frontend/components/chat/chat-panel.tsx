"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, ApiError } from "@/lib/api";
import type { AnalysisResponse, ChatMessageDto } from "@/lib/types";
import { AnalysisCard } from "./analysis-card";
import { ErrorState } from "@/components/ui/feedback";
import { Spinner } from "@/components/ui/spinner";

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  analysis?: AnalysisResponse;
}

const HISTORY_LIMIT = 8;

export function ChatPanel({
  owner,
  repo,
  onOpenFile,
}: {
  owner: string;
  repo: string;
  onOpenFile?: (path: string, line?: number | null) => void;
}) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationId = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries.length, thinking]);

  const send = useCallback(async () => {
    const message = input.trim();
    if (!message || thinking) return;

    setError(null);
    setInput("");
    setEntries((prev) => [...prev, { role: "user", content: message }]);
    setThinking(true);

    const history: ChatMessageDto[] = entries.slice(-HISTORY_LIMIT).map((entry) => ({
      role: entry.role,
      content: entry.content,
    }));

    try {
      const response = await api.chat(owner, repo, message, history, conversationId.current);
      conversationId.current = response.conversation_id ?? conversationId.current;
      const analysis = response.analysis;
      setEntries((prev) => [
        ...prev,
        {
          role: "assistant",
          content: analysis.suggested_solution || analysis.explanation || analysis.issue,
          analysis,
        },
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The agent could not answer.");
      // Drop the optimistic user message and restore it to the input for retry.
      setEntries((prev) => prev.slice(0, -1));
      setInput(message);
    } finally {
      setThinking(false);
    }
  }, [entries, input, owner, repo, thinking]);

  const empty = entries.length === 0 && !thinking;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {empty ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
            <div className="text-3xl text-accent" aria-hidden>
              ✦
            </div>
            <h3 className="text-sm font-semibold text-white">Ask about this repository</h3>
            <p className="max-w-md text-xs leading-relaxed text-slate-400">
              The agent searches the indexed code, then answers with analysis, relevant
              files, and a suggested fix. Try: &ldquo;Why is the header not sticky on the
              blog page?&rdquo;
            </p>
          </div>
        ) : (
          <div className="space-y-4 px-4 py-4">
            {entries.map((entry, index) => (
              <div
                key={index}
                className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {entry.role === "user" ? (
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent/15 px-4 py-2.5 text-sm leading-relaxed text-slate-100">
                    <span className="whitespace-pre-wrap break-words">{entry.content}</span>
                  </div>
                ) : entry.analysis ? (
                  <AnalysisCard analysis={entry.analysis} onOpenFile={onOpenFile} />
                ) : (
                  <div className="markdown max-w-[92%] rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3 text-sm text-slate-200">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
            {thinking ? (
              <div className="flex justify-start">
                <div className="flex items-center gap-2.5 rounded-2xl rounded-bl-md border border-ink-700 bg-ink-850 px-4 py-3 text-xs text-slate-400">
                  <Spinner />
                  Searching the repository and preparing an answer…
                </div>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {error ? (
        <div className="px-4 pb-2">
          <ErrorState title="Could not reach the agent" description={error} onRetry={() => setError(null)} />
        </div>
      ) : null}

      <form
        className="border-t border-ink-700 bg-ink-900/70 p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <div className="flex items-end gap-2">
          <label htmlFor="chat-input" className="sr-only">
            Ask a question about this repository
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Ask about this repository… (Enter to send, Shift+Enter for newline)"
            className="focus-ring max-h-40 min-h-[44px] flex-1 resize-y rounded-lg border border-ink-600 bg-ink-950 px-3 py-2.5 text-sm text-slate-100 placeholder:text-ink-500"
          />
          <button
            type="submit"
            disabled={thinking || !input.trim()}
            className="focus-ring inline-flex h-11 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-semibold text-white transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            {thinking ? <Spinner /> : null}
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
