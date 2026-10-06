"""Step 2, walked on one real PFAS trigger pair: what the switch is made of, base by base.

Step 1 answers WHICH pairs exist. Step 2 builds a switch from a pair, and this prints the
construction so it can be CHECKED rather than believed:

  * the pair's two windows, with their coordinates in their own transcripts
  * the assertion CLAUDE.md section 6 asks for: transcript[start:end] == the window
  * every domain of the assembled switch, with its span and its bases
  * for each domain, WHERE those bases come from -- a transcript slice, the reverse
    complement of one, or a fixed constant
  * which domains are untouchable gene bases and which a lever may still move

Nothing here is a new measurement; it reads the engine's own `find_cross_gene_pairs`,
`secondary_stems` and `assemble`.
"""

import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Dell\source\repos\cernal_software")
sys.path.insert(0, str(ROOT / "src"))

from engine import sequences as sq  # noqa: E402
from engine.domain import Constraints, Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

GENES = {"ggt": "b3447", "fadB": "b3846", "astC": "b1748", "aldA": "b1415"}

book = load_transcriptome(Host.ECOLI)
print(f"transcriptome: {len(book):,} transcripts (CDS only -- no UTRs, no operon context)")
for symbol, bnum in GENES.items():
    seq = book.get(bnum)
    print(f"  {symbol:6s} {bnum}  {len(seq) if seq else 0:>6,} nt")

a_sym, b_sym = "ggt", "fadB"
ta, tb = sq.to_rna(book[GENES[a_sym]]), sq.to_rna(book[GENES[b_sym]])

gate = ProkaryoticToeholdAndGate(
    host=Host.ECOLI,
    folder=FoldEngine(),
    translation=TranslationScorer(Host.ECOLI),
    codons=CodonOptimizer(Host.ECOLI),
)
print(f"\ngate {type(gate).__name__} v{gate.version}")
print(
    f"  ARM_LEN {gate.ARM_LEN}  SECONDARY_INVASION_LEN {gate.SECONDARY_INVASION_LEN}  "
    f"TOEHOLD_B_LEN {gate.TOEHOLD_B_LEN}  MIN_OVERLAP {gate.MIN_OVERLAP}"
)
print(f"  role_footprints = {gate.role_footprints()}  [A footprint, B footprint]")

pairs = list(gate.find_cross_gene_pairs(a_sym, ta, b_sym, tb))
counts: dict[int, int] = {}
for p in pairs:
    counts[p.len_x] = counts.get(p.len_x, 0) + 1
print(f"\nSTEP 1 on {a_sym} x {b_sym}: {len(pairs):,} pairs, both role assignments")
print("  len_x -> pairs:", dict(sorted(counts.items())))

pair = sorted(pairs, key=lambda p: (-p.len_x, p.x_start, p.xstar_start))[0]
# Slice each window from ITS OWN gene, looked up by name. Half of these pairs come from
# `swapped()`, where gene_a is the gene that was passed as B -- so using the call's own `ta`/`tb`
# positionally reads the WRONG MOLECULE for every swapped pair. The revcomp(x) == x* check below
# is what caught that, on the first run of this script.
book_rna = {a_sym: ta, b_sym: tb}
src_a, src_b = book_rna[pair.gene_a], book_rna[pair.gene_b]
wa, wb = pair.window_a(), pair.window_b()
window_a, window_b = src_a[wa[0] : wa[1]], src_b[wb[0] : wb[1]]
print(f"\nthe pair walked below: len_x {pair.len_x}, A = {pair.gene_a}, B = {pair.gene_b}")
print(f"  window A  [{wa[0]}, {wa[1]})  {wa[1] - wa[0]:>2} nt   {window_a}")
print(f"  window B  [{wb[0]}, {wb[1]})  {wb[1] - wb[0]:>2} nt   {window_b}")
print(f"  len_k2 (B's invasion 5' of the overlap) = {pair.len_k2}")

assert src_a[wa[0] : wa[0] + len(window_a)] == window_a, "window A is not its own coordinates"
assert src_b[wb[0] : wb[0] + len(window_b)] == window_b, "window B is not its own coordinates"
print("  coordinates assert clean (0-based, inclusive start, exclusive end)")

x = src_a[pair.x_start : pair.x_start + pair.len_x]
xs = src_b[pair.xstar_start : pair.xstar_start + pair.len_x]
print(f"\n  the overlap:  x  = {x}   in {pair.gene_a} at {pair.x_start}")
print(f"                x* = {xs}   in {pair.gene_b} at {pair.xstar_start}")
_ok = sq.reverse_complement(x) == xs
print(f"                revcomp(x) == x* ?  {_ok}")
if not _ok:
    raise SystemExit("  NOT reverse-complementary -- stopping; this is a fault, not a detail")

stems = gate.secondary_stems(window_a, window_b, pair.len_x)
print(f"\nSTEP 2a -- secondary stems offered for this pair: {len(stems)}")
for i, st in enumerate(stems[:8]):
    shown = f"{st.lock_energy:.2f}" if st.lock_energy is not None else "None"
    print(f"  [{i}] scheme {st.scheme:14s}lock {shown:>7s} kcal/mol")
usable = [s for s in stems if (s.lock_energy or 0.0) <= 0.0]
print(
    f"  usable (lock_energy <= 0 -- a positive lock is not a lock): {len(usable)} of {len(stems)}"
)
if not usable:
    print("  nothing to assemble on this pair; stopping rather than inventing a stem")
    raise SystemExit(0)

