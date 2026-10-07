import type { ReactNode } from "react";

export function Caveat({ children }: { children: ReactNode }) {
  return (
    <aside className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-foreground">
      {children}
    </aside>
  );
}

export function HelpLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      className="text-mint underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
      href={href}
    >
      {children}
    </a>
  );
}
