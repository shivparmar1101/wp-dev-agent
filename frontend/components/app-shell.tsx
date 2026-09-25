"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { GitHubMark } from "@/components/github/login-button";
import { Spinner } from "@/components/ui/spinner";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/repositories", label: "Repositories" },
];

export function AppShell({
  children,
  wide = false,
}: {
  children: React.ReactNode;
  wide?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout, health } = useSession();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
        <div className={`mx-auto flex h-14 items-center justify-between gap-4 px-4 ${wide ? "max-w-none" : "max-w-6xl"}`}>
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="focus-ring flex items-center gap-2 text-sm font-semibold text-white">
              <span className="flex h-6 w-6 items-center justify-center rounded bg-accent text-[11px] font-bold text-white">
                WP
              </span>
              Dev Agent
            </Link>
            <nav className="hidden items-center gap-1 sm:flex">
              {NAV.map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`focus-ring rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                      active ? "bg-ink-800 text-white" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {health && !health.ai_configured ? (
              <span className="hidden rounded-md border border-warn/40 bg-warn/10 px-2 py-0.5 text-[10px] font-medium text-warn sm:inline">
                AI not configured
              </span>
            ) : null}
            {health && !health.github_configured ? (
              <span className="hidden rounded-md border border-danger/40 bg-danger/10 px-2 py-0.5 text-[10px] font-medium text-danger sm:inline">
                GitHub OAuth not configured
              </span>
            ) : null}
            {loading ? (
              <Spinner />
            ) : user ? (
              <div className="flex items-center gap-2">
                {user.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={user.avatar}
                    alt=""
                    className="h-7 w-7 rounded-full border border-ink-600"
                  />
                ) : (
                  <GitHubMark className="h-5 w-5 text-slate-400" />
                )}
                <span className="hidden text-xs text-slate-300 sm:inline">{user.login}</span>
                <button
                  type="button"
                  className="focus-ring rounded-lg border border-ink-600 px-2.5 py-1 text-[11px] font-medium text-slate-300 transition hover:bg-ink-800"
                  onClick={async () => {
                    await logout();
                    router.replace("/login");
                  }}
                >
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <main className={`mx-auto w-full flex-1 px-4 py-6 ${wide ? "max-w-none" : "max-w-6xl"}`}>
        {children}
      </main>
    </div>
  );
}
