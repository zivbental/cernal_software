/**
 * Organism and RNA icons, lifted verbatim from the Lovable design.
 *
 * Hand-drawn SVGs rather than lucide, because each carries a micro-animation keyed to
 * the organism it represents (see `animate-bacteria` etc. in styles.css).
 */

export function BacteriaIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="4.5" y="8.5" width="15" height="7" rx="3.5" />
      <circle cx="9" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="13" cy="11" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="13" r="0.8" fill="currentColor" stroke="none" />
      <path d="M4.5 12c-1.2-.6-2-1.4-2.5-2.4" />
      <path d="M4.5 12c-1.2.6-2 1.4-2.5 2.4" />
      <path d="M19.5 12c1.2-.6 2-1.4 2.5-2.4" />
      <path d="M19.5 12c1.2.6 2 1.4 2.5 2.4" />
    </svg>
  );
}

/* ---------- Yeast (budding) icon ---------- */
export function YeastIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* mother cell */}
      <ellipse cx="10" cy="13" rx="6" ry="6.5" />
      {/* nucleus */}
      <circle cx="9" cy="13" r="1.6" fill="currentColor" stroke="none" opacity="0.55" />
      {/* daughter bud */}
      <circle className="yeast-bud" cx="18" cy="8.5" r="3.2" />
      <circle cx="18" cy="8" r="0.7" fill="currentColor" stroke="none" opacity="0.55" />
    </svg>
  );
}

/* ---------- Human (waving) icon ---------- */
export function HumanIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* head */}
      <circle cx="12" cy="5" r="2.6" />
      {/* body */}
      <path d="M12 8v8" />
      {/* legs */}
      <path d="M12 16l-2.5 5" />
      <path d="M12 16l2.5 5" />
      {/* static arm */}
      <path d="M12 10l-4 4" />
      {/* waving arm — rotates from shoulder */}
      <g className="human-wave" style={{ transformOrigin: "12px 10px" }}>
        <path d="M12 10l4-3" />
        <path d="M16 7l0.5 -1.5" />
      </g>
    </svg>
  );
}

export function ShieldBacteriaIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* bacteria (behind shield, upper-right) */}
      <g className="shield-bact">
        <circle cx="22" cy="9" r="4.2" fill="currentColor" stroke="none" opacity="0.9" />
        {/* surface pili / spikes */}
        <g stroke="currentColor" strokeWidth="1.4">
          <line x1="22" y1="3.2" x2="22" y2="5" />
          <line x1="27.6" y1="9" x2="25.8" y2="9" />
          <line x1="22" y1="14.8" x2="22" y2="13" />
          <line x1="16.4" y1="9" x2="18.2" y2="9" />
          <line x1="26.2" y1="5" x2="25" y2="6.2" />
          <line x1="26.2" y1="13" x2="25" y2="11.8" />
          <line x1="17.8" y1="5" x2="19" y2="6.2" />
          <line x1="17.8" y1="13" x2="19" y2="11.8" />
        </g>
        {/* inner specks */}
        <circle cx="20.8" cy="8" r="0.7" fill="hsl(var(--card))" stroke="none" />
        <circle cx="23" cy="10" r="0.6" fill="hsl(var(--card))" stroke="none" />
      </g>
      {/* shield (in front) */}
      <path
        d="M14 6 L4 9 V16 C4 21.5 8 25.5 14 28 C20 25.5 24 21.5 24 16 V9 Z"
        fill="hsl(var(--card))"
      />
      <path d="M14 6 L4 9 V16 C4 21.5 8 25.5 14 28 C20 25.5 24 21.5 24 16 V9 Z" />
      {/* center divider */}
      <path d="M14 7.5 V27" strokeWidth="1.4" />
    </svg>
  );
}

export function SkullBonesIcon({ className = "" }: { className?: string }) {
  const Bone = () => (
    <g>
      <rect x="4" y="15" width="24" height="2.2" rx="1.1" />
      <circle cx="5" cy="14.2" r="2.2" />
      <circle cx="5" cy="17.8" r="2.2" />
      <circle cx="27" cy="14.2" r="2.2" />
      <circle cx="27" cy="17.8" r="2.2" />
    </g>
  );
  return (
    <svg
      viewBox="0 0 32 32"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      <g className="reaper-body" transform="rotate(30 16 16)">
        <Bone />
      </g>
      <g className="reaper-scythe" transform="rotate(-30 16 16)">
        <Bone />
      </g>
    </svg>
  );
}

export function RnaIcon({ className = "" }: { className?: string }) {
  const dots = Array.from({ length: 40 }, (_, i) => {
    const a = (i / 40) * Math.PI * 2;
    return { x: 16 + Math.cos(a) * 14.6, y: 16 + Math.sin(a) * 14.6 };
  });
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* dotted outer ring */}
      <g className="rna-dots" fill="currentColor" stroke="none">
        {dots.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r="0.55" />
        ))}
      </g>
      {/* solid inner ring */}
      <circle cx="16" cy="16" r="12.4" />
      {/* RNA helix: two crossing strands */}
      <g className="rna-helix" strokeWidth="1.4">
        <path d="M9 9 C 21 12, 11 20, 22 23" />
        <path d="M22 9 C 10 12, 21 20, 9 23" />
        {/* rungs */}
        <path d="M11.2 10.8 L 19.6 10.4" strokeWidth="1" />
        <path d="M13.6 13.2 L 18.6 13.2" strokeWidth="1" />
        <path d="M13.6 16 L 18.6 16" strokeWidth="1" />
        <path d="M13.6 18.8 L 18.6 18.8" strokeWidth="1" />
        <path d="M12.4 21.2 L 20.8 21.6" strokeWidth="1" />
      </g>
    </svg>
  );
}