stem = min(usable, key=lambda s: s.lock_energy)
built = gate.assemble(window_a, window_b, pair.len_x, stem)
print(f"\nSTEP 2b -- assembled switch: {len(built.sequence)} nt")
print(f"  {built.sequence}")
print(f"  {built.dot_bracket}")

CONSTANTS = {
    "cap": "LEADER_SEQUENCE",
    "secondary_loop": "SECONDARY_LOOP",
    "rbs_loop": "RBS_FLANK + RBS_CORE",
    "aug": "the start codon",
    "linker": "LINKER_SEQUENCE",
}


def origin(name: str, bases: str) -> str:
    """Where these bases come from -- the distinction that decides what can be edited."""
    if name in CONSTANTS:
        return f"constant ({CONSTANTS[name]})"
    for label, source in ((pair.gene_a, window_a), (pair.gene_b, window_b)):
        if bases and bases in source:
            return f"{label} window, FORWARD -- gene bases, not editable"
        if bases and sq.reverse_complement(bases) in source:
            return f"revcomp of the {label} window -- synthetic, a lever may move it"
    return "derived"


print(f"\n  {'domain':16s}{'span':>12s}{'nt':>4s}  {'bases':<36s}origin")
total = 0
for name, (start, end) in built.domains.items():
    bases = built.sequence[start:end]
    total += end - start
    print(
        f"  {name:16s}{f'[{start},{end})':>12s}{end - start:>4d}  {bases:<36s}{origin(name, bases)}"
    )
print(f"  {'':32s}{total:>4d}  domains cover {total} of {len(built.sequence)} nt")

rebuilt = "".join(built.sequence[s:e] for s, e in built.domains.values())
print(f"\n  the domains concatenate back to the switch ?  {rebuilt == built.sequence}")

# ---------------------------------------------------------------------------------------------
# STEP 2c -- the screens that act on this pair, and what they say about it.
print("\nSTEP 2c -- the screens on this pair")
main_pre = built.sequence[slice(*built.domains["main_pre"])]
codons = [main_pre[i : i + 3] for i in (0, 3, 6)]
print(f"  main_pre = {main_pre}  -> codons after the AUG: {' '.join(codons)}")
print(f"  stop codons among them: {[c for c in codons if c in sq.STOP_CODONS] or 'none'}")
print(f"  rare codons among them: {[c for c in codons if c in gate.RARE_CODONS] or 'none'}")
print(f"  stop_rescue_cost(main_pre) = {gate.stop_rescue_cost(main_pre)}  (wobble substitutions)")
screened = gate.screen_trigger_pair(window_a, window_b, main_pre)
print(f"  screen_trigger_pair(A, B, main_pre) = {screened}")
print(f"  assembly_violations(switch) = {gate.assembly_violations(built)}")
print(f"  rnase_e_sites in window B: {len(gate.rnase_e_sites(window_b))} site(s)")

# How often this is the situation, over every pair of this gene pair -- n beside the rate.
priced, free = 0, 0
for p in pairs:
    # `main_pre` is the 9 nt immediately 5' of the overlap in trigger A, which in the finished
    # switch becomes codons 2 to 4 of the reporter -- so this is where a gene's own stop lands
    # in OUR reading frame. Read from the A gene by name: half these pairs are swapped.
    pre = book_rna[p.gene_a][p.x_start - 9 : p.x_start]
    cost = gate.stop_rescue_cost(pre)
    if cost is None:
        continue
    if cost == 0:
        free += 1
    else:
        priced += 1
n = priced + free
print(f"\n  over all {n:,} pairs of {a_sym} x {b_sym} with a readable main_pre:")
print(f"    no in-frame stop        {free:>6,}  ({100.0 * free / n:.1f}%)")
print(f"    stop, wobble-rescuable  {priced:>6,}  ({100.0 * priced / n:.1f}%)")

# STEP 2d -- the levers `generate_designs` sweeps, and the size of the space they define.
print("\nSTEP 2d -- the levers, and what they cost to enumerate")
print(f"  CLOSURES {len(gate.CLOSURES)}   UPPER3 {len(gate.UPPER3)}   LOWER3 {len(gate.LOWER3)}")
print(f"    upper3 levels: {[name for name, _ in gate.UPPER3]}")
print(f"    lower3 levels: {[name for name, _ in gate.LOWER3]}")
grid = len(gate.CLOSURES) * len(gate.UPPER3) * len(gate.LOWER3)
print(f"  grid per (pair, stem) = {grid}")
print("  A-anchored and unlocked schemes are excluded in generate_designs, measured dead")

# The budget, which has to be stated rather than discovered. `Constraints` carries
# `stems_per_pair` but has NO field for how many PAIRS of a gene pair to carry, and that is the
# factor that decides whether the run is hours or weeks.
limits = Constraints()
print(
    f"\n  Constraints: stems_per_pair {limits.stems_per_pair}  "
    f"min_window_gap {limits.min_window_gap}  overlap_range {limits.overlap_range}"
)
per_pair = grid * limits.stems_per_pair
total_designs = per_pair * len(pairs)
print(f"  designs per trigger pair = {per_pair}")
print(f"  x {len(pairs):,} pairs on this ONE gene pair = {total_designs:,} designs")
print(
    f"  at the measured ~0.3 s per design after the ON ceiling: "
    f"{total_designs * 0.3 / 3600:,.0f} core-hours -- so the cap must be DECLARED, not discovered"
)
