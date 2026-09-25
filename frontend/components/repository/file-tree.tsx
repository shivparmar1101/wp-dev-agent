"use client";

import { useMemo, useState } from "react";
import type { FileNode } from "@/lib/types";

export function FileTree({
  node,
  selected,
  onSelect,
  depth = 0,
}: {
  node: FileNode;
  selected?: string | null;
  onSelect?: (path: string) => void;
  depth?: number;
}) {
  const isDir = node.type === "dir";
  const [open, setOpen] = useState(depth < 1);

  const icon = useMemo(() => {
    if (isDir) return open ? "▾" : "▸";
    const ext = node.path.split(".").pop()?.toLowerCase();
    switch (ext) {
      case "php":
        return "λ";
      case "css":
      case "scss":
      case "sass":
        return "#";
      case "js":
      case "jsx":
      case "ts":
      case "tsx":
        return "JS";
      case "json":
        return "{}";
      case "md":
        return "M";
      default:
        return "·";
    }
  }, [isDir, open, node.path]);

  const active = selected === node.path;

  return (
    <li>
      <button
        type="button"
        className={`focus-ring flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs transition ${
          active ? "bg-accent/15 text-accent-soft" : "text-slate-300 hover:bg-ink-800"
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => {
          if (isDir) setOpen((v) => !v);
          else onSelect?.(node.path);
        }}
        aria-expanded={isDir ? open : undefined}
      >
        <span
          className={`w-4 shrink-0 text-center font-mono text-[10px] ${
            isDir ? "text-ink-500" : node.wordpress ? "text-accent" : "text-ink-500"
          }`}
          aria-hidden
        >
          {icon}
        </span>
        <span className={`truncate ${isDir ? "font-medium" : ""}`}>{node.name}</span>
        {node.wordpress && !isDir ? (
          <span className="ml-auto shrink-0 text-[9px] uppercase tracking-wide text-accent/70">
            wp
          </span>
        ) : null}
      </button>
      {isDir && open && node.children?.length ? (
        <ul>
          {node.children.map((child) => (
            <FileTree
              key={child.path}
              node={child}
              depth={depth + 1}
              selected={selected}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
