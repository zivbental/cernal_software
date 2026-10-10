/**
 * Adapted from cernal-rnaviz render/{single,common}.js, utils.js and CSS.
 * Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University. Apache-2.0.
 * Modified for a read-only React viewer; see PROVENANCE.md and NOTICE.
 */
import { useId } from "react";

export interface RnaBase { index: number; char: string; x: number; y: number }
export interface RnaLink { source: number; target: number }
export interface RnaRegion { label: string; start: number; end: number; color: string }

export const BASE_COLORS: Record<string, string> = {
  A: "#ef4444", U: "#3b82f6", G: "#10b981", C: "#f59e0b",
};
const NODE_RADIUS = 6;
const END_LABEL_OFFSET = 14;
const SINGLE_FOLD_PADDING = 24;

function boundingBox(points: RnaBase[]) {
  const box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  points.forEach((p) => {
    box.minX = Math.min(box.minX, p.x);
    box.minY = Math.min(box.minY, p.y);
    box.maxX = Math.max(box.maxX, p.x);
    box.maxY = Math.max(box.maxY, p.y);
  });
  return box;
}

/** Upstream canvas arithmetic with explicit rotation instead of global state. */
export function computeCanvas(bases: RnaBase[], rotation: number) {
  const box = boundingBox(bases);
  const nativeWidth = box.maxX - box.minX + SINGLE_FOLD_PADDING * 2;
  const nativeHeight = box.maxY - box.minY + SINGLE_FOLD_PADDING * 2;
  const quarterTurn = (Math.abs(rotation) / 90) % 2 === 1;
  const width = quarterTurn ? nativeHeight : nativeWidth;
  const height = quarterTurn ? nativeWidth : nativeHeight;
  const originX = box.minX + (box.maxX - box.minX) / 2;
  const originY = box.minY + (box.maxY - box.minY) / 2;
  return {
    width, height,
    transform: `translate(${width / 2}, ${height / 2}) rotate(${rotation}) translate(${-originX}, ${-originY})`,
  };
}

/** A polyline through consecutive nucleotides: the sugar-phosphate backbone. */
function backbonePath(bases: RnaBase[], from = 0, to = bases.length) {
  if (to - from < 2) return "";
  let d = `M ${bases[from].x} ${bases[from].y}`;
  for (let i = from + 1; i < to; i++) d += ` L ${bases[i].x} ${bases[i].y}`;
  return d;
}

function endLabelPosition(terminal: RnaBase, neighbour: RnaBase | undefined, fallbackY: number) {
  const length = neighbour ? Math.hypot(terminal.x - neighbour.x, terminal.y - neighbour.y) : 0;
  const dx = length && neighbour ? (terminal.x - neighbour.x) / length : 0;
  const dy = length && neighbour ? (terminal.y - neighbour.y) / length : fallbackY;
  return { x: terminal.x + dx * END_LABEL_OFFSET, y: terminal.y + dy * END_LABEL_OFFSET };
}

/**
 * Upstream single-strand drawing: backbone, dashed pairs, colored bases and ends.
 * React escapes all labels; data is validated before reaching the renderer.
 */
export function RnaDrawing({ bases, links, regions, rotation, zoom, selected, onSelect, title }: {
  bases: RnaBase[]; links: RnaLink[]; regions: RnaRegion[]; rotation: number; zoom: number;
  selected: number | null; onSelect: (index: number) => void; title: string;
}) {
  const id = useId();
  const canvas = computeCanvas(bases, rotation);
  const ends = [
    { ...endLabelPosition(bases[0], bases[1], -1), text: "5′" },
    { ...endLabelPosition(bases.at(-1)!, bases.at(-2), 1), text: "3′" },
  ];
  return (
    <svg
      className="rna-structure-svg"
      role="group" aria-roledescription="RNA structure diagram" aria-labelledby={`${id}-title ${id}-description`}
      viewBox={`0 0 ${canvas.width} ${canvas.height}`}
      width={`${zoom * 100}%`} height={380 * zoom}
      style={{ minWidth: `${zoom * 100}%`, maxWidth: "none" }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title id={`${id}-title`}>{title}</title>
      <desc id={`${id}-description`}>
        {bases.length} nucleotides and {links.length} stored base pairs. Solid lines are the
        RNA backbone; dashed lines are base pairs. Select a base to inspect its position.
      </desc>
      <g transform={canvas.transform}>
        <path d={backbonePath(bases)} fill="none" stroke="#94a3b8" strokeWidth={2} />
        {links.map((link) => <line key={`${link.source}-${link.target}`}
          x1={bases[link.source].x} y1={bases[link.source].y}
          x2={bases[link.target].x} y2={bases[link.target].y}
          stroke="#64748b" strokeWidth={1.5} strokeDasharray={4} />)}
        {regions.map((region, index) => <path key={index}
          d={backbonePath(bases, region.start, region.end)}
          fill="none" stroke={region.color} strokeOpacity={0.3} strokeWidth={19}
          strokeLinecap="round" strokeLinejoin="round" />)}
        {bases.map((base) => {
          const region = regions.find((item) => base.index >= item.start && base.index < item.end);
          const tooltip = `${base.char} · position ${base.index + 1}${region ? ` · ${region.label}` : ""}`;
          return <g key={base.index} className="rna-base" data-base-index={base.index}
            role="button" aria-label={tooltip} aria-pressed={selected === base.index}
            tabIndex={base.index === (selected ?? 0) ? 0 : -1}
            onClick={() => onSelect(base.index)}
            onKeyDown={(event) => {
              let next = base.index;
              if (event.key === "ArrowRight" || event.key === "ArrowDown") next = Math.min(bases.length - 1, next + 1);
              else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = Math.max(0, next - 1);
              else if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              onSelect(next);
              const nextBase = event.currentTarget.parentElement?.querySelector<SVGGElement>(`[data-base-index="${next}"]`);
              nextBase?.focus();
            }}>
            <title>{tooltip}</title>
            <circle cx={base.x} cy={base.y} r={NODE_RADIUS}
              fill={BASE_COLORS[base.char]} stroke={selected === base.index ? "#ffffff" : "#0f172a"}
              strokeWidth={selected === base.index ? 3 : 1.5} />
            <text x={base.x} y={base.y} fontSize={6} fontWeight={700} fill="#ffffff"
              textAnchor="middle" dominantBaseline="central" pointerEvents="none"
              transform={`rotate(${-rotation}, ${base.x}, ${base.y})`}>{base.char}</text>
          </g>;
        })}
        {ends.map((end) => <text key={end.text} x={end.x} y={end.y} fontSize={8}
          fontWeight={700} fill="#f8fafc" stroke="#0f172a" strokeWidth={2.5}
          paintOrder="stroke fill" textAnchor="middle" dominantBaseline="central"
          transform={`rotate(${-rotation}, ${end.x}, ${end.y})`}>{end.text}</text>)}
      </g>
    </svg>
  );
}
