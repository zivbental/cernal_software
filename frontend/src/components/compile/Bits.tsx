/**
 * Small shared controls from the Lovable design, used across the wizard steps.
 */

import { CheckCircle2 } from "lucide-react";
import type { ReactNode } from "react";

export function Token({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md border border-border bg-card px-2.5 py-1 text-foreground">
      [ {children} ]
    </span>
  );
}

export function Check({ on }: { on: boolean }) {
  return (
    <div
      className={`grid h-5 w-5 place-items-center rounded-md border transition ${
        on ? "border-mint bg-mint text-mint-foreground" : "border-border bg-card"
      }`}
    >
      {on && <CheckCircle2 className="h-3.5 w-3.5" />}
    </div>
  );
}

/** A labelled slider bound to real state (the design's version was decorative). */
export function SliderRow({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange?: (value: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono text-foreground">
          {value}
          {unit}
        </span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-border">
        <div
          className="absolute h-1.5 rounded-full bg-gradient-mint"
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-mint bg-card shadow-clinical"
          style={{ left: `calc(${pct}% - 7px)` }}
        />
        {onChange && (
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-label={label}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          />
        )}
      </div>
    </div>
  );
}
