import { Loader2 } from "lucide-react";

/** Shared spinner. Lives here rather than in a route module so route files stay leaves. */
export function Loading() {
  return (
    <div className="grid place-items-center py-20">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  );
}
