import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CheckCircle2, Loader2, UserPlus } from "lucide-react";

import cernalLogo from "@/assets/cernal-logo-animated.svg";
import { ApiError } from "@/api/client";
import { useRegister } from "@/api/queries";

export const Route = createFileRoute("/register")({
  component: RegisterPage,
});

function RegisterPage() {
  const register = useRegister();

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const mismatch = confirm.length > 0 && password !== confirm;
  const serverError =
    register.error instanceof ApiError
      ? register.error.message
      : register.error
        ? "Could not reach the server."
        : null;

  if (register.data) {
    return (
      <Shell>
        <div className="rounded-2xl border border-border bg-card p-7 text-center shadow-clinical">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-mint/10">
            <CheckCircle2 className="h-6 w-6 text-mint" />
          </div>
          <h1 className="mt-4 text-lg font-semibold tracking-tight text-foreground">
            Request received
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">{register.data.message}</p>
          <p className="mt-4 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-xs text-muted-foreground">
            {register.data.username} · {register.data.email}
          </p>
          <Link
            to="/login"
            className="mt-6 inline-flex w-full items-center justify-center rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:border-mint"
          >
            Back to sign in
          </Link>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (mismatch) return;
          register.mutate({ username, email, password, full_name: fullName });
        }}
        className="rounded-2xl border border-border bg-card p-7 shadow-clinical"
      >
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          Request an account
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A team administrator approves new accounts before they can be used.
        </p>

        <Field label="Full name" value={fullName} onChange={setFullName} autoFocus
               placeholder="Rosalind Franklin" />
        <Field label="Username" value={username} onChange={setUsername} required
               autoComplete="username" />
        <Field label="Email" value={email} onChange={setEmail} required type="email"
               autoComplete="email" />
        <Field label="Password" value={password} onChange={setPassword} required
               type="password" autoComplete="new-password" />
        <Field label="Confirm password" value={confirm} onChange={setConfirm} required
               type="password" autoComplete="new-password" />

        {mismatch && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            The passwords do not match.
          </p>
        )}

        {serverError && (
          <p
            role="alert"
            className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            {serverError}
          </p>
        )}

        <button
          type="submit"
          disabled={register.isPending || mismatch}
          className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-deep px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:opacity-95 disabled:opacity-60"
        >
          {register.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <UserPlus className="h-4 w-4" />
          )}
          Request account
        </button>

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="text-foreground underline underline-offset-2">
            Sign in
          </Link>
        </p>
      </form>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center bg-background px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <img src={cernalLogo} alt="CERNAL" className="h-11 w-auto" />
          <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Compiler-like Engine for RNA Logic
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  ...props
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <label className="mt-4 block">
      <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <input
        {...props}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
      />
    </label>
  );
}
