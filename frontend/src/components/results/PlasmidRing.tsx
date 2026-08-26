/**
 * Plasmid map, lifted from the Lovable design.
 *
 * Segment names and lengths come from the engine (`design.plasmid_segments`); the
 * colours are chosen here, because colour is presentation, not science.
 */

import type { CandidateDetail, PlasmidSegment } from "@/api/types";

const SEGMENT_COLORS: Record<PlasmidSegment["kind"], string> = {
  promoter: "var(--mint)",
  switch: "var(--deep-blue)",
  payload: "oklch(0.7 0.18 145)",
  marker: "oklch(0.6 0.18 280)",
  terminator: "oklch(0.78 0.14 90)",
  backbone: "oklch(0.75 0.03 250)",
};

/**
 * Draw the construct as a ring, with each segment sized by its real base-pair length.
 *
 * The Lovable design used fixed arc positions; here the arcs are proportional, so a
 * 1,800 bp payload actually looks larger than a 35 bp promoter.
 */
export function PlasmidRing({ candidate }: { candidate: CandidateDetail }) {
  const segments = candidate.design.plasmid_segments ?? [];
  const totalBp =
    candidate.design.sequence_length_bp ||
    segments.reduce((sum, seg) => sum + seg.length_bp, 0) ||
    1;

  const radius = 100;
  const cx = 130;
  const cy = 130;
  const gapDegrees = 3;

  const polar = (deg: number) => {
    const a = ((deg - 90) * Math.PI) / 180;
    return [cx + radius * Math.cos(a), cy + radius * Math.sin(a)] as const;
  };

  const arc = (start: number, end: number) => {
    const [x1, y1] = polar(start);
    const [x2, y2] = polar(end);
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${end - start > 180 ? 1 : 0} 1 ${x2} ${y2}`;
  };

  let cursor = 0;
  const arcs = segments.map((segment) => {
    const sweep = (segment.length_bp / totalBp) * 360;
    const start = cursor;
    cursor += sweep;
    return {
      segment,
      start,
      // Never let a rounding gap swallow a short segment entirely.
      end: Math.max(start + 1, start + sweep - gapDegrees),
    };
  });

  return (
    <svg width="260" height="260" viewBox="0 0 260 260" className="drop-shadow-sm">
      <title>{`Plasmid map · ${totalBp.toLocaleString()} bp`}</title>
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill="none"
        stroke="var(--border)"
        strokeWidth="1"
        strokeDasharray="2 4"
      />
      <circle cx={cx} cy={cy} r={radius - 14} fill="none" stroke="var(--border)" strokeWidth="1" />

      {arcs.map(({ segment, start, end }) => (
        <path
          key={`${segment.kind}-${segment.name}-${start}`}
          d={arc(start, end)}
          stroke={SEGMENT_COLORS[segment.kind] ?? "var(--muted-foreground)"}
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
        >
          <title>{`${segment.name} · ${segment.length_bp.toLocaleString()} bp`}</title>
        </path>
      ))}

      {Array.from({ length: 24 }).map((_, i) => {
        const [x1, y1] = polar(i * 15);
        const a = ((i * 15 - 90) * Math.PI) / 180;
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={cx + (radius + 8) * Math.cos(a)}
            y2={cy + (radius + 8) * Math.sin(a)}
            stroke="var(--muted-foreground)"
            strokeWidth="0.5"
            opacity="0.4"
          />
        );
      })}

      <text
        x={cx}
        y={cy - 6}
        textAnchor="middle"
        className="fill-foreground font-mono"
        fontSize="11"
        fontWeight="600"
      >
        {candidate.engine_ref}
      </text>
      <text
        x={cx}
        y={cy + 10}
        textAnchor="middle"
        className="fill-muted-foreground font-mono"
        fontSize="9"
      >
        {totalBp.toLocaleString()} bp
      </text>
      <text x={cx} y={cy + 24} textAnchor="middle" className="fill-mint font-mono" fontSize="9">
        ● rank {candidate.rank ?? "—"}
      </text>
    </svg>
  );
}

/** Legend for the ring, so the colours mean something. */
export function PlasmidLegend({ segments }: { segments: PlasmidSegment[] }) {
  return (
    <div className="mt-4 flex flex-wrap justify-center gap-x-4 gap-y-2">
      {segments.map((segment) => (
        <div key={`${segment.kind}-${segment.name}`} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: SEGMENT_COLORS[segment.kind] ?? "var(--muted-foreground)" }}
          />
          <span className="font-mono text-[10px] text-muted-foreground">
            {segment.name}
            <span className="ml-1 opacity-60">{segment.length_bp.toLocaleString()}bp</span>
          </span>
        </div>
      ))}
    </div>
  );
}
