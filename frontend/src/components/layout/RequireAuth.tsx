import { Navigate, useRouterState } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { useMe } from "@/api/queries";

/**
 * Gate for every authenticated screen.
 *
 * `useMe` resolves to null rather than throwing when there is no session, so an expired
 * cookie sends the user to /login with a redirect back, instead of showing a broken page.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isLoading } = useMe();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  if (isLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" search={{ redirect: pathname }} replace />;
  }

  return <>{children}</>;
}
