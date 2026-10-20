"""Portable pair-budget inspection and bounded equilibrium pilot on pinned E. coli RNA.

    python tools/pair_budget_on_pfas.py
    python tools/pair_budget_on_pfas.py --pilot --pairs 1 --stems 1 \
        --assignment-budget 1000 --accessible-fraction .25 --seed 7 \
        --out var/prokaryotic-and-pilot.json
    python tools/pair_budget_on_pfas.py --pipeline --max-designs 20 --max-pairs 8
    python tools/pair_budget_on_pfas.py --pipeline --pipeline-output gfp

Fractions and compute limits are engineering experiments, not biological thresholds.
Pair ranking uses the weaker window's mean unpaired probability by default; --pair-key
minimum compares the alternative minimum-per-base rule. Both statistics are retained.
All 22 shared structural checks apply. No thresholds are fitted. The pilot evaluates isolated
switches unless --payload is supplied; it excludes application/worker overhead.
The --pipeline mode instead measures the complete application compiler, including
its declared prefix screen and full-output verification of passing finalists.
"""

import argparse
import dataclasses
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine import sequences as sq  # noqa: E402
from engine.artifacts import sha256_bytes, write_artifact  # noqa: E402
from engine.client import LocalEngine, validate_job_configuration  # noqa: E402
from engine.contract import INPUT_DE, SCHEMA_VERSION, JobRequest  # noqa: E402
from engine.domain import (  # noqa: E402
    AssemblyStandard,
    Constraints,
    DesiredOutcome,
    Host,
    TriggerCandidate,
    TriggerSet,
)
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402
from engine.stages.folding import FoldProfiler  # noqa: E402
from engine.stages.motifs import MotifScreener  # noqa: E402
from engine.stages.plasmids import PAYLOADS, validate_payload_cds  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

PAIRS = (("ggt", "b3447", "fadB", "b3846"), ("ggt", "b3447", "astC", "b1748"))


def candidate(gene, sequence, start, profile):
    """Carry exact upstream statistics; isolated MFE was not measured here."""
    local = profile[start : start + len(sequence)]
    return TriggerCandidate(
        trigger_id=f"{gene}:{start}:{len(sequence)}",
        gene_id=gene,
        symbol=gene,
        sequence=sequence,
        start_index=start,
        openness=statistics.fmean(local),
        accessibility=min(local),
        mfe=None,
        gc_content=sq.gc_content(sequence),
    )


def choose(records, count, policy, fraction, seed):
    """Select paired windows; seeded sampling stays inside the declared subset."""
    if policy == "top":
        return records[:count]
    pool = records[: max(count, math.ceil(len(records) * fraction))]
    return random.Random(seed).sample(pool, min(count, len(pool)))


def historical_positive(gate, sources, profiles):
    """Reconstruct a historical positive, not an unbiased selection-policy result.

    Coordinates/energies identify a 22-pass row from axes_c8_0.csv. The full shared
    solver reconstructs it from pinned references; the large CSV is not required.
    """
    a = candidate("ggt", sources["ggt"][1678:1714], 1678, profiles["ggt"])
    b = candidate("astC", sources["astC"][637:687], 637, profiles["astC"])
    with (
        patch.object(gate, "max_secondary_assignments", None),
        patch.object(gate, "max_variable_conflicts", None),
    ):
        tick = time.perf_counter()
        stems = gate.secondary_stems(a.sequence, b.sequence, 6)
        stem_seconds = time.perf_counter() - tick
        expected = (-17.600000381469727, -18.700000762939453, -20.700000762939453)
        stem = next(
            stem
            for stem in stems
            if all(
                math.isclose(got, want, abs_tol=1e-5)
                for got, want in zip(
                    (stem.lock_energy, stem.a_site_energy, stem.b_site_energy),
                    expected,
                    strict=True,
                )
            )
        )
        constraints = Constraints(stems_per_pair=1, stem_order="front", closure_set="chosen")
        with patch.object(gate, "secondary_stems", lambda *_args, **_kwargs: [stem]):
            designs = list(gate.generate_designs(TriggerSet((a, b)), constraints))
        design = next(
            d
            for d in designs
            if d.architecture["closure"] == "trigger_derived"
            and d.architecture["upper3"] == "WWW_AUA"
            and d.architecture["lower3"] == "trigger_derived"
        )
    return design, stem_seconds


