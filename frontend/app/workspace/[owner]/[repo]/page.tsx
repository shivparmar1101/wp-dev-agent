"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { api, ApiError } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";
import type { FileNode, ProjectSummary, ScanStatus } from "@/lib/types";
import { RepoHeader } from "@/components/repository/repo-header";
import { ScanProgress } from "@/components/repository/scan-progress";
import { FileTree } from "@/components/repository/file-tree";
import { FileViewer } from "@/components/repository/file-viewer";
import { ChatPanel } from "@/components/chat/chat-panel";
import { SearchPanel } from "@/components/search/search-panel";
import { OverviewPanel } from "@/components/analysis/overview";
import { WordPressPanel } from "@/components/analysis/wordpress-panel";
import { ThemesPanel } from "@/components/analysis/themes-panel";
import { PluginsPanel } from "@/components/analysis/plugins-panel";
import { ElementorPanel } from "@/components/analysis/elementor-panel";
import { ErrorState, EmptyState } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/spinner";

type View =
  | "chat"
  | "overview"
  | "files"
  | "wordpress"
  | "themes"
  | "plugins"
  | "elementor"
  | "search";

const NAV: { id: View; label: string }[] = [
  { id: "chat", label: "AI Chat" },
  { id: "overview", label: "Project Overview" },
  { id: "files", label: "File Explorer" },
  { id: "wordpress", label: "WordPress" },
  { id: "themes", label: "Themes" },
  { id: "plugins", label: "Plugins" },
  { id: "elementor", label: "Elementor" },
  { id: "search", label: "Search" },
];

