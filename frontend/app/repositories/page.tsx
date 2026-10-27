"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { api, ApiError } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";
import type { Repository } from "@/lib/types";
import { RepoCard } from "@/components/github/repo-card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ErrorState, EmptyState } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/spinner";

export default function RepositoriesPage() {
  const { authorized, loading } = useAuthGuard();
  const router = useRouter();

  const [repositories, setRepositories] = useState<Repository[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visibility, setVisibility] = useState("all");
  const [showForks, setShowForks] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [scanning, setScanning] = useState<string | null>(null);
  const [siteUrl, setSiteUrl] = useState("");
  const [scanningSite, setScanningSite] = useState(false);

  const load = useCallback(
    async (targetPage: number) => {
      setError(null);
      if (targetPage === 1) setRepositories(null);
      try {
        const response = await api.repositories({
          page: targetPage,
          per_page: 30,
          q: search.trim() || undefined,
          visibility: visibility === "all" ? undefined : visibility,
        });
        setRepositories((prev) =>
          targetPage === 1 ? response.repositories : [...(prev || []), ...response.repositories],
        );
        setHasMore(response.has_more);
        setPage(response.page);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load repositories.");
        setRepositories((prev) => prev ?? []);
      }
    },
    [search, visibility],
  );

  useEffect(() => {
    if (!authorized) return;
    const timer = setTimeout(() => {
      void load(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [authorized, load]);

  const analyze = async (repo: Repository) => {
    const key = `${repo.owner}/${repo.name}`;
    setScanning(key);
    setError(null);
    try {
      await api.startScan(repo.owner, repo.name);
      router.push(`/workspace/${repo.owner}/${repo.name}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not start the scan. Please try again.",
      );
      setScanning(null);
    }
  };

  const analyzeSite = async () => {
    const raw = siteUrl.trim();
    if (!raw) return;
    setScanningSite(true);
    setError(null);
    try {
      const status = await api.startUrlScan(raw);
      router.push(`/workspace/${status.owner}/${status.repo}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not start the website scan. Please try again.",
      );
      setScanningSite(false);
    }
  };

  if (loading || !authorized) {
    return (
      <AppShell>
        <LoadingState label="Loading repositories…" />
      </AppShell>
    );
  }

  const visible = (repositories || []).filter(
    (repo) => showForks || !repo.fork,
  );

  return (
    <AppShell>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-white">Repositories</h1>
        <p className="mt-1 text-sm text-slate-400">
          Choose a repository to scan and index for AI analysis.
        </p>
      </div>

      <section className="mb-6 rounded-xl border border-ink-600 bg-ink-900/60 p-4">
        <h2 className="text-sm font-medium text-white">Scan a website</h2>
        <p className="mt-1 text-xs text-slate-400">
          No GitHub needed — paste any public URL. The site is crawled same-origin
          (pages, CSS, JS it serves to browsers) and indexed for search + AI chat.
        </p>
        <form
          className="mt-3 flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void analyzeSite();
          }}
        >
          <div className="min-w-64 flex-1">
            <Input
              label="Website URL"
              value={siteUrl}
              onChange={(event) => setSiteUrl(event.target.value)}
              placeholder="https://example.com"
              inputMode="url"
            />
          </div>
          <Button
            type="submit"
            disabled={scanningSite || !siteUrl.trim()}
          >
            {scanningSite ? "Starting…" : "Scan website"}
          </Button>
        </form>
      </section>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1">
          <Input
            label="Search repositories"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name…"
          />
        </div>
        <div className="w-44">
          <Select
            label="Visibility"
            value={visibility}
            onChange={(event) => setVisibility(event.target.value)}
          >
            <option value="all">All</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
          </Select>
        </div>
        <label className="focus-ring mb-1 flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-ink-600 bg-ink-900 px-3 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={showForks}
            onChange={(event) => setShowForks(event.target.checked)}
            className="h-3.5 w-3.5 accent-accent"
          />
          Include forks
        </label>
        <Button onClick={() => void load(1)} variant="secondary">
          Refresh
        </Button>
      </div>

      {error ? <div className="mb-4"><ErrorState description={error} onRetry={() => void load(1)} /></div> : null}

      {repositories === null ? (
        <LoadingState label="Loading repositories…" />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No repositories found"
          description={
            search
              ? "No repositories match your search."
              : "Your GitHub account has no visible repositories."
          }
        />
      ) : (
        <>
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((repo) => (
              <li key={repo.full_name}>
                <RepoCard
                  repo={repo}
                  onAnalyze={(target) => void analyze(target)}
                  analyzing={scanning === repo.full_name}
                />
              </li>
            ))}
          </ul>
          {hasMore ? (
            <div className="mt-5 flex justify-center">
              <Button onClick={() => void load(page + 1)}>Load more</Button>
            </div>
          ) : null}
        </>
      )}
    </AppShell>
  );
}
