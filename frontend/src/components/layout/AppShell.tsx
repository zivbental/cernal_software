/**
 * The signed-in chrome: navigation, session, footer.
 *
 * Lifted from the Lovable design's `Nav`, with the hardcoded avatar replaced by the
 * real session and the dead links replaced by routes.
 */

import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { LogOut, Settings, User } from "lucide-react";
import type { ReactNode } from "react";

import cernalLogo from "@/assets/cernal-logo-animated.svg";
import { useLogout, useMe, useVersion } from "@/api/queries";

const NAV = [
  // The compiler is the product's front door, so it leads.
  { to: "/compile", label: "New Circuit" },
  { to: "/projects", label: "Dashboard" },
  { to: "/guide", label: "Quick Guide" },
  { to: "/use-cases", label: "Use Cases" },
  { to: "/about", label: "About Us" },
] as const;

function Nav() {
  const { data: user } = useMe();
  const { data: version } = useVersion();
  const logout = useLogout();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  async function onLogout() {
    await logout.mutateAsync();
    navigate({ to: "/login" });
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-8">
        <div className="flex items-center gap-10">
          <Link to="/projects" className="flex items-center gap-2.5">
            <img
              src={cernalLogo}
              alt="CERNAL — Compiler-like Engine for RNA Logic"
              className="h-9 w-auto"
            />
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => {
              const active = pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`rounded-md px-3 py-1.5 text-sm transition ${
                    active
                      ? "bg-secondary font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <div
            className="hidden items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs md:flex"
            title={
              version
                ? `Engine ${version.engine} ${version.engine_version}`
                : "Checking engine…"
            }
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${version ? "bg-mint" : "bg-muted-foreground"}`}
            />
            <span className="font-mono text-muted-foreground">TAU iGEM Lab</span>
          </div>

          <Link
            to="/about"
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="About"
          >
            <Settings className="h-4 w-4" />
          </Link>

          <div
            className="grid h-9 w-9 place-items-center rounded-full bg-gradient-mint text-mint-foreground"
            title={user?.username}
          >
            <User className="h-4 w-4" />
          </div>

          <button
            onClick={onLogout}
            disabled={logout.isPending}
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  const { data: version } = useVersion();
  const mock = version?.engine === "MockEngine";

  return (
    <footer className="mx-auto flex max-w-[1400px] items-center justify-between border-t border-border px-8 py-6 font-mono text-[11px] text-muted-foreground">
      <div>CERNAL · Synthetic Biology Compiler · © 2026</div>
      <div className="flex items-center gap-4">
        <span>{version ? `v${version.app_version}` : "—"}</span>
        <span className="flex items-center gap-1.5" title={version?.engine_version}>
          <span className={`h-1.5 w-1.5 rounded-full ${mock ? "bg-amber-500" : "bg-mint"}`} />
          {/* Never let a demo be mistaken for real science. */}
          {mock ? "Mock engine — results are simulated" : "All systems operational"}
        </span>
      </div>
    </footer>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Nav />
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-8 py-10">{children}</main>
      <Footer />
    </div>
  );
}

/** Page header used across the authenticated screens. */
export function PageHeader({
  kicker,
  title,
  description,
  actions,
}: {
  kicker: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
      <div>
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          {kicker}
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}
