import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

// --- FUTURISTIC, DE-LOOPED SLIM RNA KEY COMPONENT ---
const RNAKeyIcon = ({ color, name, x, y, opacity, isClashing }) => {
  // Snappy entry, but smooth retreat
  const transition = 'transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.6s ease';

  return (
    <g 
      style={{ 
        transform: `translate(${x}px, ${y}px)`, 
        opacity: opacity, 
        transition: transition 
      }}
    >
      <g className={isClashing ? "animate-wiggle" : ""}>
        <g style={{ filter: `drop-shadow(0px 0px 8px ${color}80)` }}>
          {/* --- Slim Cyber-Key Handle (Hexagonal Tech design, zero circular loops) --- */}
          <g transform="translate(-10, -42) scale(0.85)">
            <polygon points="-8,0 -4,-8 4,-8 8,0 4,8 -4,8" fill={`${color}20`} stroke={color} strokeWidth="1.5" />
            <circle cx="0" cy="0" r="1.5" fill={color} />
            <line x1="8" y1="0" x2="24" y2="0" stroke={color} strokeWidth="2" />
            <line x1="16" y1="0" x2="16" y2="5" stroke={color} strokeWidth="2" strokeLinecap="square" />
            <line x1="22" y1="0" x2="22" y2="5" stroke={color} strokeWidth="2" strokeLinecap="square" />
          </g>

          {/* --- Slim mRNA Backbone --- */}
          <line x1="0" y1="0" x2="100" y2="0" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
          
          {/* --- Slim Nucleobase Teeth --- */}
          {[15, 32.5, 50, 67.5, 85].map((tx, i) => (
            <g key={i}>
              <line x1={tx} y1="0" x2={tx} y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
              <circle cx={tx} cy="10" r="1.2" fill="#fff" opacity="0.9" />
            </g>
          ))}
          
          {/* Sequence label - Monospace Tech */}
          <text x="50" y="-8" fill={color} fontSize="8" fontFamily="monospace" fontWeight="bold" letterSpacing="2" textAnchor="middle">
            SEQ-MATCH
          </text>
        </g>
        
        {/* Target Name Label */}
        <text x="50" y="-24" fill="#f8fafc" fontSize="10" fontFamily="sans-serif" fontWeight="bold" textAnchor="middle" className="tracking-widest uppercase">
          {name}
        </text>
      </g>
    </g>
  );
};

