import type { DetectionStatus, StageStatus } from "./types";

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatRelative(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function formatNumber(value?: number | null): string {
  if (value === undefined || value === null) return "0";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function statusLabel(status: DetectionStatus): string {
  if (status === "detected") return "Detected";
  if (status === "not_detected") return "Not Detected";
  return "Unknown";
}

export function themeTypeLabel(type: string): string {
  switch (type) {
    case "child":
      return "Child Theme";
    case "custom":
      return "Custom Theme";
    case "known":
      return "Installed Theme";
    case "parent":
      return "Parent Theme";
    default:
      return "Unknown";
  }
}

export function languageColor(language?: string | null): string {
  const key = (language || "").toLowerCase();
  const map: Record<string, string> = {
    php: "#8892bf",
    css: "#519aba",
    scss: "#cd6799",
    sass: "#cd6799",
    less: "#519aba",
    javascript: "#f1e05a",
    typescript: "#3178c6",
    jsx: "#61dafb",
    tsx: "#3178c6",
    html: "#e34c26",
    json: "#cbcb41",
    yaml: "#cb171e",
    markdown: "#083fa1",
    python: "#3572a5",
    text: "#8b949e",
  };
  return map[key] || "#8b949e";
}

export function stageDone(stage: StageStatus): boolean {
  return stage.status === "done" || stage.status === "skipped";
}

export function parseErrorParams(params: URLSearchParams): string | null {
  const code = params.get("error");
  if (!code) return null;
  const map: Record<string, string> = {
    github_denied: "GitHub authorization was declined. Please try again.",
    missing_code: "GitHub did not return an authorization code.",
    invalid_state: "The sign-in attempt could not be verified. Please try again.",
    exchange_failed: "GitHub could not complete the sign-in. Please try again.",
    user_lookup_failed: "Could not load your GitHub profile. Please try again.",
  };
  return map[code] || "Sign-in failed. Please try again.";
}

export function fileLanguageOf(path: string, language?: string | null): string | null {
  if (language && language !== "text" && language !== "binary") return language;
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    php: "php",
    css: "css",
    scss: "scss",
    js: "javascript",
    jsx: "jsx",
    ts: "typescript",
    tsx: "tsx",
    html: "markup",
    htm: "markup",
    json: "json",
    yml: "yaml",
    yaml: "yaml",
    md: "markdown",
    markdown: "markdown",
    sh: "bash",
    bash: "bash",
    xml: "markup",
  };
  return map[ext] || null;
}
