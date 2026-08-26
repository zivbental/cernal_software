import type { RunStatus } from "@/api/types";

const STYLES: Record<RunStatus, string> = {
  DRAFT: "bg-secondary text-muted-foreground",
  QUEUED: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  RUNNING: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  COMPLETED: "bg-mint/10 text-mint",
  FAILED: "bg-destructive/10 text-destructive",
  CANCELLED: "bg-secondary text-muted-foreground",
};

const LABELS: Record<RunStatus, string> = {
  DRAFT: "Draft",
  QUEUED: "Queued",
  RUNNING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${STYLES[status]}`}
    >
      {status === "RUNNING" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {LABELS[status]}
    </span>
  );
}