def regression_contexts(gate, sources, profiles):
    """Recheck the same reconstructed switch with three complete RNA contexts."""
    design, stem_seconds = historical_positive(gate, sources, profiles)
    rows = []
    for label, payload in (
        ("switch_only", ""),
        ("short_custom", "ATGGCTGCTTAA"),
        ("gfp", PAYLOADS[DesiredOutcome.GFP][1]),
    ):
        evaluated = (
            dataclasses.replace(
                design,
                architecture={
                    **design.architecture,
                    "evaluation_sequence": design.sequence + sq.to_rna(payload)[3:],
                },
            )
            if payload
            else design
        )
        tick = time.perf_counter()
        raw = gate.measure_design(evaluated, on_ceiling=7.2, compute_barrier=False)
        elapsed = time.perf_counter() - tick
        violations = gate.gate_violations(raw)
        rows.append(
            {
                "context": label,
                "seconds": elapsed,
                "evaluated_nt": len(
                    evaluated.architecture.get("evaluation_sequence", design.sequence)
                ),
                "sequence_sha256": sha256_bytes(design.sequence.encode()),
                "architecture": dict(design.architecture),
                "raw": raw,
                "violations": violations,
                "secondary_seconds": stem_seconds,
                "selection": "historical positive regression; not general-policy yield",
            }
        )
        print(
            f"Regression {label}: {elapsed:.3f}s, {len(violations)} structural violations",
            flush=True,
        )
    return rows


