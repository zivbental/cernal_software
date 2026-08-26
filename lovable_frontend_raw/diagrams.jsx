/* CERNAL diagram + simulation components — adapted from the original source.
   Tailwind classes converted to inline styles; fill-* utility classes converted
   to fill="var(--token)" so the components are self-contained (no Tailwind needed).
   React is provided globally by the DC runtime. */

const { useState, useEffect, useRef } = React;

const MONO = "var(--font-mono)";

const OUTPUT_COLORS = {
  GFP: "oklch(0.72 0.18 145)",
  mCherry: "oklch(0.6 0.22 25)",
  RFP: "oklch(0.6 0.22 25)",
  YFP: "oklch(0.82 0.16 95)",
  BFP: "oklch(0.55 0.18 260)",
};

/* ---------- RNA "key" used by the toehold simulation ---------- */
function RNAKey({ color, name, x, y, opacity, clashing }) {
  return (
    <g
      style={{
        transform: `translate(${x}px, ${y}px)`,
        opacity,
        transition: "transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.6s ease",
      }}
    >
      <g className={clashing ? "tha-wiggle" : ""}>
        <g style={{ filter: `drop-shadow(0px 0px 6px ${color})` }}>
          <g transform="translate(-10, -38) scale(0.8)">
            <polygon points="-8,0 -4,-8 4,-8 8,0 4,8 -4,8" fill={color} fillOpacity="0.15" stroke={color} strokeWidth="1.5" />
            <circle cx="0" cy="0" r="1.5" fill={color} />
            <line x1="8" y1="0" x2="24" y2="0" stroke={color} strokeWidth="2" />
            <line x1="16" y1="0" x2="16" y2="5" stroke={color} strokeWidth="2" />
            <line x1="22" y1="0" x2="22" y2="5" stroke={color} strokeWidth="2" />
          </g>
          <line x1="0" y1="0" x2="100" y2="0" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
          {[15, 32.5, 50, 67.5, 85].map((tx, i) => (
            <g key={i}>
              <line x1={tx} y1="0" x2={tx} y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
              <circle cx={tx} cy="10" r="1.2" fill={color} opacity="0.9" />
            </g>
          ))}
          <text x="50" y="-8" fill={color} fontSize="8" fontFamily={MONO} fontWeight="bold" letterSpacing="2" textAnchor="middle">
            SEQ-MATCH
          </text>
        </g>
        <text x="50" y="-22" fill="var(--foreground)" fontSize="9.5" fontFamily={MONO} fontWeight="700" textAnchor="middle" style={{ letterSpacing: 1.5 }}>
          {name.toUpperCase()}
        </text>
      </g>
    </g>
  );
}

