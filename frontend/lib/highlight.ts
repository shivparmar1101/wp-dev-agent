"use client";

import Prism from "prismjs";
import "prismjs/components/prism-markup-templating";
import "prismjs/components/prism-json";
import "prismjs/components/prism-php";
import "prismjs/components/prism-scss";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-sql";

const ALIASES: Record<string, string> = {
  javascript: "javascript",
  js: "javascript",
  typescript: "typescript",
  ts: "typescript",
  tsx: "tsx",
  jsx: "jsx",
  html: "markup",
  htm: "markup",
  xml: "markup",
  svg: "markup",
  vue: "markup",
  php: "php",
  css: "css",
  scss: "scss",
  sass: "scss",
  less: "css",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  markdown: "markdown",
  md: "markdown",
  bash: "bash",
  shell: "bash",
  sh: "bash",
  sql: "sql",
  txt: "text",
};

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export interface HighlightResult {
  html: string;
  language: string;
}

/** Returns highlighted HTML for `code`, falling back to escaped plain text. */
export function highlight(code: string, language?: string | null): HighlightResult {
  const normalized = (language || "").toLowerCase();
  const key = ALIASES[normalized];
  if (!key) {
    return { html: escapeHtml(code), language: "text" };
  }
  const grammar = Prism.languages[key];
  if (!grammar) {
    return { html: escapeHtml(code), language: "text" };
  }
  try {
    return { html: Prism.highlight(code, grammar, key), language: key };
  } catch {
    return { html: escapeHtml(code), language: "text" };
  }
}