def pipeline_example(args):
    """Run the supported compiler on a named pair, without pinning any switch.

    The small custom CDS is a software test output, not a functional reporter.
    Generated artifacts stay under var/ unless --run-dir chooses another path.
    Sequence release uses the application's real fail-closed policy.
    """
    run_dir = args.run_dir or ROOT / "var" / f"prokaryotic-and-example-{args.pipeline_output}"
    content = (
        b"gene_id,base_expression,target_expression,log2fc,padj\n"
        b"b3447,1.0,8.0,3.0,0.001\n"
        b"b1748,1.0,6.0,2.585,0.002\n"
    )
    input_artifact = write_artifact(
        run_dir,
        "inputs.csv",
        content,
        kind="benchmark_input",
        media_type="text/csv",
        sequence_free=True,
    )
    payload = {"outputs": [args.pipeline_output]}
    if args.pipeline_output == "other":
        payload["custom_sequence"] = validate_payload_cds(
            "benchmark custom CDS", args.payload or "ATGGCTGCTTAA"
        )
    config = validate_job_configuration(
        {
            "payload": payload,
            "constraints": {"max_triggers": 2, "max_circuit_gates": 1},
            "and_inputs": {"gene_a": "b3447", "gene_b": "b1748"},
            "prokaryotic_and": {
                "max_pairs": args.max_pairs,
            },
            "budget": {"max_designs": args.max_designs},
        },
        ["prokaryotic_toehold_and"],
        "default",
        INPUT_DE,
        organism="ecoli",
    )
    request = JobRequest(
        schema_version=SCHEMA_VERSION,
        run_id="00000000-0000-4000-8000-000000000007",
        idempotency_key=f"prokaryotic-and-example-{args.pipeline_output}-{args.seed}",
        input_mode=INPUT_DE,
        trigger_sequence="",
        input_path=str(run_dir / "inputs.csv"),
        input_checksum=input_artifact.checksum_sha256,
        organism="ecoli",
        params=config,
        gate_families=["prokaryotic_toehold_and"],
        scoring_profile="default",
        seed=args.seed,
        output_dir=str(run_dir),
    )
    source_checksums = {
        str(path.relative_to(ROOT)): sha256_bytes(path.read_bytes())
        for path in (
            ROOT / "src/engine/pipeline.py",
            ROOT / "src/engine/domain.py",
            ROOT / "src/engine/client.py",
            ROOT / "src/engine/gates/toehold.py",
            ROOT / "src/engine/stages/switches.py",
            ROOT / "src/engine/stages/triggers.py",
        )
    }
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    started = time.perf_counter()
    progress_rows = []
    last_stage = None

    def progress(percent, stage):
        nonlocal last_stage
        elapsed = time.perf_counter() - started
        progress_rows.append({"elapsed_seconds": elapsed, "percent": percent, "stage": stage})
        if stage != last_stage:
            print(f"{elapsed:.3f}s {percent}% {stage}", flush=True)
            last_stage = stage
        return True

    result = LocalEngine().run(request, progress)
    elapsed = time.perf_counter() - started
    candidates = []
    for candidate_result in result.candidates:
        info = candidate_result.design.get("and_gate", {})
        architecture = candidate_result.design.get("architecture", {})
        candidates.append(
            {
                "ref": candidate_result.ref,
                "rank": candidate_result.rank,
                "is_rejected": candidate_result.is_rejected,
                "rejection_reason": candidate_result.rejection_reason,
                "switch_sequence_sha256": sha256_bytes(
                    candidate_result.design.get("switch_sequence", "").encode()
                ),
                "evaluation_context": info.get("evaluation_context"),
                "feasibility": info.get("feasibility"),
                "states": info.get("states"),
                "worst_off_state": info.get("worst_off_state"),
                "architecture": {
                    key: architecture.get(key)
                    for key in (
                        "gene_a",
                        "gene_b",
                        "len_x",
                        "closure",
                        "upper3",
                        "lower3",
                        "geometry",
                        "stem_index",
                        "secondary_search",
                    )
                },
                "metrics": [dataclasses.asdict(metric) for metric in candidate_result.metrics],
            }
        )
    summary = {
        "schema": "cernal-prokaryotic-and-pipeline-example-v1",
        "status": result.status,
        "revision": revision,
        "working_tree_changes_may_be_present": True,
        "error": result.error,
        "elapsed_seconds": elapsed,
        "selection": "supported complete pipeline; no pinned pair windows, stem or sequence",
        "sequence_release": "real fail-closed application policy; no test release adapter",
        "input_checksum": input_artifact.checksum_sha256,
        "config": config,
        "seed": args.seed,
        "scientific_provenance": result.scientific_provenance,
        "warnings": result.warnings,
        "candidates": candidates,
        "accepted": sum(not c.is_rejected for c in result.candidates),
        "ranked": sum(c.rank is not None for c in result.candidates),
        "artifacts": [dataclasses.asdict(artifact) for artifact in result.artifacts],
        "progress": progress_rows,
        "code_checksums_at_start": source_checksums,
    }
    out = args.out or run_dir / "benchmark-summary.json"
    artifact = write_artifact(
        out.parent,
        out.name,
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        kind="benchmark",
        media_type="application/json",
        sequence_free=True,
    )
    print(
        f"{result.status} in {elapsed:.3f}s; {len(candidates)} candidates, "
        f"{summary['accepted']} accepted, {summary['ranked']} ranked",
        flush=True,
    )
    print(f"Wrote {out}: SHA256 {artifact.checksum_sha256}", flush=True)
    return 0 if result.status == "succeeded" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--regression-contexts", action="store_true")
    mode.add_argument("--pipeline", action="store_true", help="run complete compiler on ggt/astC")
    parser.add_argument("--pipeline-output", choices=("other", "gfp"), default="other")
    parser.add_argument("--max-pairs", type=int, default=8, help="complete compiler pair budget")
    parser.add_argument("--max-designs", type=int, default=20)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--pairs", type=int, default=1, help="pairs per policy/gene pair/geometry")
    parser.add_argument("--stems", type=int, default=1, help="front-sampled stems per pair")
    parser.add_argument("--assignment-budget", type=int, default=1000)
    parser.add_argument("--accessible-fraction", type=float, default=0.25)
    parser.add_argument("--pair-key", choices=("mean", "minimum"), default="mean")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--payload", default="", help="optional output CDS appended for evaluation")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.pairs < 1 or args.stems < 1 or args.assignment_budget < 1:
        parser.error("pairs, stems and assignment-budget must be positive")
    if not 0 < args.accessible_fraction <= 1:
        parser.error("accessible-fraction must be in (0, 1]")
    if args.pipeline:
        return pipeline_example(args)
    if args.payload:
        args.payload = validate_payload_cds("pilot payload", args.payload)
    started = time.perf_counter()
    book = load_transcriptome(Host.ECOLI)
    folder, profiler = FoldEngine(cache_size=2000), FoldProfiler()
    screener = MotifScreener(AssemblyStandard.RFC10)
    translation, codons = TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    constraints = Constraints(stems_per_pair=args.stems, stem_order="front", closure_set="chosen")
    kwargs = (
        {
            "compute_barrier": False,
            "upper3_levels": ("trigger_derived", "WWW_AUA"),
            "max_secondary_assignments": args.assignment_budget,
            "seed": args.seed,
        }
        if args.pilot or args.regression_contexts
        else {}
    )
    gates = [
        cls(Host.ECOLI, folder, translation, codons, **kwargs)
        for cls in (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate)
    ]
    sources = {symbol: book[gene] for a, ai, b, bi in PAIRS for symbol, gene in ((a, ai), (b, bi))}
    tick = time.perf_counter()
    profiles = {gene: profiler.profile(sequence) for gene, sequence in sources.items()}
    profile_seconds = time.perf_counter() - tick
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    result = {
        "schema": "cernal-prokaryotic-and-pilot-v1",
        "revision": revision,
        "working_tree_changes_may_be_present": True,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "folding_model": folder.provenance(),
        "accessibility_definition": "per-window min per-base unpaired; retained independently",
        "pair_selection_key": f"weaker of the two windows' {args.pair_key} unpaired probability",
        "code_checksums": {
            str(path.relative_to(ROOT)): sha256_bytes(path.read_bytes())
            for path in (Path(__file__), ROOT / "src/engine/gates/toehold.py")
        },
        "source_checksums": {gene: sha256_bytes(seq.encode()) for gene, seq in sources.items()},
        "rnaplfold_seconds": profile_seconds,
        "on_ceiling_kcal_mol": 7.2,
        "on_ceiling_origin": "existing Wiki section 4.5 external single-input benchmark",
        "barrier_computed": False,
        "payload_context": sq.to_rna(args.payload) if args.payload else "isolated_switch",
        "cells": [],
        "designs": [],
    }
    print(f"RNAplfold for {len(profiles)} transcripts: {profile_seconds:.3f}s", flush=True)
    if args.regression_contexts:
        result["regression_contexts"] = regression_contexts(gates[0], sources, profiles)
    for a_sym, _a_id, b_sym, _b_id in PAIRS:
        if args.regression_contexts:
            break
        for gate in gates:
            tick = time.perf_counter()
            found = list(gate.find_cross_gene_pairs(a_sym, sources[a_sym], b_sym, sources[b_sym]))
            discovery_seconds = time.perf_counter() - tick
            records = []
            for pair in found:
                a0, a1 = pair.window_a()
                b0, b1 = pair.window_b()
                a = candidate(pair.gene_a, sources[pair.gene_a][a0:a1], a0, profiles[pair.gene_a])
                b = candidate(pair.gene_b, sources[pair.gene_b][b0:b1], b0, profiles[pair.gene_b])
                if screener.violations(a.sequence) or screener.violations(b.sequence):
                    continue
                key = (
                    min(a.openness, b.openness)
                    if args.pair_key == "mean"
                    else min(a.accessibility, b.accessibility)
                )
                records.append((key, pair, a, b))
            records.sort(
                key=lambda row: (-row[0], row[1].gene_a, row[1].x_start, row[1].xstar_start)
            )
            print(
                f"{a_sym}/{b_sym} {gate.geometry_name}: {len(found)} pairs, "
                f"{len(records)} pass source screen; discovery {discovery_seconds:.3f}s",
                flush=True,
            )
            if not args.pilot:
                result["cells"].append(
                    {
                        "gene_pair": [a_sym, b_sym],
                        "geometry": gate.geometry_name,
                        "discovered": len(found),
                        "source_screen_survivors": len(records),
                        "discovery_seconds": discovery_seconds,
                    }
                )
                continue
            for policy in ("top", "seeded"):
                selected = choose(records, args.pairs, policy, args.accessible_fraction, args.seed)
                for pair_index, (access, pair, a, b) in enumerate(selected):
                    cell = {
                        "gene_pair": [a_sym, b_sym],
                        "geometry": gate.geometry_name,
                        "policy": policy,
                        "pair_index": pair_index,
                        "roles": [a.gene_id, b.gene_id],
                        "starts": [a.start_index, b.start_index],
                        "overlap_nt": pair.len_x,
                        "pair_accessibility": access,
                        "window_mean_openness": [a.openness, b.openness],
                        "discovered": len(found),
                        "source_screen_survivors": len(records),
                        "discovery_seconds": discovery_seconds,
                        "secondary_seconds": 0.0,
                        "secondary_calls": 0,
                        "constructed": 0,
                        "assembly_rejected": 0,
                        "on_rejected": 0,
                        "four_state_evaluations": 0,
                        "feasible": 0,
                        "fold_seconds": 0.0,
                        "failures": Counter(),
                    }
                    secondary = gate.secondary_stems

                    def timed_secondary(*values, _secondary=secondary, _cell=cell, **keywords):
                        tick = time.perf_counter()
                        stems = _secondary(*values, **keywords)
                        _cell["secondary_seconds"] += time.perf_counter() - tick
                        _cell["secondary_calls"] += 1
                        return stems

                    tick = time.perf_counter()
                    with patch.object(gate, "secondary_stems", timed_secondary):
                        designs = list(gate.generate_designs(TriggerSet((a, b)), constraints))
                    cell["construction_seconds"] = time.perf_counter() - tick
                    cell["constructed"] = len(designs)
                    for design in designs:
                        faults = design.architecture.get("assembly_violations", ())
                        if faults:
                            cell["assembly_rejected"] += 1
                            cell["failures"].update(faults)
                            continue
                        if args.payload:
                            design = dataclasses.replace(
                                design,
                                architecture={
                                    **design.architecture,
                                    "evaluation_sequence": design.sequence
                                    + sq.to_rna(args.payload)[3:],
                                },
                            )
                        tick = time.perf_counter()
                        raw = gate.measure_design(design, on_ceiling=7.2, compute_barrier=False)
                        cell["fold_seconds"] += time.perf_counter() - tick
                        violations = gate.gate_violations(raw)
                        if raw.get("skipped") == "on_ceiling":
                            cell["on_rejected"] += 1
                        else:
                            cell["four_state_evaluations"] += 1
                            cell["feasible"] += not violations
                            cell["failures"].update(violations)
                        result["designs"].append(
                            {
                                "cell": len(result["cells"]),
                                "id": design.design_id,
                                "sequence_sha256": sha256_bytes(design.sequence.encode()),
                                "architecture": dict(design.architecture),
                                "raw": raw,
                                "violations": violations,
                            }
                        )
                    result["cells"].append(cell)
                    print(
                        f"  {policy} #{pair_index}: constructed={cell['constructed']} "
                        f"assembly_rejected={cell['assembly_rejected']} "
                        f"ON_rejected={cell['on_rejected']} "
                        f"four_state={cell['four_state_evaluations']} feasible={cell['feasible']} "
                        f"secondary={cell['secondary_seconds']:.3f}s "
                        f"fold={cell['fold_seconds']:.3f}s",
                        flush=True,
                    )
    result["elapsed_seconds"] = time.perf_counter() - started
    if args.out:
        artifact = write_artifact(
            args.out.parent,
            args.out.name,
            json.dumps(result, indent=2, allow_nan=False) + "\n",
            kind="benchmark",
            media_type="application/json",
        )
        print(f"Wrote {args.out}: SHA256 {artifact.checksum_sha256}", flush=True)
    print(f"Total elapsed: {result['elapsed_seconds']:.3f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
