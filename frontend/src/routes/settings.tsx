import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { BookMarked, Check, Copy, KeyRound, Plus, RotateCw, ShieldAlert, Trash2 } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  useApiKeys,
  useCreateApiKey,
  useRegenerateApiKey,
  useRevokeApiKey,
} from "@/api/queries";
import type { ApiKey, ApiKeyCreated } from "@/api/types";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Loading } from "@/components/layout/Loading";

export const Route = createFileRoute("/settings")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <SettingsPage />
      </AppShell>
    </RequireAuth>
  ),
});

function SettingsPage() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <KeyRound className="h-3 w-3" /> Developer
          </>
        }
        title="API Keys"
        description="Authenticate a script, notebook or pipeline with a header instead of a
          login — the same account, the same projects and runs, no browser required."
        actions={
          <Link
            to="/api-docs"
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint"
          >
            <BookMarked className="h-4 w-4" /> API reference
          </Link>
        }
      />
      <ApiKeysSection />
    </>
  );
}

function ApiKeysSection() {
  const keysQuery = useApiKeys();
  const [creating, setCreating] = useState(false);
  /** The secret to show right now — from a create or a reset. Cleared on dismiss, and
   * never re-derivable afterwards: this is the only place it ever exists client-side. */
  const [revealed, setRevealed] = useState<ApiKeyCreated | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        {!creating && (
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> New key
          </button>
        )}
      </div>

      {creating && (
        <NewKeyForm
          onCreated={(key) => {
            setRevealed(key);
            setCreating(false);
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {revealed && <SecretReveal apiKey={revealed} onDismiss={() => setRevealed(null)} />}

      {keysQuery.isLoading ? (
        <Loading />
      ) : keysQuery.data && keysQuery.data.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-border">
          {keysQuery.data.map((key) => (
            <KeyRow
              key={key.id}
              apiKey={key}
              onRegenerated={(fresh) => setRevealed(fresh)}
            />
          ))}
        </div>
      ) : (
        !creating && <EmptyKeys onCreate={() => setCreating(true)} />
      )}
    </div>
  );
}

const SCOPE_OPTIONS = [
  { value: "read", label: "Read only", hint: "View projects, runs and results" },
  { value: "read,design", label: "Read + Design", hint: "Also submit runs, cancel them, annotate" },
] as const;

const EXPIRY_OPTIONS = [
  { value: "", label: "Never" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "1 year" },
] as const;

function NewKeyForm({
  onCreated,
  onCancel,
}: {
  onCreated: (key: ApiKeyCreated) => void;
  onCancel: () => void;
}) {
  const create = useCreateApiKey();
  const [label, setLabel] = useState("");
  const [scopes, setScopes] = useState<string>(SCOPE_OPTIONS[1].value);
  const [expiresInDays, setExpiresInDays] = useState("");

  const message = create.error instanceof ApiError ? create.error.message : null;

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        const key = await create.mutateAsync({
          label,
          scopes: scopes.split(","),
          expires_in_days: expiresInDays ? Number(expiresInDays) : null,
        });
        onCreated(key);
        setLabel("");
      }}
      className="rounded-2xl border border-border bg-card p-6 shadow-clinical"
    >
      <h2 className="text-base font-semibold text-foreground">New API key</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Label
          </span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="laptop, snakemake-prod…"
            required
            autoFocus
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Access
          </span>
          <select
            value={scopes}
            onChange={(e) => setScopes(e.target.value)}
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
          >
            {SCOPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Expires
          </span>
          <select
            value={expiresInDays}
            onChange={(e) => setExpiresInDays(e.target.value)}
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
          >
            {EXPIRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {SCOPE_OPTIONS.find((o) => o.value === scopes)?.hint}
      </p>

      {message && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {message}
        </p>
      )}

      <div className="mt-5 flex gap-2">
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-lg bg-gradient-deep px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
        >
          {create.isPending ? "Creating…" : "Create key"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Shown exactly once, right after a key is minted or reset — the server never
 * returns the secret again after this response. */
function SecretReveal({ apiKey, onDismiss }: { apiKey: ApiKeyCreated; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    await navigator.clipboard.writeText(apiKey.secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-2xl border border-mint bg-mint/5 p-6">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-mint" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-foreground">
            Save this key now — you won&rsquo;t see it again
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            &ldquo;{apiKey.label}&rdquo; is stored as a digest, not the secret itself. If you
            lose it, reset the key for a new one.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm text-foreground">
              {apiKey.secret}
            </code>
            <button
              onClick={onCopy}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground hover:border-mint"
            >
              {copied ? <Check className="h-4 w-4 text-mint" /> : <Copy className="h-4 w-4" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className="mt-4">
            <button
              onClick={onDismiss}
              className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
            >
              Done — I&rsquo;ve saved it
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function keyStatus(apiKey: ApiKey): { label: string; className: string } {
  if (apiKey.revoked_at) return { label: "Revoked", className: "bg-secondary text-muted-foreground" };
  if (apiKey.expires_at && new Date(apiKey.expires_at) <= new Date()) {
    return { label: "Expired", className: "bg-secondary text-muted-foreground" };
  }
  return { label: "Active", className: "bg-mint/10 text-mint" };
}

function KeyRow({
  apiKey,
  onRegenerated,
}: {
  apiKey: ApiKey;
  onRegenerated: (key: ApiKeyCreated) => void;
}) {
  const regenerate = useRegenerateApiKey();
  const revoke = useRevokeApiKey();
  const status = keyStatus(apiKey);
  const revoked = Boolean(apiKey.revoked_at);

  async function onReset() {
    if (
      !window.confirm(
        `Reset "${apiKey.label}"? The current secret will stop working immediately.`,
      )
    ) {
      return;
    }
    const fresh = await regenerate.mutateAsync(apiKey.id);
    onRegenerated(fresh);
  }

  async function onRevoke() {
    if (!window.confirm(`Revoke "${apiKey.label}"? This cannot be undone.`)) return;
    await revoke.mutateAsync(apiKey.id);
  }

  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-border bg-card px-5 py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">{apiKey.label}</span>
          <span
            className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${status.className}`}
          >
            {status.label}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <span>{apiKey.prefix}…</span>
          <span>{apiKey.scopes.join(" + ")}</span>
          <span>
            {apiKey.last_used_at
              ? `last used ${new Date(apiKey.last_used_at).toLocaleDateString()}`
              : "never used"}
          </span>
          {apiKey.expires_at && (
            <span>expires {new Date(apiKey.expires_at).toLocaleDateString()}</span>
          )}
        </div>
      </div>

      <div className="flex shrink-0 gap-2">
        <button
          onClick={onReset}
          disabled={regenerate.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground hover:border-mint disabled:opacity-60"
        >
          <RotateCw className="h-3.5 w-3.5" /> Reset
        </button>
        <button
          onClick={onRevoke}
          disabled={revoked || revoke.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-destructive hover:border-destructive disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" /> Revoke
        </button>
      </div>
    </div>
  );
}

function EmptyKeys({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-gradient-mint shadow-mint">
        <KeyRound className="h-5 w-5 text-mint-foreground" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-foreground">No API keys yet</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Mint one to call CERNAL from a script, a notebook, or a pipeline — with
        <code className="mx-1 rounded bg-secondary px-1 py-0.5 font-mono text-xs">
          X-API-Key
        </code>
        instead of a login.
      </p>
      <button
        onClick={onCreate}
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
      >
        <Plus className="h-4 w-4" /> Create your first key
      </button>
    </div>
  );
}
