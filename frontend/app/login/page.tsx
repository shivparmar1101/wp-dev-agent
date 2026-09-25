"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LoginButton } from "@/components/github/login-button";
import { useSession } from "@/lib/session";
import { parseErrorParams } from "@/lib/format";
import { Spinner } from "@/components/ui/spinner";

const FEATURES = [
  {
    title: "Connect GitHub",
    body: "Sign in with OAuth and pick any repository you can read — public or private.",
  },
  {
    title: "Scan and index",
    body: "Background scans detect WordPress, themes, plugins, and Elementor, then index PHP, CSS, and JS for search.",
  },
  {
    title: "Ask the agent",
    body: "Get grounded answers with relevant files, line ranges, and a suggested fix — read-only, no commits.",
  },
];

function LoginContent() {
  const { user, loading, health } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const error = parseErrorParams(new URLSearchParams(params.toString()));

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60rem 30rem at 15% -10%, rgba(109,139,255,0.16), transparent 60%), radial-gradient(50rem 26rem at 90% 110%, rgba(62,207,142,0.10), transparent 55%)",
        }}
      />
      <div className="relative w-full max-w-lg animate-fade-up">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white">
            WP
          </span>
          <div>
            <h1 className="text-lg font-semibold text-white">WP Dev Agent</h1>
            <p className="text-xs text-slate-400">
              AI development agent for WordPress and Elementor repositories
            </p>
          </div>
        </div>

        <div className="panel p-6">
          <h2 className="text-base font-semibold text-white">Sign in to get started</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            Read-only access. The agent never commits, pushes, opens pull requests, or
            modifies your repositories.
          </p>

          {error ? (
            <div
              className="mt-4 rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          <div className="mt-5">
            {loading ? (
              <div className="flex h-11 items-center justify-center gap-2 text-xs text-slate-400">
                <Spinner /> Checking session…
              </div>
            ) : (
              <LoginButton className="w-full" />
            )}
          </div>

          {health && !health.github_configured ? (
            <p className="mt-4 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-[11px] leading-relaxed text-warn">
              GitHub OAuth is not configured on the backend. Set{" "}
              <code className="font-mono">GITHUB_CLIENT_ID</code> and{" "}
              <code className="font-mono">GITHUB_CLIENT_SECRET</code> in{" "}
              <code className="font-mono">.env</code>, then restart the API.
            </p>
          ) : null}
        </div>

        <ul className="mt-5 grid gap-3">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="panel-subtle px-4 py-3">
              <div className="text-xs font-semibold text-white">{feature.title}</div>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{feature.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <LoginContent />
    </Suspense>
  );
}