export default function WorkspacePage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = decodeURIComponent(params.owner);
  const repo = decodeURIComponent(params.repo);
  const { authorized, loading: authLoading } = useAuthGuard();

  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projectLoaded, setProjectLoaded] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [tree, setTree] = useState<FileNode | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [focusLine, setFocusLine] = useState<number | null>(null);

  const loadProject = useCallback(async () => {
    try {
      const data = await api.project(owner, repo);
      setProject(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setProject(null);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to load the project.");
      }
    } finally {
      setProjectLoaded(true);
    }
  }, [owner, repo]);

  const loadScan = useCallback(async () => {
    try {
      const status = await api.scanStatus(owner, repo);
      if (status.status === "pending" || status.status === "running") {
        setScan(status);
      } else if (status.status === "completed") {
        setScan(null);
        await loadProject();
      } else {
        setScan(status);
      }
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 404) {
        // Ignore: scan history may simply not exist yet.
      }
    }
  }, [owner, repo, loadProject]);

  const startScan = useCallback(async () => {
    setError(null);
    try {
      const status = await api.startScan(owner, repo);
      setScan(status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the scan.");
    }
  }, [owner, repo]);

  useEffect(() => {
    if (!authorized) return;
    void loadProject();
    void loadScan();
  }, [authorized, loadProject, loadScan]);

  // Poll scan status while a scan is active.
  const scanStatus = scan?.status ?? null;
  const scanId = scan?.scan_id;
  useEffect(() => {
    if (scanStatus !== "pending" && scanStatus !== "running") return;
    const interval = setInterval(async () => {
      try {
        const status = await api.scanStatus(owner, repo);
        setScan(status);
        if (status.status === "completed") {
          await loadProject();
        }
      } catch {
        /* keep polling */
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [scanStatus, scanId, owner, repo, loadProject]);

  const scanActive =
    scan !== null && (scan.status === "pending" || scan.status === "running");

  const openFile = useCallback((path: string, line?: number | null) => {
    setSelectedFile(path);
    setFocusLine(line ?? null);
    setView("files");
  }, []);

  const ensureTree = useCallback(async () => {
    if (tree || treeError) return;
    try {
      setTree(await api.tree(owner, repo));
    } catch (err) {
      setTreeError(err instanceof ApiError ? err.message : "Failed to load the file tree.");
    }
  }, [owner, repo, tree, treeError]);

  useEffect(() => {
    if (view === "files") void ensureTree();
  }, [view, ensureTree]);

  if (authLoading || !authorized) {
    return (
      <AppShell wide>
        <LoadingState label="Loading workspace…" />
      </AppShell>
    );
  }

  if (!projectLoaded && !error) {
    return (
      <AppShell wide>
        <LoadingState label={`Loading ${owner}/${repo}…`} />
      </AppShell>
    );
  }

  if (error && !project && !scan) {
    return (
      <AppShell wide>
        <ErrorState title="Could not open workspace" description={error} onRetry={() => void loadProject()} />
      </AppShell>
    );
  }

  // Repository was never analyzed.
  if (!project && !scan) {
    return (
      <AppShell wide>
        <div className="mx-auto max-w-xl">
          <EmptyState
            title={`${owner}/${repo} has not been analyzed`}
            description="Run a scan to detect WordPress, themes, plugins, and Elementor, and to index the code for search and AI answers."
            action={{ label: "Analyze Repository", onClick: () => void startScan() }}
          />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell wide>
      {project ? (
        <RepoHeader
          project={project}
          scanning={scanActive}
          onRescan={() => void startScan()}
        />
      ) : null}

      {scanActive ? (
        <div className="mx-auto max-w-3xl">
          <ScanProgress scan={scan!} />
        </div>
      ) : null}

      {scan && scan.status === "failed" && !project ? (
        <div className="mx-auto max-w-3xl">
          <ScanProgress scan={scan} onCancel={() => setScan(null)} />
        </div>
      ) : null}

      {project && !scanActive && scan?.status !== "failed" ? (
        <div className="grid gap-4 lg:grid-cols-[210px_minmax(0,1fr)]">
          <aside className="lg:sticky lg:top-20 lg:self-start">
            <nav className="panel flex flex-row gap-1 overflow-x-auto p-2 lg:flex-col">
              {NAV.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-active={view === item.id}
                  className="nav-item shrink-0"
                  onClick={() => setView(item.id)}
                >
                  {item.label}
                  {item.id === "themes" && project.themes.length ? (
                    <span className="ml-auto hidden text-[10px] text-ink-500 lg:inline">
                      {project.themes.length}
                    </span>
                  ) : null}
                  {item.id === "plugins" && project.plugins.length ? (
                    <span className="ml-auto hidden text-[10px] text-ink-500 lg:inline">
                      {project.plugins.length}
                    </span>
                  ) : null}
                </button>
              ))}
            </nav>
            <div className="panel mt-3 hidden p-3 lg:block">
              <div className="text-[10px] uppercase tracking-wide text-ink-500">Index</div>
              <div className="mt-1 text-xs text-slate-300">
                {project.index?.files_indexed ?? 0} files · {project.index?.chunks ?? 0} chunks
              </div>
              <div className="mt-1 text-[11px] text-ink-500">
                {project.index?.embeddings_enabled
                  ? "Embeddings enabled"
                  : "Lexical search only"}
              </div>
            </div>
          </aside>

          <section className="min-w-0">
            {view === "chat" ? (
              <div className="panel flex h-[calc(100vh-11rem)] min-h-96 flex-col overflow-hidden">
                <ChatPanel owner={owner} repo={repo} onOpenFile={openFile} />
              </div>
            ) : null}

            {view === "overview" ? <OverviewPanel project={project} /> : null}
            {view === "wordpress" ? <WordPressPanel project={project} /> : null}
            {view === "themes" ? <ThemesPanel themes={project.themes} /> : null}
            {view === "plugins" ? <PluginsPanel plugins={project.plugins} /> : null}
            {view === "elementor" ? <ElementorPanel elementor={project.elementor} /> : null}

            {view === "search" ? (
              <div className="panel h-[calc(100vh-11rem)] min-h-96 p-4">
                <SearchPanel owner={owner} repo={repo} onOpenFile={openFile} />
              </div>
            ) : null}

            {view === "files" ? (
              <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
                <div className="panel max-h-[calc(100vh-11rem)] min-h-64 overflow-y-auto p-2">
                  {treeError ? (
                    <div className="p-3">
                      <ErrorState description={treeError} onRetry={() => { setTreeError(null); void ensureTree(); }} />
                    </div>
                  ) : tree ? (
                    <ul>
                      <FileTree node={tree} selected={selectedFile} onSelect={(path) => { setSelectedFile(path); setFocusLine(null); }} />
                    </ul>
                  ) : (
                    <div className="flex items-center justify-center gap-2 p-6 text-xs text-ink-500">
                      Loading files…
                    </div>
                  )}
                </div>
                <div className="min-h-[calc(100vh-11rem)]">
                  <FileViewer
                    owner={owner}
                    repo={repo}
                    path={selectedFile}
                    focusLine={focusLine}
                    onClose={() => setSelectedFile(null)}
                  />
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}
