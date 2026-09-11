/**
 * The docs sidebar: sticky on desktop, a "jump to" select on mobile — same anchor
 * list drives both, so there is exactly one place that names a section.
 */

import { useEffect, useState } from "react";

export type DocsGroup = { heading: string; items: { id: string; label: string }[] };

export const DOCS_NAV: DocsGroup[] = [
  {
    heading: "Start",
    items: [
      { id: "overview", label: "Overview" },
      { id: "authentication", label: "Get an API key" },
      { id: "quickstart", label: "Quickstart" },
    ],
  },
  {
    heading: "How it works",
    items: [
      { id: "lifecycle", label: "Request lifecycle" },
      { id: "objects", label: "Client, Job & Artifact" },
      { id: "scoring", label: "Scoring & the 9 metrics" },
    ],
  },
  {
    heading: "Reference",
    items: [
      { id: "parameters", label: "Every request field" },
      { id: "query-params", label: "Query parameters" },
      { id: "errors", label: "Errors" },
      { id: "functions", label: "Functions & methods" },
      { id: "rest-api", label: "Full REST API" },
    ],
  },
  {
    heading: "Recipes",
    items: [
      { id: "recipe-deseq2", label: "DESeq2 → plasmid design" },
      { id: "recipe-sweep", label: "Cost a sweep first" },
      { id: "recipe-scoring", label: "Custom scoring" },
      { id: "notebook", label: "Jupyter notebook" },
    ],
  },
];

const ALL_IDS = DOCS_NAV.flatMap((g) => g.items.map((i) => i.id));

/** Tracks which section heading is currently under the sticky nav bar. */
function useScrollSpy(ids: string[]): string {
  const [active, setActive] = useState(ids[0]);

  useEffect(() => {
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActive(visible[0].target.id);
        }
      },
      // Offset for the sticky nav (h-16) plus the sticky language switcher below it.
      { rootMargin: "-128px 0px -70% 0px", threshold: 0 },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [ids]);

  return active;
}

function jumpTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  history.replaceState(null, "", `#${id}`);
}

export function DocsSidebar() {
  const active = useScrollSpy(ALL_IDS);

  return (
    <>
      {/* Mobile / narrow: a single jump-to select, no sticky rail to fight the page for space. */}
      <div className="mb-6 lg:hidden">
        <select
          value={active}
          onChange={(e) => jumpTo(e.target.value)}
          className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
        >
          {DOCS_NAV.map((group) => (
            <optgroup key={group.heading} label={group.heading}>
              {group.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      <aside className="hidden lg:block">
        <nav className="sticky top-32 max-h-[calc(100vh-9rem)] w-56 overflow-y-auto pr-2 pb-10">
          {DOCS_NAV.map((group) => (
            <div key={group.heading} className="mb-6">
              <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground/70">
                {group.heading}
              </div>
              <ul className="space-y-0.5 border-l border-border">
                {group.items.map((item) => {
                  const isActive = active === item.id;
                  return (
                    <li key={item.id}>
                      <a
                        href={`#${item.id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          jumpTo(item.id);
                        }}
                        className={`-ml-px block border-l-2 py-1 pl-3 text-sm transition ${
                          isActive
                            ? "border-mint font-medium text-foreground"
                            : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                        }`}
                      >
                        {item.label}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