/* ---------- Toehold riboswitch simulation ---------- */
function ToeholdSimulation({ logic, gate = "mid", simKey }) {
  const gateType = gate === "mid" ? logic.midGate : logic.outerGate;
  const gateLabel = gate === "mid" ? "MID GATE" : "OUTER GATE";
  const keys =
    gate === "mid"
      ? [
          { name: logic.genes[1].role, color: "var(--mint)" },
          { name: logic.genes[2].role, color: "var(--deep-blue)" },
        ]
      : [
          { name: logic.genes[0].role, color: "var(--mint)" },
          { name: "MID_OUT", color: "var(--deep-blue)" },
        ];
  const output = { name: logic.output, color: OUTPUT_COLORS[logic.output] ?? "var(--mint)" };
  const playbackSpeed = 1.0;

  const [phase, setPhase] = useState(0);
  const [paused, setPaused] = useState(false);
  const phaseRef = useRef(0);
  const timerRef = useRef(null);

  const andPhases = [
    { id: "LOCKED", duration: 1800, text: "LOCKED · Stem-loop blocks the ribosome binding site." },
    { id: "WRONG_APP", duration: 1300, text: "TEST · Off-target RNA approaches." },
    { id: "WRONG_FAIL", duration: 2200, text: "MISMATCH · Sequence fails to hybridize." },
    { id: "WRONG_REJ", duration: 1300, text: "REJECTED · Off-target dissociates." },
    { id: "A_APP", duration: 1300, text: `AND TEST · ${keys[0].name} approaches toehold.` },
    { id: "A_FAIL", duration: 2200, text: `INSUFFICIENT · ${keys[0].name} alone cannot melt the stem.` },
    { id: "A_REJ", duration: 1300, text: `REJECTED · ${keys[0].name} dissociates.` },
    { id: "B_APP", duration: 1300, text: `AND TEST · ${keys[1].name} approaches toehold.` },
    { id: "B_FAIL", duration: 2200, text: `INSUFFICIENT · ${keys[1].name} alone cannot melt the stem.` },
    { id: "B_REJ", duration: 1300, text: `REJECTED · ${keys[1].name} dissociates.` },
    { id: "BOTH_APP", duration: 1800, text: "COOPERATIVE · Both keys dock simultaneously." },
    { id: "UNLOCK", duration: 2200, text: "UNLOCKED · Dual hybridization melts the stem." },
    { id: "TRANSLATE", duration: 5000, text: `TRANSLATING · Ribosome synthesizes ${output.name}.` },
    { id: "RESET", duration: 1300, text: "Resetting logic gate…" },
  ];
  const orPhases = [
    { id: "LOCKED", duration: 1800, text: "LOCKED · Stem-loop blocks the ribosome binding site." },
    { id: "WRONG_APP", duration: 1300, text: "TEST · Off-target RNA approaches." },
    { id: "WRONG_FAIL", duration: 2200, text: "MISMATCH · Sequence fails to hybridize." },
    { id: "WRONG_REJ", duration: 1300, text: "REJECTED · Off-target dissociates." },
    { id: "A_APP", duration: 1300, text: `OR TEST · ${keys[0].name} approaches toehold.` },
    { id: "A_UNLOCK", duration: 2200, text: `SUCCESS · ${keys[0].name} melts the stem.` },
    { id: "A_TRANS", duration: 5000, text: `TRANSLATING · ${output.name} via ${keys[0].name}.` },
    { id: "A_RESET", duration: 1300, text: "Resetting…" },
    { id: "B_APP", duration: 1300, text: `OR TEST · ${keys[1].name} approaches toehold.` },
    { id: "B_UNLOCK", duration: 2200, text: `SUCCESS · ${keys[1].name} melts the stem.` },
    { id: "B_TRANS", duration: 5000, text: `TRANSLATING · ${output.name} via ${keys[1].name}.` },
    { id: "RESET", duration: 1300, text: "Resetting logic gate…" },
  ];
  const activePhases = gateType === "AND" ? andPhases : orPhases;

  // Reset to phase 0 whenever the candidate or gate changes.
  useEffect(() => {
    phaseRef.current = 0;
    setPhase(0);
  }, [gateType, simKey]);

  // Playback loop.
  useEffect(() => {
    if (paused) {
      if (timerRef.current) clearTimeout(timerRef.current);
      return;
    }
    const run = () => {
      const d = activePhases[phaseRef.current].duration / playbackSpeed;
      timerRef.current = setTimeout(() => {
        const next = (phaseRef.current + 1) % activePhases.length;
        phaseRef.current = next;
        setPhase(next);
        run();
      }, d);
    };
    run();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, gateType, simKey]);

  const isUnlocked =
    gateType === "AND"
      ? phase === 11 || phase === 12
      : phase === 5 || phase === 6 || phase === 9 || phase === 10;
  const isTranslating = gateType === "AND" ? phase === 12 : phase === 6 || phase === 10;

  const rbsPos = isUnlocked ? { x: 445, y: 300 } : { x: 280, y: 115 };
  const startPos = isUnlocked ? { x: 560, y: 300 } : { x: 310, y: 220 };
  const pathD = isUnlocked
    ? "M 50 300 L 250 300 L 400 300 C 430 300, 460 300, 490 300 L 640 300 L 850 300"
    : "M 50 300 L 250 300 L 250 150 C 250 80, 310 80, 310 150 L 310 300 L 750 300";

  let wrongKey = { x: 100, y: 150, opacity: 0, clashing: false };
  let key1 = { x: 50, y: 150, opacity: 0, clashing: false };
  let key2 = { x: 150, y: 150, opacity: 0, clashing: false };
  if (gateType === "AND") {
    switch (phase) {
      case 1: wrongKey = { x: 100, y: 286, opacity: 1, clashing: false }; break;
      case 2: wrongKey = { x: 100, y: 286, opacity: 1, clashing: true }; break;
      case 3: wrongKey = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 4: key1 = { x: 50, y: 286, opacity: 1, clashing: false }; break;
      case 5: key1 = { x: 50, y: 286, opacity: 1, clashing: true }; break;
      case 6: key1 = { x: 50, y: 150, opacity: 0, clashing: false }; break;
      case 7: key2 = { x: 150, y: 286, opacity: 1, clashing: false }; break;
      case 8: key2 = { x: 150, y: 286, opacity: 1, clashing: true }; break;
      case 9: key2 = { x: 150, y: 150, opacity: 0, clashing: false }; break;
      case 10:
      case 11:
      case 12:
        key1 = { x: 50, y: 286, opacity: 1, clashing: false };
        key2 = { x: 150, y: 286, opacity: 1, clashing: false };
        break;
      default: break;
    }
  } else {
    switch (phase) {
      case 1: wrongKey = { x: 100, y: 286, opacity: 1, clashing: false }; break;
      case 2: wrongKey = { x: 100, y: 286, opacity: 1, clashing: true }; break;
      case 3: wrongKey = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 4:
      case 5:
      case 6:
        key1 = { x: 100, y: 286, opacity: 1, clashing: false };
        break;
      case 7: key1 = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 8:
      case 9:
      case 10:
        key2 = { x: 100, y: 286, opacity: 1, clashing: false };
        break;
      default: break;
    }
  }
  const showClash = gateType === "AND" ? phase === 2 || phase === 5 || phase === 8 : phase === 2;

  const riboOp = isUnlocked ? 1 : 0;
  const riboX = isTranslating ? 760 : 445;
  const outScale = isTranslating ? 1.6 : 0;
  const outY = isTranslating ? 180 : 280;

  const chip = (bg) => ({ display: "inline-block", height: 8, width: 8, borderRadius: 2, background: bg });

  return (
    <div style={{ width: "100%" }}>
      <style>{`
        @keyframes tha-wiggle {
          0%,100% { transform: translate(0,0) rotate(0); }
          25% { transform: translate(-3px,0) rotate(-0.6deg); }
          50% { transform: translate(3px,0) rotate(0.6deg); }
          75% { transform: translate(-2px,0) rotate(-0.4deg); }
        }
        .tha-wiggle { animation: tha-wiggle 0.25s ease-in-out infinite; }
        @keyframes tha-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        .tha-pulse { animation: tha-pulse 2s cubic-bezier(0.4,0,0.6,1) infinite; }
        .tha-btn { cursor: pointer; transition: color 0.15s; }
        .tha-btn:hover { color: var(--foreground) !important; }
      `}</style>

      {/* HUD banner */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12, borderRadius: 8, border: "1px solid var(--border)", background: "var(--card)", padding: "10px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, borderRight: "1px solid var(--border)", paddingRight: 12 }}>
          <span className="tha-pulse" style={{ height: 8, width: 8, borderRadius: 999, background: "var(--mint)" }} />
          <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--mint)" }}>
            {gateLabel} · {gateType}
          </span>
        </div>
        <p style={{ flex: 1, margin: 0, fontFamily: MONO, fontSize: 11, letterSpacing: "0.02em", color: "var(--foreground)" }}>
          {activePhases[phase].text}
        </p>
        <button className="tha-btn" onClick={() => setPaused((p) => !p)} style={{ borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", padding: "4px 8px", fontFamily: MONO, fontSize: 10, color: "var(--muted-foreground)" }}>
          {paused ? "PLAY" : "PAUSE"}
        </button>
      </div>

      {/* Canvas */}
      <div style={{ position: "relative", width: "100%", overflow: "hidden", borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)" }}>
        <svg viewBox="0 0 850 400" style={{ display: "block", height: "auto", width: "100%" }}>
          <defs>
            <linearGradient id="tha-strand" x1="50" y1="300" x2="850" y2="300" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="var(--border)" />
              <stop offset="30%" stopColor="var(--muted-foreground)" />
              <stop offset="70%" stopColor="var(--muted-foreground)" />
              <stop offset="100%" stopColor="var(--border)" />
            </linearGradient>
            <pattern id="tha-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="var(--border)" strokeWidth="0.5" opacity="0.4" />
            </pattern>
          </defs>
          <rect width="850" height="400" fill="url(#tha-grid)" />

          <path d={pathD} stroke="url(#tha-strand)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none" style={{ transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)" }} />

          {/* Stem base-pairing */}
          <g style={{ opacity: isUnlocked ? 0 : 1, transition: "opacity 0.6s" }} stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="2,4">
            <line x1="260" y1="280" x2="300" y2="280" />
            <line x1="260" y1="250" x2="300" y2="250" />
            <line x1="260" y1="220" x2="300" y2="220" />
            <line x1="260" y1="190" x2="300" y2="190" />
            <line x1="260" y1="160" x2="300" y2="160" />
          </g>

          {/* RBS */}
          <g style={{ transform: `translate(${rbsPos.x}px, ${rbsPos.y}px)`, transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)" }}>
            <circle cx="0" cy="0" r="8" fill="oklch(0.78 0.14 90)" />
            <circle cx="0" cy="0" r="3" fill="#fff" opacity="0.9" />
            <text x="0" y="-14" fill="oklch(0.55 0.14 90)" fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle">RBS</text>
          </g>

          {/* Start codon */}
          <g style={{ transform: `translate(${startPos.x}px, ${startPos.y}px)`, transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)" }}>
            <polygon points="-7,-7 8,0 -7,7" fill="oklch(0.65 0.18 145)" />
            <text x="0" y="-14" fill="oklch(0.5 0.18 145)" fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle">START</text>
          </g>

          {/* Toehold pad */}
          <line x1="50" y1="300" x2="250" y2="300" stroke="var(--mint)" strokeWidth="10" strokeLinecap="round" opacity="0.12" />
          <line x1="50" y1="308" x2="250" y2="308" stroke="var(--mint)" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
          <text x="150" y="322" fill="var(--mint)" fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle" letterSpacing="2">TOEHOLD_DOMAIN</text>

          <text x="750" y="322" fill="var(--muted-foreground)" fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle" letterSpacing="2" style={{ transition: "opacity 2s", opacity: isUnlocked ? 1 : 0 }}>
            {output.name.toUpperCase()}_CDS
          </text>

          {/* Clash */}
          <g style={{ opacity: showClash ? 1 : 0, transform: `translate(150px, 300px) scale(${showClash ? 1 : 0.8})`, transition: "all 0.2s ease" }}>
            <rect x="-20" y="-9" width="40" height="18" rx="4" fill="var(--accent)" stroke="var(--accent)" strokeWidth="1" />
            <text x="0" y="4" fill="var(--accent-foreground)" fontSize="9" fontFamily={MONO} fontWeight="bold" textAnchor="middle">FAIL</text>
          </g>

          {/* Keys */}
          <RNAKey color="var(--accent)" name="Off-Target" x={wrongKey.x} y={wrongKey.y} opacity={wrongKey.opacity} clashing={wrongKey.clashing} />
          <RNAKey color={keys[0].color} name={keys[0].name} x={key1.x} y={key1.y} opacity={key1.opacity} clashing={key1.clashing} />
          <RNAKey color={keys[1].color} name={keys[1].name} x={key2.x} y={key2.y} opacity={key2.opacity} clashing={key2.clashing} />

          {/* Ribosome */}
          <g style={{ transform: `translate(${riboX}px, 300px)`, opacity: riboOp, transition: `transform ${isTranslating ? 5 / playbackSpeed : 1.5 / playbackSpeed}s linear, opacity 0.8s` }}>
            <path d="M -45 -8 L -35 -35 L 35 -35 L 45 -8 C 45 5, -45 5, -45 -8" fill="var(--deep-blue)" stroke="var(--border)" strokeWidth="1" />
            <path d="M -30 8 C -30 25, 30 25, 30 8 C 30 -2, -30 -2, -30 8" fill="var(--primary)" stroke="var(--border)" strokeWidth="1" />
            <circle cx="0" cy="0" r="4" fill="var(--mint)" opacity={isTranslating ? 1 : 0.4} />
            <text x="0" y="-42" fill="var(--muted-foreground)" fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle">RIBOSOME</text>
          </g>

          {/* Output protein */}
          <g style={{ transform: `translate(${riboX}px, ${outY}px) scale(${outScale})`, opacity: outScale > 0 ? 1 : 0, transition: `transform ${isTranslating ? 5 / playbackSpeed : 0.5 / playbackSpeed}s linear, opacity 0.8s` }}>
            <polygon points="0,-14 12,-6 12,8 0,16 -12,8 -12,-6" fill={output.color} />
            <circle cx="0" cy="1" r="3" fill="#ffffff" opacity="0.75" />
            <text x="0" y="-20" fill={output.color} fontSize="8" fontFamily={MONO} fontWeight="bold" textAnchor="middle">{output.name}</text>
          </g>
        </svg>
      </div>

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 10, fontFamily: MONO, color: "var(--muted-foreground)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={chip("var(--mint)")} /> {keys[0].name}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={chip("var(--deep-blue)")} /> {keys[1].name}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={chip(output.color)} /> Output · {output.name}</div>
      </div>
    </div>
  );
}

/* ---------- Logic circuit (gate diagram) ---------- */
function LogicCircuitView({ logic, activeGate, onGateClick }) {
  const genes = logic.genes.map((g, i) => ({ ...g, y: 50 + i * 80 }));
  const W = 720, H = 460;
  const geneX = 20, geneW = 150;
  const midGateX = 280, invGateX = 280, outerGateX = 460;
  const gateH = 64, outX = 610;
  const midY = (genes[1].y + genes[2].y) / 2 + 18;
  const invY = genes[3].y + 18;
  const outerY = 200;
  const aLineY = genes[0].y + 18;

  const legendChip = (style) => ({ height: 8, width: 8, ...style });

  return (
    <div style={{ width: "100%" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ height: "auto", width: "100%" }}>
        <defs>
          <linearGradient id="upGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--mint)" stopOpacity="0.22" />
            <stop offset="1" stopColor="var(--mint)" stopOpacity="0.08" />
          </linearGradient>
          <linearGradient id="downGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--deep-blue)" stopOpacity="0.22" />
            <stop offset="1" stopColor="var(--deep-blue)" stopOpacity="0.08" />
          </linearGradient>
          <linearGradient id="outGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--mint)" />
            <stop offset="1" stopColor="oklch(0.75 0.2 145)" />
          </linearGradient>
        </defs>

        {genes.map((g) => (
          <g key={g.n}>
            <rect x={geneX} y={g.y} width={geneW} height={36} rx={8}
              fill={g.dir === "up" ? "url(#upGrad)" : "url(#downGrad)"}
              stroke={g.dir === "up" ? "var(--mint)" : "var(--deep-blue)"} strokeWidth="1.25" />
            <text x={geneX + 12} y={g.y + 23} fontSize="14" fontWeight="700" fill="var(--foreground)" fontFamily={MONO}>{g.n}</text>
            <text x={geneX + 78} y={g.y + 23} fontSize="11" fill="var(--muted-foreground)" fontFamily={MONO}>{g.role}</text>
            <rect x={geneX + geneW - 36} y={g.y + 8} width={28} height={20} rx={4}
              fill={g.state === "ON" ? "var(--mint)" : "var(--deep-blue)"} fillOpacity="0.18"
              stroke={g.state === "ON" ? "var(--mint)" : "var(--deep-blue)"} strokeWidth="1" />
            <text x={geneX + geneW - 22} y={g.y + 22} textAnchor="middle" fontSize="9" fontWeight="800"
              fill={g.state === "ON" ? "var(--mint)" : "var(--primary)"} fontFamily={MONO}>{g.state}</text>
          </g>
        ))}

        <path d={`M ${geneX + geneW} ${aLineY} H ${outerGateX - 30} V ${outerY - 22} H ${outerGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[1].y + 18} H ${midGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[2].y + 18} H ${midGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[3].y + 18} H ${invGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />

        {/* Mid gate */}
        <g onClick={() => onGateClick && onGateClick("mid")} style={{ cursor: onGateClick ? "pointer" : "default" }}>
          {activeGate === "mid" && (
            <rect x={midGateX - 10} y={midY - gateH / 2 - 10} width={92} height={gateH + 20} rx={10}
              fill="var(--mint)" fillOpacity="0.08" stroke="var(--mint)" strokeOpacity="0.6" strokeDasharray="4 3" />
          )}
          {logic.midGate === "OR" ? (
            <path d={`M ${midGateX} ${midY - gateH / 2} Q ${midGateX + 28} ${midY - gateH / 2 + 8} ${midGateX + 72} ${midY} Q ${midGateX + 28} ${midY + gateH / 2 - 8} ${midGateX} ${midY + gateH / 2} Q ${midGateX + 20} ${midY} ${midGateX} ${midY - gateH / 2} Z`}
              fill="var(--mint)" fillOpacity="0.14" stroke="var(--mint)" strokeWidth="1.75" />
          ) : (
            <path d={`M ${midGateX} ${midY - gateH / 2} H ${midGateX + 32} A ${gateH / 2} ${gateH / 2} 0 0 1 ${midGateX + 32} ${midY + gateH / 2} H ${midGateX} Z`}
              fill="var(--foreground)" fillOpacity="0.08" stroke="var(--foreground)" strokeWidth="1.75" />
          )}
          <text x={midGateX + 18} y={midY + 5} fontSize="14" fontWeight="800" fill={logic.midGate === "OR" ? "var(--mint)" : "var(--foreground)"} fontFamily={MONO}>{logic.midGate}</text>
        </g>

        {logic.invert && (
          <g>
            <path d={`M ${invGateX} ${invY - gateH / 2} L ${invGateX + 56} ${invY} L ${invGateX} ${invY + gateH / 2} Z`} fill="var(--primary)" fillOpacity="0.14" stroke="var(--primary)" strokeWidth="1.75" />
            <circle cx={invGateX + 62} cy={invY} r="5" fill="var(--background)" stroke="var(--primary)" strokeWidth="1.75" />
            <text x={invGateX + 10} y={invY + 5} fontSize="13" fontWeight="800" fill="var(--primary)" fontFamily={MONO}>NOT</text>
          </g>
        )}

        <path d={`M ${midGateX + 72} ${midY} H ${outerGateX - 18} V ${outerY + 22} H ${outerGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        {logic.invert && (
          <path d={`M ${invGateX + 67} ${invY} H ${outerGateX - 10} V ${outerY + 44} H ${outerGateX - 8}`} stroke="var(--primary)" strokeWidth="1.75" fill="none" opacity="0.85" />
        )}

        {/* Outer gate */}
        <g onClick={() => onGateClick && onGateClick("outer")} style={{ cursor: onGateClick ? "pointer" : "default" }}>
          {activeGate === "outer" && (
            <rect x={outerGateX - 10} y={outerY - 70} width={112} height={140} rx={10}
              fill="var(--mint)" fillOpacity="0.08" stroke="var(--mint)" strokeOpacity="0.6" strokeDasharray="4 3" />
          )}
          {logic.outerGate === "AND" ? (
            <path d={`M ${outerGateX} ${outerY - 56} H ${outerGateX + 34} A 56 56 0 0 1 ${outerGateX + 34} ${outerY + 56} H ${outerGateX} Z`}
              fill="var(--foreground)" fillOpacity="0.08" stroke="var(--foreground)" strokeWidth="1.75" />
          ) : (
            <path d={`M ${outerGateX} ${outerY - 56} Q ${outerGateX + 36} ${outerY - 48} ${outerGateX + 90} ${outerY} Q ${outerGateX + 36} ${outerY + 48} ${outerGateX} ${outerY + 56} Q ${outerGateX + 26} ${outerY} ${outerGateX} ${outerY - 56} Z`}
              fill="var(--mint)" fillOpacity="0.14" stroke="var(--mint)" strokeWidth="1.75" />
          )}
          <text x={outerGateX + 14} y={outerY + 6} fontSize="16" fontWeight="800" fill={logic.outerGate === "AND" ? "var(--foreground)" : "var(--mint)"} fontFamily={MONO}>{logic.outerGate}</text>
        </g>

        <path d={`M ${outerGateX + 90} ${outerY} H ${outX - 6}`} stroke="url(#outGrad)" strokeWidth="3" fill="none" />

        <g>
          <rect x={outX} y={outerY - 28} width={90} height={56} rx={12} fill="url(#outGrad)" stroke="var(--mint)" strokeWidth="1.25" />
          <text x={outX + 45} y={outerY - 4} textAnchor="middle" fontSize="11" fontWeight="800" fill="var(--mint-foreground)" fontFamily={MONO}>EXPRESS</text>
          <text x={outX + 45} y={outerY + 18} textAnchor="middle" fontSize="20" fontWeight="900" fill="var(--mint-foreground)" fontFamily={MONO}>{logic.output}</text>
        </g>

        <text x={20} y={H - 16} fontSize="13" fontWeight="600" fill="var(--foreground)" fontFamily={MONO}>{logic.caption}</text>
      </svg>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 8, fontSize: 10, fontFamily: MONO, color: "var(--muted-foreground)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={legendChip({ borderRadius: 2, background: "var(--mint)" })} /> Over-expressed</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={legendChip({ borderRadius: 2, background: "var(--primary)" })} /> Under-expressed</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={legendChip({ borderRadius: 999, border: "1px solid var(--mint)" })} /> Activating gate</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={legendChip({ borderRadius: 999, border: "1px solid var(--primary)" })} /> Inverting gate</div>
      </div>
    </div>
  );
}

/* ---------- Plasmid map (circular) ---------- */
function PlasmidRing({ candidate }) {
  const cc = candidate.ringColors;
  const features = [
    { start: 10,  end: 80,  color: cc.promoter, label: "T7 Promoter",      sublabel: "~200 bp" },
    { start: 90,  end: 160, color: cc.switch,   label: "Toehold Switch",   sublabel: "~180 bp · AND gate" },
    { start: 170, end: 240, color: cc.payload,  label: "sfGFP Reporter",   sublabel: "~720 bp" },
    { start: 250, end: 310, color: cc.marker,   label: "AmpR Resistance",  sublabel: "~861 bp" },
    { start: 320, end: 355, color: cc.term,     label: "T7 Terminator",    sublabel: "~60 bp" },
  ];
  const r = 110, cx = 230, cy = 230;
  const SVG_W = 500, SVG_H = 500;

  const [hovered, setHovered] = useState(null);
  const [angle, setAngle] = useState(0);
  const rafRef = useRef(null);
  const lastRef = useRef(null);
  const angleRef = useRef(0);

  // Slow spin loop
  useEffect(() => {
    const spin = (ts) => {
      if (lastRef.current != null) {
        const dt = ts - lastRef.current;
        angleRef.current = (angleRef.current + dt * 0.008) % 360;
        setAngle(angleRef.current);
      }
      lastRef.current = ts;
      rafRef.current = requestAnimationFrame(spin);
    };
    if (hovered === null) {
      lastRef.current = null;
      rafRef.current = requestAnimationFrame(spin);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastRef.current = null;
    }
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [hovered]);

  const polar = (deg, radius) => {
    const a = ((deg - 90) * Math.PI) / 180;
    return [cx + radius * Math.cos(a), cy + radius * Math.sin(a)];
  };
  const arc = (start, end) => {
    const [x1, y1] = polar(start, r);
    const [x2, y2] = polar(end, r);
    const large = end - start > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };

  // Hit-test arc: wider invisible stroke for mouse target
  const arcHit = (start, end) => arc(start, end);

  const labelLeader = (start, end) => {
    const nominalMid = (start + end) / 2;
    const [px, py] = polar(nominalMid, r + 6);    // line start just outside arc
    const [lx, ly] = polar(nominalMid, r + 26);   // elbow
    const [tx, ty] = polar(nominalMid, r + 54);   // text center — always radially outside
    return { px, py, lx, ly, tx, ty };
  };

  const hovF = hovered !== null ? features[hovered] : null;

  return (
    <div style={{ position: "relative", display: "block", width: "100%", height: "100%" }}>
      <style>{`
        @keyframes plasmid-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .plasmid-arc-hit { cursor: pointer; }
      `}</style>
      <svg width="100%" height="100%" viewBox={`0 0 ${SVG_W} ${SVG_H}`} style={{ display: "block", filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.12))", overflow: "visible" }}>

        {/* Spinning group — arcs + labels all rotate together */}
        <g style={{ transformOrigin: `${cx}px ${cy}px`, transform: `rotate(${angle}deg)` }}>
          {/* Backbone ring */}
          <circle cx={cx} cy={cy} r={r + 1} fill="none" stroke="var(--border)" strokeWidth="10" strokeOpacity="0.18" />
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth="1" strokeDasharray="2 4" />
          <circle cx={cx} cy={cy} r={r - 12} fill="none" stroke="var(--border)" strokeWidth="0.75" />

          {/* Tick marks */}
          {Array.from({ length: 24 }).map((_, i) => {
            const [x1, y1] = polar(i * 15, r);
            const [x2, y2] = polar(i * 15, r + 5);
            return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--muted-foreground)" strokeWidth="0.5" opacity="0.3" />;
          })}

          {/* Feature arcs + leader lines + labels (all spinning) */}
          {features.map((f, i) => {
            const isHov = hovered === i;
            const dimmed = hovered !== null && !isHov;
            const { px, py, lx, ly, tx, ty } = labelLeader(f.start, f.end);
            return (
              <g key={i} style={{ opacity: dimmed ? 0.2 : 1, transition: "opacity 0.2s" }}>
                {isHov && (
                  <path d={arc(f.start, f.end)} stroke={f.color} strokeWidth="22" fill="none" strokeLinecap="round" opacity="0.18" />
                )}
                <path
                  className="plasmid-arc-hit"
                  d={arcHit(f.start, f.end)}
                  stroke={f.color}
                  strokeWidth={isHov ? 16 : 12}
                  fill="none"
                  strokeLinecap="round"
                  style={{ transition: "stroke-width 0.2s" }}
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                />
                <path d={arcHit(f.start, f.end)} stroke="transparent" strokeWidth="28" fill="none" strokeLinecap="round"
                  onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)} style={{ cursor: "pointer" }} />
                {/* Radial leader line — always points outward, never jumps */}
                <line x1={px} y1={py} x2={lx} y2={ly} stroke={f.color} strokeWidth={isHov ? 1.2 : 0.75} opacity="0.7" />
                <line x1={lx} y1={ly} x2={tx} y2={ty} stroke={f.color} strokeWidth={isHov ? 1.2 : 0.75} opacity="0.5" strokeDasharray="2 2" />
                {/* Text counter-rotates around its own center to stay upright */}
                <g style={{ transformOrigin: `${tx}px ${ty}px`, transform: `rotate(${-angle}deg)` }}>
                  <text x={tx} y={ty - 3} textAnchor="middle" fill={isHov ? f.color : "var(--foreground)"} fontFamily={MONO} fontSize={isHov ? 9.5 : 9} fontWeight="700" letterSpacing="0.03em">{f.label}</text>
                  <text x={tx} y={ty + 8} textAnchor="middle" fill="var(--muted-foreground)" fontFamily={MONO} fontSize="7.5">{f.sublabel}</text>
                </g>
              </g>
            );
          })}
        </g>

        {/* Backbone sublabel */}
        <text x={cx} y={cy - 10} textAnchor="middle" fill="var(--muted-foreground)" fontFamily={MONO} fontSize="7.5" opacity="0.5">pUC19 Backbone</text>

        {/* Center text */}
        <text x={cx} y={cy + 6} textAnchor="middle" fill="var(--foreground)" fontFamily={MONO} fontSize="11" fontWeight="600">{hovF ? hovF.label : candidate.name}</text>
        <text x={cx} y={cy + 20} textAnchor="middle" fill={hovF ? hovF.color : "var(--muted-foreground)"} fontFamily={MONO} fontSize="9">{hovF ? hovF.sublabel : candidate.bp.toLocaleString() + " bp"}</text>
        {!hovF && <text x={cx} y={cy + 34} textAnchor="middle" fill="var(--mint)" fontFamily={MONO} fontSize="8">● optimized</text>}
      </svg>
    </div>
  );
}

module.exports = { ToeholdSimulation, LogicCircuitView, PlasmidRing };
