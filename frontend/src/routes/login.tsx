import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Clock, Loader2, LogIn } from "lucide-react";

import cernalLogo from "@/assets/cernal-logo-animated.svg";
import { ApiError } from "@/api/client";
import { useLogin } from "@/api/queries";

export const Route = createFileRoute("/login")({
  component: LoginPage,
  // Optional, so other routes can link here without supplying search params.
  validateSearch: (search: Record<string, unknown>): { redirect?: string } =>
    typeof search.redirect === "string" ? { redirect: search.redirect } : {},
});

function LoginPage() {
  const navigate = useNavigate();
  const { redirect } = Route.useSearch();
  const login = useLogin();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const pending =
    login.error instanceof ApiError && login.error.code === "pending_approval"
      ? login.error.message
      : null;

  const message = pending
    ? null
    : login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "Could not reach the server."
        : null;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    await login.mutateAsync({ username, password });
    navigate({ to: redirect ?? "/projects" });
  }

  return (
    <div className="grid min-h-screen place-items-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <img src={cernalLogo} alt="CERNAL" className="h-11 w-auto" />
          <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Compiler-like Engine for RNA Logic
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-border bg-card p-7 shadow-clinical"
        >
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Use the account your lab administrator created for you.
          </p>

          <label className="mt-6 block">
            <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Username
            </span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
            />
          </label>

          <label className="mt-4 block">
            <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
            />
          </label>

          {pending && (
            <div
              role="status"
              className="mt-4 flex items-start gap-2.5 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2.5"
            >
              <Clock className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div className="text-sm">
                <div className="font-medium text-foreground">Awaiting approval</div>
                <p className="mt-0.5 text-muted-foreground">{pending}</p>
              </div>
            </div>
          )}

          {message && (
            <p
              role="alert"
              className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={login.isPending}
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-deep px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:opacity-95 disabled:opacity-60"
          >
            {login.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <LogIn className="h-4 w-4" />
            )}
            Sign in
          </button>

          <p className="mt-5 text-center text-sm text-muted-foreground">
            No account yet?{" "}
            <Link to="/register" className="text-foreground underline underline-offset-2">
              Request one
            </Link>
          </p>
        </form>

        <p className="mt-6 text-center font-mono text-[11px] text-muted-foreground">
          CERNAL · TAU iGEM
        </p>
      </div>
    </div>
  );
}