// --- WIDGET COMPONENT ---
export const ToeholdWidget = ({ gateType, keys, output, playbackSpeed, isPaused, onPhaseChange }) => {
  const [phase, setPhase] = useState(0);
  const phaseRef = useRef(0);
  const timerRef = useRef(null);

  // Highly granular phases to perfectly time the "fly in -> wait -> fail -> leave" sequences
  const andPhases = [
    { id: 'LOCKED', duration: 2000, text: 'LOCKED: Stem-loop structure blocks the Ribosome Binding Site.' },
    
    // Wrong Key Sequence
    { id: 'WRONG_APP', duration: 1500, text: 'TEST: Non-target RNA approaches.' },
    { id: 'WRONG_FAIL', duration: 2500, text: 'MISMATCH: Sequence fails to hybridize. Thermodynamic clash.' },
    { id: 'WRONG_REJ', duration: 1500, text: 'REJECTED: Non-target RNA dissociates.' },
    
    // Key A Sequence
    { id: 'A_APP', duration: 1500, text: 'AND TEST: Key A (Target 1) approaches toehold.' },
    { id: 'A_FAIL', duration: 2500, text: 'INSUFFICIENT: Key A alone lacks energy to melt the stem.' },
    { id: 'A_REJ', duration: 1500, text: 'REJECTED: Key A dissociates.' },
    
    // Key B Sequence
    { id: 'B_APP', duration: 1500, text: 'AND TEST: Key B (Target 2) approaches toehold.' },
    { id: 'B_FAIL', duration: 2500, text: 'INSUFFICIENT: Key B alone lacks energy to melt the stem.' },
    { id: 'B_REJ', duration: 1500, text: 'REJECTED: Key B dissociates.' },
    
    // Success Sequence
    { id: 'BOTH_APP', duration: 2000, text: 'COOPERATIVE: Both keys dock simultaneously.' },
    { id: 'UNLOCK', duration: 2500, text: 'UNLOCKED: Dual hybridization energy melts the stem.' },
    { id: 'TRANSLATE', duration: 6000, text: `TRANSLATING: Ribosome synthesizes ${output.name} output.` },
    { id: 'RESET', duration: 1500, text: 'Resetting logic gate...' }
  ];

  const orPhases = [
    { id: 'LOCKED', duration: 2000, text: 'LOCKED: Stem-loop structure blocks the Ribosome Binding Site.' },
    
    // Wrong Key Sequence
    { id: 'WRONG_APP', duration: 1500, text: 'TEST: Non-target RNA approaches.' },
    { id: 'WRONG_FAIL', duration: 2500, text: 'MISMATCH: Sequence fails to hybridize. Thermodynamic clash.' },
    { id: 'WRONG_REJ', duration: 1500, text: 'REJECTED: Non-target RNA dissociates.' },
    
    // Key A Sequence
    { id: 'A_APP', duration: 1500, text: 'OR TEST: Key A approaches toehold.' },
    { id: 'A_UNLOCK', duration: 2500, text: 'SUCCESS: Key A alone possesses energy to melt the stem.' },
    { id: 'A_TRANS', duration: 6000, text: `TRANSLATING: Ribosome synthesizes ${output.name} via Key A.` },
    { id: 'A_RESET', duration: 1500, text: 'Resetting...' },
    
    // Key B Sequence
    { id: 'B_APP', duration: 1500, text: 'OR TEST: Key B approaches toehold.' },
    { id: 'B_UNLOCK', duration: 2500, text: 'SUCCESS: Key B alone possesses energy to melt the stem.' },
    { id: 'B_TRANS', duration: 6000, text: `TRANSLATING: Ribosome synthesizes ${output.name} via Key B.` },
    { id: 'RESET', duration: 1500, text: 'Resetting logic gate...' }
  ];

  const activePhases = gateType === 'AND' ? andPhases : orPhases;

  useEffect(() => {
    onPhaseChange(activePhases[phase].text);
  }, [phase, gateType]);

  // Clean, self-contained playback loop triggered directly by React standard lifecycle
  useEffect(() => {
    if (isPaused) {
      if (timerRef.current) clearTimeout(timerRef.current);
      return;
    }

    const runStep = () => {
      const currentDuration = activePhases[phaseRef.current].duration / playbackSpeed;
      timerRef.current = setTimeout(() => {
        const nextPhase = (phaseRef.current + 1) % activePhases.length;
        phaseRef.current = nextPhase;
        setPhase(nextPhase);
        runStep();
      }, currentDuration);
    };

    runStep();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [playbackSpeed, isPaused, gateType]);

  // Structural checks based on strictly mapped phases
  const getIsUnlocked = () => {
    if (gateType === 'AND') return phase === 11 || phase === 12; // UNLOCK, TRANSLATE
    return (phase === 5 || phase === 6) || (phase === 9 || phase === 10); // A_UNLOCK, A_TRANS or B_UNLOCK, B_TRANS
  };

  const getIsTranslating = () => {
    if (gateType === 'AND') return phase === 12;
    return phase === 6 || phase === 10;
  };

  const isUnlocked = getIsUnlocked();
  const isTranslating = getIsTranslating();

  const rbsPos = isUnlocked ? { x: 445, y: 300 } : { x: 280, y: 115 };
  const startPos = isUnlocked ? { x: 560, y: 300 } : { x: 310, y: 220 };
  
  const pathD = isUnlocked
    ? "M 50 300 L 250 300 L 400 300 C 430 300, 460 300, 490 300 L 640 300 L 850 300"
    : "M 50 300 L 250 300 L 250 150 C 250 80, 310 80, 310 150 L 310 300 L 750 300";

  // Coordinates mapping based on the active phase
  const getKeyPositions = () => {
    let wrongKey = { x: 100, y: 150, opacity: 0, clashing: false };
    let key1 = { x: 50, y: 150, opacity: 0, clashing: false };
    let key2 = { x: 150, y: 150, opacity: 0, clashing: false };

    if (gateType === 'AND') {
      switch (phase) {
        case 1: wrongKey = { x: 100, y: 286, opacity: 1, clashing: false }; break; // Approach (smoothly sits)
        case 2: wrongKey = { x: 100, y: 286, opacity: 1, clashing: true }; break; // Fail (sits and wiggles)
        case 3: wrongKey = { x: 100, y: 150, opacity: 0, clashing: false }; break; // Retreat
        case 4: key1 = { x: 50, y: 286, opacity: 1, clashing: false }; break;
        case 5: key1 = { x: 50, y: 286, opacity: 1, clashing: true }; break;
        case 6: key1 = { x: 50, y: 150, opacity: 0, clashing: false }; break;
        case 7: key2 = { x: 150, y: 286, opacity: 1, clashing: false }; break;
        case 8: key2 = { x: 150, y: 286, opacity: 1, clashing: true }; break;
        case 9: key2 = { x: 150, y: 150, opacity: 0, clashing: false }; break;
        case 10: 
        case 11: 
        case 12: // Keys stay exactly at 100% opacity during translation
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
        case 6: // Key stays exactly at 100% opacity during translation
          key1 = { x: 100, y: 286, opacity: 1, clashing: false }; 
          break;
        case 7: key1 = { x: 100, y: 150, opacity: 0, clashing: false }; break;
        case 8:
        case 9:
        case 10: // Key stays exactly at 100% opacity during translation
          key2 = { x: 100, y: 286, opacity: 1, clashing: false }; 
          break;
        default: break;
      }
    }
    return { wrongKey, key1, key2 };
  };

  const { wrongKey, key1, key2 } = getKeyPositions();
  
  // Show clash strictly during the designated "FAIL" holding phases
  const showClash = gateType === 'AND' ? (phase === 2 || phase === 5 || phase === 8) : (phase === 2);

  const riboOp = isUnlocked ? 1 : 0;
  const riboX = isTranslating ? 760 : 445;
  const outScale = isTranslating ? 1.6 : 0;
  const outY = isTranslating ? 180 : 280;

  return (
    <div className="flex flex-col gap-5 w-full max-w-5xl mx-auto">
      <style>{`
        @keyframes wiggle {
          0%, 100% { transform: translate(0px, 0px) rotate(0deg); }
          15% { transform: translate(-3px, 0px) rotate(-0.5deg); }
          30% { transform: translate(3px, 0px) rotate(0.5deg); }
          45% { transform: translate(-2px, 0px) rotate(-0.5deg); }
          60% { transform: translate(2px, 0px) rotate(0.5deg); }
        }
        .animate-wiggle { animation: wiggle 0.25s ease-in-out infinite; }
        
        .cyber-grid {
          background-image: linear-gradient(rgba(56, 189, 248, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(56, 189, 248, 0.05) 1px, transparent 1px);
          background-size: 30px 30px;
        }
      `}</style>

      {/* --- TOP HUD BANNER --- */}
      <div className="bg-slate-900/90 border border-slate-700/50 px-6 py-4 rounded-xl shadow-lg flex items-center gap-4 backdrop-blur-sm">
        <div className="flex items-center gap-2 border-r border-slate-700 pr-4">
          <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_10px_#22d3ee] animate-pulse"></div>
          <span className="text-cyan-400 text-xs font-mono font-bold tracking-widest">{gateType}_GATE</span>
        </div>
        <p className="text-slate-200 font-mono text-sm tracking-wide flex-1">{activePhases[phase].text}</p>
      </div>

      {/* --- MAIN SVG CANVAS --- */}
      <div className="relative w-full aspect-[16/10] bg-[#0a0f18] rounded-xl overflow-hidden border border-slate-800 shadow-2xl">
        <div className="absolute inset-0 cyber-grid" />
        
        {/* Corner Brackets */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          <path d="M 15 30 L 15 15 L 30 15" fill="none" stroke="#38bdf8" strokeWidth="2" opacity="0.3" />
          <path d="M 835 30 L 835 15 L 820 15" fill="none" stroke="#38bdf8" strokeWidth="2" opacity="0.3" />
          <path d="M 15 370 L 15 385 L 30 385" fill="none" stroke="#38bdf8" strokeWidth="2" opacity="0.3" />
          <path d="M 835 370 L 835 385 L 820 385" fill="none" stroke="#38bdf8" strokeWidth="2" opacity="0.3" />
        </svg>

        <svg viewBox="0 0 850 400" className="w-full h-full relative z-10">
          <defs>
            {/* Use userSpaceOnUse for gradient coordinates to completely resolve the 0-height SVG path bug 
              occurring on flat/unlocked horizontal configurations!
            */}
            <linearGradient id="strandGrad" x1="50" y1="300" x2="850" y2="300" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#475569" />
              <stop offset="30%" stopColor="#94a3b8" />
              <stop offset="70%" stopColor="#94a3b8" />
              <stop offset="100%" stopColor="#475569" />
            </linearGradient>
            
            <filter id="neonGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* --- MAIN mRNA STRAND --- */}
          <path 
            d={pathD} 
            stroke="url(#strandGrad)" 
            strokeWidth="4" 
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none" 
            style={{ transition: 'all 2.0s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
          />

          {/* Stem Base-Pairing Bonds */}
          <g style={{ opacity: isUnlocked ? 0 : 1, transition: 'opacity 0.6s' }} stroke="#f43f5e" strokeWidth="1.5" strokeDasharray="2, 4">
            <line x1="260" y1="280" x2="300" y2="280" />
            <line x1="260" y1="250" x2="300" y2="250" />
            <line x1="260" y1="220" x2="300" y2="220" />
            <line x1="260" y1="190" x2="300" y2="190" />
            <line x1="260" y1="160" x2="300" y2="160" />
          </g>

          {/* RBS Site */}
          <g style={{ transform: `translate(${rbsPos.x}px, ${rbsPos.y}px)`, transition: 'all 2.0s cubic-bezier(0.34, 1.56, 0.64, 1)' }}>
            <circle cx="0" cy="0" r="8" fill="#f59e0b" filter="url(#neonGlow)" />
            <circle cx="0" cy="0" r="3" fill="#fff" opacity="0.9" />
            <text x="0" y="-14" fill="#fcd34d" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" letterSpacing="1">RBS</text>
          </g>

          {/* Start Codon */}
          <g style={{ transform: `translate(${startPos.x}px, ${startPos.y}px)`, transition: 'all 2.0s cubic-bezier(0.34, 1.56, 0.64, 1)' }}>
            <polygon points="-7,-7 8,0 -7,7" fill="#10b981" filter="url(#neonGlow)" />
            <text x="0" y="-14" fill="#6ee7b7" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" letterSpacing="1">START</text>
          </g>

          {/* Toehold Landing Pad Indicator */}
          <line x1="50" y1="300" x2="250" y2="300" stroke="#38bdf8" strokeWidth="10" strokeLinecap="round" opacity="0.1" />
          <line x1="50" y1="308" x2="250" y2="308" stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" opacity="0.3" />
          <text x="150" y="322" fill="#38bdf8" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" letterSpacing="2">TOEHOLD_DOMAIN</text>

          {/* Output Region Indicator */}
          <text x="750" y="322" fill="#94a3b8" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" letterSpacing="2" style={{ transition: 'opacity 2.0s', opacity: isUnlocked ? 1 : 0 }}>{output.name.toUpperCase()}_CDS</text>

          {/* --- HIGH VISIBILITY THERMODYNAMIC CLASH --- */}
          <g 
            style={{ 
              opacity: showClash ? 1 : 0,
              transform: `translate(150px, 300px) scale(${showClash ? 1 : 0.8})`,
              transition: showClash ? 'all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.2)' : 'all 0.2s ease'
            }}
          >
            <circle cx="0" cy="0" r="30" fill="none" stroke="#ef4444" strokeWidth="1" className="animate-ping" opacity="0.6" />
            <rect x="-18" y="-8" width="36" height="16" rx="4" fill="#7f1d1d" stroke="#ef4444" strokeWidth="1" filter="url(#neonGlow)" />
            <text x="0" y="3" fill="#fff" fontSize="9" fontFamily="monospace" fontWeight="bold" textAnchor="middle">FAIL</text>
          </g>

          {/* --- MOLECULAR KEYS --- */}
          <RNAKeyIcon color="#ef4444" name="Off-Target" x={wrongKey.x} y={wrongKey.y} opacity={wrongKey.opacity} isClashing={wrongKey.clashing} />
          <RNAKeyIcon color={keys[0].color} name={keys[0].name} x={key1.x} y={key1.y} opacity={key1.opacity} isClashing={key1.clashing} />
          {keys[1] && <RNAKeyIcon color={keys[1].color} name={keys[1].name} x={key2.x} y={key2.y} opacity={key2.opacity} isClashing={key2.clashing} />}

          {/* --- RIBOSOME ASSEMBLY (Sleeker, Capsule Design) --- */}
          <g style={{ transform: `translate(${riboX}px, 300px)`, opacity: riboOp, transition: `transform ${isTranslating ? 6.0 / playbackSpeed : 1.5 / playbackSpeed}s linear, opacity 1s` }}>
            <g filter="drop-shadow(0 10px 10px rgba(0,0,0,0.4))">
              {/* Large Subunit (60S) */}
              <path d="M -45 -8 L -35 -35 L 35 -35 L 45 -8 C 45 5, -45 5, -45 -8" fill="#1e293b" stroke="#475569" strokeWidth="1" opacity="0.95" />
              {/* Small Subunit (40S) */}
              <path d="M -30 8 C -30 25, 30 25, 30 8 C 30 -2, -30 -2, -30 8" fill="#0f172a" stroke="#475569" strokeWidth="1" opacity="0.95" />
              {/* Active Center Glow */}
              <circle cx="0" cy="0" r="4" fill="#38bdf8" filter="url(#neonGlow)" opacity={isTranslating ? 1 : 0.2} />
              <text x="0" y="-42" fill="#94a3b8" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" letterSpacing="1">RIBOSOME</text>
            </g>
          </g>

          {/* --- TRANSLATED PROTEIN (Output) --- */}
          <g style={{ transform: `translate(${riboX}px, ${outY}px) scale(${outScale})`, opacity: outScale > 0 ? 1 : 0, transition: `transform ${isTranslating ? 6.0 / playbackSpeed : 0.5 / playbackSpeed}s linear, opacity 1s` }}>
            <polygon points="0,-14 12,-6 12,8 0,16 -12,8 -12,-6" fill={output.color} filter="url(#neonGlow)" />
            <circle cx="0" cy="1" r="3" fill="#ffffff" opacity="0.7" />
            <text x="0" y="-20" fill={output.color} fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle" filter="url(#neonGlow)">{output.name}</text>
          </g>
        </svg>
      </div>
    </div>
  );
};


// --- PLASMID DESIGNS SPECS ---
const PLASMID_REGISTRY = [
  {
    id: "Plasmid-AND",
    title: "AND GATE",
    gateType: "AND",
    keys: [
      { name: 'Target-A: miR-21', color: '#06b6d4' },
      { name: 'Target-B: miR-122', color: '#d946ef' }
    ],
    output: { name: 'mCherry', color: '#f43f5e' }
  },
  {
    id: "Plasmid-OR",
    title: "OR GATE",
    gateType: "OR",
    keys: [
      { name: 'Target-A: Hepato-A', color: '#06b6d4' },
      { name: 'Target-B: Hepato-B', color: '#d946ef' }
    ],
    output: { name: 'GFP', color: '#4ade80' }
  }
];

// --- MAIN DEMO WRAPPER ---
export default function App() {
  const [selectedPlasmidIndex, setSelectedPlasmidIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [isPaused, setIsPaused] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [triggerReset, setTriggerReset] = useState(0);

  const activePlasmid = PLASMID_REGISTRY[selectedPlasmidIndex];

  const handleRestart = () => {
    setTriggerReset(prev => prev + 1);
  };

  return (
    <div className="min-h-screen bg-slate-950 p-6 flex flex-col items-center justify-center font-sans">
      
      {/* Minimalistic Circuit Switcher for Demo Purposes */}
      <div className="mb-8 flex bg-slate-900 p-1.5 rounded-xl border border-slate-800">
        {PLASMID_REGISTRY.map((plasmid, index) => (
          <button
            key={plasmid.id}
            onClick={() => { setSelectedPlasmidIndex(index); handleRestart(); }}
            className={`px-6 py-2 text-xs font-bold rounded-lg tracking-widest transition-all uppercase ${selectedPlasmidIndex === index ? 'bg-cyan-500 text-slate-950 shadow-[0_0_15px_rgba(6,182,212,0.4)]' : 'text-slate-400 hover:text-white'}`}
          >
            {plasmid.title}
          </button>
        ))}
      </div>

      {/* Idiomatic React rendering technique: keying by gateType and triggerReset cleanly 
        unmounts/remounts the animation. This prevents memory leaks, clears any active timers, 
        and resets the biophysical logic sequence perfectly to State 0.
      */}
      <ToeholdWidget 
        key={`${activePlasmid.gateType}-${triggerReset}`}
        gateType={activePlasmid.gateType} 
        keys={activePlasmid.keys} 
        output={activePlasmid.output}
        playbackSpeed={playbackSpeed}
        setPlaybackSpeed={setPlaybackSpeed}
        isPaused={isPaused}
        onPhaseChange={setStatusMessage}
        triggerResetKey={handleRestart}
      />

      {/* --- BOTTOM CONTROLS --- */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-3 rounded-xl mt-5 w-full max-w-5xl mx-auto">
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setIsPaused(!isPaused)} 
            className="flex items-center gap-2 px-6 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-bold transition-all border border-slate-700"
          >
            {isPaused ? <Play className="w-3.5 h-3.5 text-emerald-400 fill-emerald-400" /> : <Pause className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />}
            {isPaused ? 'RESUME' : 'PAUSE'}
          </button>
          
          <button 
            onClick={handleRestart} 
            className="flex items-center gap-2 px-4 py-2 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg text-xs font-bold transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            RESTART
          </button>
        </div>

        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <span className="text-[10px] uppercase font-bold text-slate-500 px-3 tracking-widest font-mono">Speed:</span>
          {[
            { label: '0.5X', value: 0.5 },
            { label: '1.0X', value: 1.0 },
            { label: '2.0X', value: 2.0 }
          ].map((speedOpt) => (
            <button
              key={speedOpt.value}
              onClick={() => setPlaybackSpeed(speedOpt.value)}
              className={`px-3 py-1 text-xs font-bold rounded transition-all font-mono ${playbackSpeed === speedOpt.value ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
            >
              {speedOpt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}