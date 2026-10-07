import type { ReactNode } from "react";

const HELP_LINKS = [
  { href: "/use-cases", label: "Choose a workflow" },
  { href: "/guide", label: "Quick Guide" },
  { href: "/faq", label: "FAQ" },
  { href: "/api-docs", label: "API Reference" },
  { href: "/compile", label: "New Circuit" },
] as const;

export function HelpNav({ current }: { current: string }) {
  return (
    <nav aria-label="CERNAL help" className="mb-8 flex flex-wrap gap-2">
      {HELP_LINKS.map((item) => (
        <a
          key={item.href}
          href={item.href}
          aria-current={current === item.href ? "page" : undefined}
          className={`rounded-md border px-3 py-1.5 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint ${
            current === item.href
              ? "border-mint/50 bg-mint/10 text-foreground"
              : "border-border bg-surface text-muted-foreground hover:text-foreground"
          }`}
        >
          {item.label}
        </a>
      ))}
    </nav>
  );
}

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
