"""Mathematical and integration checks, with real ViennaRNA; no experimental claims."""

import copy
import json
import math
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from engine import sequences as sq
from engine.domain import (
    Constraints,
    CrisprObjective,
    CrisprObservables,
    CrisprTemplate,
    Host,
    TriggerCandidate,
    TriggerSet,
)
from engine.gates.crispr import CrisprGate, scan_spacers
from engine.gates.tools.folding import FoldEngine
from engine.pipeline import run_crispr_workbench
from engine.scoring.crispr import calibrate_scale, inner_objective, outer_objective

ROOT = Path(__file__).resolve().parents[3]


def config():
    return json.loads((ROOT / "examples/crispr/demo.json").read_text())


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.p = CrisprObjective(**config()["objective"], scale_lambda=10)
        self.o = CrisprObservables(0.01, 0.8, 0.01, 0.01, -10)

    def test_hand_calculated_objective(self):
        # .5*10 + .5*10*(.4*.8-.6*.01) = 6.57
        self.assertAlmostEqual(inner_objective(self.o, self.p)["j"], 6.57)
        outer = outer_objective(8.95, 0.8, 0.1, 0.7, self.p)
        self.assertAlmostEqual(outer["q_spacer"], 0.86)
        self.assertAlmostEqual(outer["phi"], 8.95 * 0.796)

    def test_inclusive_accessibility_exclusive_defect_gates(self):
        o = replace(self.o, a_off=self.p.tau_off, a_on=self.p.tau_on)
        self.assertTrue(inner_objective(o, self.p)["feasible"])
        self.assertFalse(inner_objective(replace(o, d_on=self.p.epsilon), self.p)["feasible"])
        self.assertIsNone(inner_objective(replace(o, a_off=0.9), self.p)["j"])

    def test_selected_thresholds_and_explicit_overrides(self):
        self.assertEqual((self.p.tau_off, self.p.tau_on, self.p.epsilon), (0.05, 0.50, 0.10))
        boundary = replace(self.o, a_off=0.05, a_on=0.50, d_off=0.099, d_on=0.099)
        self.assertTrue(inner_objective(boundary, self.p)["feasible"])
        for changes in ({"a_off": 0.0501}, {"a_on": 0.4999}, {"d_off": 0.10}, {"d_on": 0.10}):
            with self.subTest(changes=changes):
                self.assertFalse(inner_objective(replace(boundary, **changes), self.p)["feasible"])
        overridden = CrisprObjective(
            **(config()["objective"] | {"tau_off": 0.1, "tau_on": 0.7, "epsilon": 0.2})
        )
        self.assertEqual(
            (overridden.tau_off, overridden.tau_on, overridden.epsilon), (0.1, 0.7, 0.2)
        )

    def test_all_failures_recorded(self):
        o = CrisprObservables(0.9, 0.01, 1, 1, -100)
        self.assertEqual(len(inner_objective(o, self.p)["rejections"]), 4)

    def test_bad_parameters_and_nan_rejected(self):
        for p in (
            replace(self.p, scale_lambda=-1),
            replace(self.p, w_energy=0.8),
            replace(self.p, epsilon=math.nan),
        ):
            with self.assertRaises(ValueError):
                inner_objective(self.o, p)
        with self.assertRaises(ValueError):
            inner_objective(replace(self.o, a_on=math.nan), self.p)

    def test_specificity_formula_and_nonnegative_switching_factor(self):
        for j, expected_phi in ((8.95, 7.1242), (0, 0), (-4, 0)):
            with self.subTest(j=j):
                result = outer_objective(j, 0.8, 0.1, 0.7, self.p)
                self.assertAlmostEqual(result["q_spacer"], 0.86)
                self.assertAlmostEqual(result["q_pair"], 0.796)
                self.assertAlmostEqual(result["phi"], expected_phi)
                self.assertEqual(result["j_positive"], max(0, j))
                self.assertEqual(result["rejections"], [])
                self.assertEqual(result["selectable"], j > 0)

    def test_outer_convex_bounds_and_specificity_monotonicity(self):
        from itertools import product

        for v, w, on, off, qt in product((0, 0.3, 1), (0, 0.7, 1), (0, 1), (0, 1), (0, 1)):
            p = replace(self.p, v_on=v, v_off=1 - v, w_spacer=w, w_trigger=1 - w, off_target_max=1)
            result = outer_objective(2, on, off, qt, p)
            self.assertTrue(0 <= result["q_spacer"] <= 1)
            self.assertTrue(0 <= result["q_pair"] <= 1)
            self.assertAlmostEqual(result["phi"], 2 * result["q_pair"])
        safer = outer_objective(2, 0.8, 0.1, 0.7, self.p)
        riskier = outer_objective(2, 0.8, 0.2, 0.7, self.p)
        self.assertGreater(safer["q_spacer"], riskier["q_spacer"])
        self.assertGreater(safer["phi"], riskier["phi"])

    def test_batch_scale_zero_energy_and_undefined_denominator(self):
        self.assertEqual(calibrate_scale([replace(self.o, dg_bind=0)], 0.4, 0.6), 0)
        with self.assertRaisesRegex(ValueError, "empty batch"):
            calibrate_scale([], 0.4, 0.6)
        with self.assertRaisesRegex(ValueError, "zero mean"):
            calibrate_scale([replace(self.o, a_on=0, a_off=0)], 0.4, 0.6)
        with self.assertRaisesRegex(ValueError, "Compute lambda"):
            inner_objective(self.o, replace(self.p, scale_lambda=None))
        self.assertEqual(inner_objective(self.o, replace(self.p, scale_lambda=0))["j"], 5)

    def test_external_scores_must_be_finite_and_normalized(self):
        for index in range(3):
            for invalid in (-0.001, 1.001, math.nan, math.inf):
                values = [0.8, 0.1, 0.7]
                values[index] = invalid
                with (
                    self.subTest(index=index, invalid=invalid),
                    self.assertRaisesRegex(ValueError, "External spacer/trigger metrics"),
                ):
                    outer_objective(2, *values, self.p)

    def test_offtarget_cannot_be_bought_back(self):
        self.assertIsNone(outer_objective(1000000, 1, 0.9, 1, self.p)["phi"])

    def test_calibration_degenerate_set(self):
        self.assertAlmostEqual(calibrate_scale([self.o], 1, 1), 10 / 0.79)
        with self.assertRaises(ValueError):
            calibrate_scale([replace(self.o, a_on=self.o.a_off)], 1, 1)


class ScanTests(unittest.TestCase):
    def test_both_strand_coordinates(self):
        dna = "AAAACAAAAGAAAACAAAAGTGG"
        plus = scan_spacers(dna, (0, 20))
        self.assertEqual([(s["start"], s["end"], s["strand"]) for s in plus], [(0, 20, "+")])
        reverse = sq.reverse_complement(dna, dna=True)
        minus = scan_spacers(reverse, (3, 23))
        self.assertEqual([(s["start"], s["end"], s["strand"]) for s in minus], [(3, 23, "-")])
        self.assertEqual(plus[0]["sequence"], minus[0]["sequence"])
        self.assertEqual(scan_spacers(dna, (1, 20)), [])

    def test_ambiguous_and_bad_window(self):
        with self.assertRaises(ValueError):
            scan_spacers("ANNN", (0, 4))
        with self.assertRaises(ValueError):
            scan_spacers("AAAA", (4, 1))


class FoldingTests(unittest.TestCase):
    def setUp(self):
        self.f = FoldEngine()

    def test_joint_unpaired_partition_ratio(self):
        seq = "GGGAAACCC"
        expected = math.exp(self.f.constrained_free_energy(seq) / (0.00198717 * 310.15))
        self.assertAlmostEqual(self.f.region_accessibility(seq, 0, len(seq)), expected, places=6)
        self.assertAlmostEqual(self.f.region_accessibility("AAAAAAAA", 0, 8), 1.0, places=6)

    def test_connected_ensemble_not_unbound_monomers(self):
        self.assertAlmostEqual(self.f.constraint_probability("GGGG&CCCC", "xxxxxxxx"), 0.0)
        # Connected binding can leave no probability of a fully exposed region.
        self.assertAlmostEqual(self.f.region_accessibility("GGGG&CCCC", 0, 4), 0.0)
        with self.assertRaises(ValueError):
            self.f.constraint_probability("AAAA&AAAA", "........")

    def test_scaffold_defect_matches_base_pair_matrix(self):
        seq = "GGGAAACCC"
        bpp = self.f.base_pair_probabilities(seq)
        expected_correct = 2 * (bpp[0][8] + bpp[1][7] + bpp[2][6])
        expected_correct += sum(1 - sum(bpp[i]) for i in (3, 4, 5))
        self.assertAlmostEqual(
            self.f.region_defect(seq, "(((...)))"), 1 - expected_correct / 9, places=5
        )

    def test_region_defect_at_nonzero_offset_matches_pair_probabilities(self):
        seq, start = "AAAAGGGAAACCC", 4
        matrix = self.f.base_pair_probabilities(seq)
        correct = 2 * sum(matrix[start + i][start + 8 - i] for i in range(3))
        correct += sum(1 - sum(matrix[start + i]) for i in (3, 4, 5))
        self.assertAlmostEqual(
            self.f.region_defect(seq, "(((...)))", start=start),
            1 - correct / 9,
            places=5,
        )
        with self.assertRaises(ValueError):
            self.f.region_defect(seq, "(((...)))", start=5)
        with self.assertRaises(ValueError):
            self.f.region_defect(seq, "(((...)))", start=-1)

    def test_shared_binding_energy_uses_connected_partition_energies(self):
        a, b = "GGGGGG", "CCCCCC"
        expected = (
            self.f.constrained_free_energy(a + "&" + b)
            - self.f.constrained_free_energy(a)
            - self.f.constrained_free_energy(b)
        )
        self.assertAlmostEqual(self.f.binding_free_energy(a, b), expected)
        with self.assertRaisesRegex(ValueError, "No connected"):
            self.f.binding_free_energy("AAAA", "AAAA")
        with self.assertRaisesRegex(ValueError, "individual strands"):
            self.f.binding_free_energy(a + "&" + b, b)

    def test_heterodimer_handles_either_strand_in_excess(self):
        dg, fraction_a = self.f.heterodimer_equilibrium("GGGGGG", "CCCCCC", 1e-6, 1e-8)
        swapped_dg, fraction_b = self.f.heterodimer_equilibrium(
            "CCCCCC",
            "GGGGGG",
            1e-8,
            1e-6,
        )
        self.assertAlmostEqual(dg, swapped_dg)
        self.assertGreater(fraction_a, 0)
        self.assertLessEqual(fraction_a, 0.01)
        self.assertAlmostEqual(fraction_a * 1e-6, fraction_b * 1e-8, delta=1e-16)

    def test_probability_invalid_intervals(self):
        with self.assertRaises(ValueError):
            self.f.region_accessibility("AAAA", 0, 5)
        with self.assertRaises(ValueError):
            self.f.region_defect("GGGAAACCC", "(((....))")


class BinaryBlockerTests(unittest.TestCase):
    def designs(self, mismatches):
        c = config()
        gate = CrisprGate(
            Host.HUMAN,
            None,
            spacer="A" * 20,
            scaffold=c["scaffold"],
            scaffold_reference=c["scaffold_reference"],
            templates=tuple(CrisprTemplate(**t) for t in c["templates"]),
        )
        # T: loop(14), Eprime(10), blocker(20), BT(10), antiparallel.
        sequence = "A" * 24 + "A" * (20 - mismatches) + "C" * mismatches + "A" * 10
        trigger = TriggerCandidate(
            trigger_id="test",
            gene_id="test",
            symbol="test",
            sequence=sequence,
            start_index=0,
            openness=None,
            accessibility=None,
            mfe=None,
            gc_content=0,
        )
        return gate.generate_designs(
            TriggerSet(activators=(trigger,)), Constraints(max_switch_length=200)
        )

    def test_equal_complements_produce_exactly_one_candidate(self):
        designs = list(self.designs(0))
        self.assertEqual(len(designs), 1)
        self.assertEqual(designs[0].architecture["blocker"], "U" * 20)
        self.assertEqual(designs[0].architecture["blocker_candidate_count"], 1)

    def test_three_differences_cover_all_eight_patterns_without_duplicates(self):
        designs = list(self.designs(3))
        expected = {
            prefix + "U" * 17 for prefix in ("GGG", "GGU", "GUG", "GUU", "UGG", "UGU", "UUG", "UUU")
        }
        self.assertEqual({d.architecture["blocker"] for d in designs}, expected)
        self.assertEqual(len(designs), 8)
        self.assertEqual(len({d.design_id for d in designs}), 8)
        self.assertEqual(
            [d.architecture["blocker_candidate_index"] for d in designs], list(range(8))
        )
        self.assertTrue(all(d.architecture["blocker_candidate_count"] == 8 for d in designs))
        self.assertTrue(
            all(d.architecture["blocker_variable_positions"] == (0, 1, 2) for d in designs)
        )

    def test_upper_bound_is_fully_enumerated_without_folding(self):
        # Stream all 2**20 designs; retain neither a list nor a set of sequences.
        count = 0
        for design in self.designs(20):
            count = design.architecture["blocker_candidate_index"] + 1
        self.assertEqual(count, 2**20)
        self.assertEqual(design.architecture["blocker_candidate_count"], 2**20)
        self.assertEqual(design.architecture["blocker"], "U" * 20)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        # Exercise the whole generator/scorer grid cheaply. Real folding is covered
        # by FoldingTests, spot checks below, and the separately run CLI demo.
        self.real_measurement_stages = CrisprGate.measurement_stages
        self.real_observables = lambda gate, design: CrisprObservables(
            **{
                k: v
                for batch in self.real_measurement_stages(gate, design)
                for k, v in batch.items()
            }
        )
        measurement_patch = patch(
            "engine.gates.crispr.CrisprGate.measurement_stages",
            autospec=True,
            return_value=(asdict(CrisprObservables(0.01, 0.8, 0.01, 0.01, -10)),),
        )
        self.measure = measurement_patch.start()
        self.addCleanup(measurement_patch.stop)

    def test_workbench_is_repeatable_and_auditable_with_controlled_measurements(self):
        first = run_crispr_workbench(config())
        self.assertEqual(first, run_crispr_workbench(config()))
        self.assertGreaterEqual(first["summary"]["evaluated_guides"], 30)
        self.assertEqual(first["status"], "ranked")
        self.assertEqual(len(first["top_candidates"]), 5)
        self.assertTrue(all(d["feasible"] for d in first["guide_audit"]))
        for d in first["guide_audit"]:
            a = d["architecture"]
            self.assertEqual(
                d["guide"],
                "".join(
                    a[k]
                    for k in (
                        "trigger_tail",
                        "blocker",
                        "anti_extension",
                        "loop",
                        "extension",
                        "spacer",
                        "scaffold",
                    )
                ),
            )
        json.dumps(first, allow_nan=False)

    def test_result_records_effective_thresholds(self):
        c = config()
        result = run_crispr_workbench(c)
        p = result["objective_parameters"]
        self.assertEqual((p["tau_off"], p["tau_on"], p["epsilon"]), (0.05, 0.50, 0.10))
        self.assertNotIn("tau_off", c["objective"])
        c["objective"]["tau_off"] = 0.02
        self.assertEqual(run_crispr_workbench(c)["objective_parameters"]["tau_off"], 0.02)

    def test_user_confirmed_order_and_antiparallel_trigger_match(self):
        c = config()
        result = run_crispr_workbench(c)
        designs = result["guide_audit"]
        windows = {p["pair_id"]: p["trigger"]["sequence"] for p in result["pairs"]}
        self.assertEqual(
            {len(t) for t in windows.values()},
            {length + bt + 30 for length in range(14, 33, 2) for bt in (10, 15, 20)},
        )
        self.assertEqual({len(d["architecture"]["trigger_tail"]) for d in designs}, {10, 15, 20})
        self.assertEqual(len({d["design_id"] for d in designs}), len(designs))
        spacer = sq.to_rna(c["target_dna"][:20])
        self.assertEqual(designs[-1]["architecture"]["blocker"], sq.reverse_complement(spacer))
        for design in designs:
            guide, a = design["guide"], design["architecture"]
            trigger = windows[design["pair_id"]]
            self.assertEqual(len(trigger), len(a["trigger_tail"]) + 30 + len(a["loop"]))
            if a["blocker_candidate_index"] == 0:
                self.assertEqual(guide[: len(trigger)], sq.reverse_complement(trigger))
            self.assertEqual(a["loop"], sq.reverse_complement(trigger[: len(a["loop"])]))
            for name in ("trigger_tail", "anti_extension", "loop"):
                lo, hi = a["intended_trigger_regions"][name]
                self.assertEqual(a[name], sq.reverse_complement(trigger[lo:hi]))
            self.assertEqual(len(a["extension"]), 10)
            self.assertEqual(len(a["anti_extension"]), 10)
            self.assertEqual(a["anti_extension"], sq.reverse_complement(a["extension"]))
            self.assertTrue(guide.endswith(spacer + c["scaffold"]))
            self.assertEqual(
                a["regions"]["scaffold"], (len(guide) - len(c["scaffold"]), len(guide))
            )
            for name, (start, end) in a["regions"].items():
                self.assertEqual(guide[start:end], a[name])
        # Two real calculations verify measurement coordinates without folding
        # every architecture again during a sequence-layout regression test.
        calls = self.measure.call_args_list
        for call in (calls[0], calls[-1]):
            gate, design = call.args
            obs = self.real_observables(gate, design)
            start, end = design.architecture["regions"]["spacer"]
            self.assertAlmostEqual(
                obs.a_off, gate.folder.region_accessibility(design.sequence, start, end)
            )
            self.assertAlmostEqual(
                obs.d_off,
                gate.folder.region_defect(
                    design.sequence,
                    gate.scaffold_reference,
                    start=design.architecture["regions"]["scaffold"][0],
                ),
            )

    def test_extension_length_is_fixed_at_ten(self):
        for length in (0, 6, 9, 11, 10.0, None):
            with self.subTest(length=length):
                c = config()
                c["templates"][0]["extension_length"] = length
                with self.assertRaisesRegex(ValueError, "exactly 10 nucleotides"):
                    run_crispr_workbench(c)

    def test_only_the_three_bt_lengths_are_allowed(self):
        for length in (0, 8, 11, 25, 10.0, None):
            with self.subTest(length=length):
                c = config()
                c["templates"][0]["trigger_tail_length"] = length
                with self.assertRaisesRegex(ValueError, "BT length must be one of"):
                    run_crispr_workbench(c)

    def test_all_three_lengths_required_and_duplicate_templates_rejected(self):
        c = config()
        c["templates"].pop()
        with self.assertRaisesRegex(ValueError, "all three BT lengths"):
            run_crispr_workbench(c)
        c = config()
        c["templates"].append(dict(c["templates"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate CRISPR"):
            run_crispr_workbench(c)

    def test_loop_length_grid_and_rejections(self):
        for length in (12, 15, 34, 14.0, None):
            with self.subTest(length=length):
                c = config()
                c["templates"][0]["loop_length"] = length
                with self.assertRaisesRegex(ValueError, "Loop length must be"):
                    run_crispr_workbench(c)
        c = config()
        c["templates"] = [t for t in c["templates"] if t["loop_length"] != 32]
        with self.assertRaisesRegex(ValueError, "all ten loop lengths"):
            run_crispr_workbench(c)
        c = config()
        c["templates"][0]["loop"] = "A" * 14
        with self.assertRaisesRegex(ValueError, "loop sequence is derived from the trigger"):
            run_crispr_workbench(c)

    def test_every_loop_bt_combination_is_scored(self):
        result = run_crispr_workbench(config())
        audit = result["guide_audit"]
        grid = {
            (len(d["architecture"]["loop"]), len(d["architecture"]["trigger_tail"])) for d in audit
        }
        self.assertEqual(grid, {(length, bt) for length in range(14, 33, 2) for bt in (10, 15, 20)})
        self.assertEqual(self.measure.call_count, len(audit))
        self.assertEqual(len({d["design_id"] for d in audit}), len(audit))
        self.assertGreaterEqual(len(audit), 30)
        self.assertEqual(len(result["top_candidates"]), 5)
        self.assertEqual(
            {p["trigger"]["length"] for p in result["pairs"]},
            {length + bt + 30 for length in range(14, 33, 2) for bt in (10, 15, 20)},
        )
        # A 64-nt window supports (L=24, BT=10) and (L=14, BT=20).
        same_window = [d for d in audit if d["pair_id"].endswith("toy:0:64")]
        self.assertEqual(
            {
                (len(d["architecture"]["loop"]), len(d["architecture"]["trigger_tail"]))
                for d in same_window
            },
            {(24, 10), (14, 20)},
        )

    def test_equal_sequences_do_not_erase_distinct_architectures(self):
        c = config()
        c["transcripts"]["toy"] = "A" * 82
        result = run_crispr_workbench(c)
        shared = [
            d
            for d in result["guide_audit"]
            if d["pair_id"].endswith("toy:0:64")
            and d["architecture"]["blocker_candidate_index"] == 0
        ]
        self.assertEqual(len(shared), 2)
        self.assertEqual(shared[0]["guide"], shared[1]["guide"])
        self.assertNotEqual(shared[0]["design_id"], shared[1]["design_id"])

    def test_audit_cap_does_not_limit_search_or_change_winner(self):
        # Later candidates win, including those beyond the retained audit prefix.
        self.measure.side_effect = lambda *_: (
            asdict(CrisprObservables(0.01, 0.8, 0.01, 0.01, -10 - self.measure.call_count)),
        )
        c = config()
        full = run_crispr_workbench(c)
        self.measure.reset_mock()
        c["guide_audit_limit"] = 1
        capped = run_crispr_workbench(c)
        self.assertEqual(capped["pairs"], full["pairs"])
        self.assertEqual(capped["top_candidates"], full["top_candidates"])
        self.assertEqual(capped["guide_rejection_counts"], full["guide_rejection_counts"])
        self.assertEqual(capped["summary"]["evaluated_guides"], full["summary"]["evaluated_guides"])
        self.assertEqual(len(capped["guide_audit"]), 1)
        self.assertEqual(
            capped["summary"]["omitted_guide_audits"], full["summary"]["evaluated_guides"] - 1
        )
        c["guide_audit_limit"] = 0
        self.assertEqual(run_crispr_workbench(c)["guide_audit"], [])
        for invalid in (-1, 1.5, True):
            c["guide_audit_limit"] = invalid
            with self.assertRaisesRegex(ValueError, "guide_audit_limit"):
                run_crispr_workbench(c)

    def test_staged_gates_skip_later_folding_and_keep_partial_audit(self):
        self.measure.side_effect = self.real_measurement_stages
        cases = (
            (
                0.051,
                0.01,
                0.8,
                0.01,
                "a_off > tau_off",
                1,
                0,
                0,
                {"d_off", "a_on", "d_on", "dg_bind"},
            ),
            (
                0.05,
                0.10,
                0.8,
                0.01,
                "d_off >= epsilon",
                1,
                1,
                0,
                {"a_on", "d_on", "dg_bind"},
            ),
            (0.05, 0.01, 0.499, 0.01, "a_on < tau_on", 2, 1, 1, {"d_on"}),
            (0.05, 0.01, 0.50, 0.10, "d_on >= epsilon", 2, 2, 1, set()),
            (0.05, 0.099, 0.50, 0.099, None, 2, 2, 1, set()),
        )
        for off, defect_off, on, defect_on, failure, na, nd, ne, missing in cases:
            with (
                self.subTest(failure=failure),
                (
                    patch.object(
                        FoldEngine,
                        "region_accessibility",
                        side_effect=lambda strands, *_, on=on, off=off, **__: (
                            on if "&" in strands else off
                        ),
                    )
                ) as access,
                (
                    patch.object(
                        FoldEngine,
                        "region_defect",
                        side_effect=lambda strands, *_, on=defect_on, off=defect_off, **__: (
                            on if "&" in strands else off
                        ),
                    )
                ) as defect,
                patch.object(FoldEngine, "binding_free_energy", return_value=-10) as binding,
            ):
                result = run_crispr_workbench(config())
                count = result["summary"]["evaluated_guides"]
                self.assertEqual(access.call_count, na * count)
                self.assertEqual(defect.call_count, nd * count)
                self.assertEqual(binding.call_count, ne * count)
                for item in result["guide_audit"]:
                    self.assertEqual(item["rejections"], [failure] if failure else [])
                    self.assertEqual(
                        {k for k, v in item["observables"].items() if v is None}, missing
                    )
                    self.assertEqual(item["feasible"], failure is None)
                    if failure:
                        self.assertIsNone(item["j"])
                        self.assertIsNone(item["j_accessibility"])
                        self.assertIsNone(item["j_energy"])
                    else:
                        expected = inner_objective(
                            CrisprObservables(**item["observables"]),
                            CrisprObjective(**result["objective_parameters"]),
                        )
                        self.assertEqual(item["j"], expected["j"])

    def test_real_folding_staged_and_full_search_agree(self):
        # Two candidates per pair keep this equivalence check small while exercising
        # real partition functions, feasibility decisions and winner selection.
        from itertools import islice

        generate = CrisprGate.generate_designs

        def small_search(gate, trigger_set, constraints):
            return islice(generate(gate, trigger_set, constraints), 2)

        with patch.object(CrisprGate, "generate_designs", small_search):
            self.measure.side_effect = self.real_measurement_stages
            staged = run_crispr_workbench(config())
            self.measure.side_effect = lambda gate, design: (
                asdict(self.real_observables(gate, design)),
            )
            full = run_crispr_workbench(config())
        self.assertEqual(staged["pairs"], full["pairs"])
        self.assertEqual(staged["top_candidates"], full["top_candidates"])
        for early, complete in zip(staged["guide_audit"], full["guide_audit"], strict=True):
            self.assertEqual(early["design_id"], complete["design_id"])
            self.assertEqual(early["feasible"], complete["feasible"])
            self.assertEqual(early["j"], complete["j"])
            for name, value in early["observables"].items():
                if value is not None:
                    self.assertEqual(value, complete["observables"][name])

    def test_global_batch_scale_precedes_winners_and_excludes_rejected_guides(self):
        from itertools import islice

        generate = CrisprGate.generate_designs
        observations = {
            54: (
                CrisprObservables(0.01, 0.9, 0.01, 0.01, -10),
                CrisprObservables(0.01, 0.5, 0.01, 0.01, -20),
            ),
            56: (
                CrisprObservables(0.01, 0.99, 0.01, 0.01, -80),
                CrisprObservables(0.01, 0.5, 0.01, 0.01, -1),
            ),
        }

        def selected(gate, trigger_set, constraints):
            length = trigger_set.activators[0].length
            return islice(
                generate(gate, trigger_set, constraints), 3 if length in observations else 0
            )

        def measured(gate, design):
            index = design.architecture["blocker_candidate_index"]
            o = (
                observations[design.trigger_set.activators[0].length][index]
                if index < 2
                else CrisprObservables(0.9, 0.99, 0.01, 0.01, -10000)
            )
            return (asdict(o),)

        self.measure.side_effect = measured
        with patch.object(CrisprGate, "generate_designs", selected):
            result = run_crispr_workbench(config())
            self.assertEqual(self.measure.call_count, 6)  # One measurement per guide.
            flat = [o for group in observations.values() for o in group]
            expected = sum(abs(o.dg_bind) for o in flat) / sum(
                abs(0.4 * o.a_on - 0.6 * o.a_off) for o in flat
            )
            self.assertAlmostEqual(result["lambda_calculation"]["value"], expected)
            self.assertEqual(result["lambda_calculation"]["candidate_count"], 4)
            p = CrisprObjective(**result["objective_parameters"])
            viable = [row for row in result["pairs"] if row["j_best"] is not None]
            self.assertEqual(len(viable), 2)
            for row in viable:
                choices = observations[row["trigger"]["length"]]
                scores = [inner_objective(o, p)["j"] for o in choices]
                self.assertAlmostEqual(row["j_best"], max(scores))
                self.assertEqual(
                    row["architecture"]["blocker_candidate_index"], scores.index(max(scores))
                )
            # Calibrating each pair separately would select the wrong first winner.
            local = replace(p, scale_lambda=calibrate_scale(observations[54], 0.4, 0.6))
            self.assertGreater(
                inner_objective(observations[54][1], local)["j"],
                inner_objective(observations[54][0], local)["j"],
            )
            self.assertEqual(viable[0]["architecture"]["blocker_candidate_index"], 0)
            for item in result["guide_audit"]:
                if item["feasible"]:
                    self.assertAlmostEqual(
                        item["j"], inner_objective(CrisprObservables(**item["observables"]), p)["j"]
                    )
            capped = run_crispr_workbench(config() | {"guide_audit_limit": 0})
            self.assertEqual(capped["lambda_calculation"], result["lambda_calculation"])
            self.assertEqual(capped["top_candidates"], result["top_candidates"])

    def test_manual_lambda_rejected_and_empty_batch_has_no_scale(self):
        c = config()
        self.assertEqual(
            {k: c["objective"][k] for k in ("w_on", "w_off", "w_energy", "w_accessibility")},
            {"w_on": 0.4, "w_off": 0.6, "w_energy": 0.5, "w_accessibility": 0.5},
        )
        c["objective"]["scale_lambda"] = 10
        with self.assertRaisesRegex(ValueError, "Remove scale_lambda"):
            run_crispr_workbench(c)
        c = config()
        c["objective"]["tau_on"] = 0.99
        result = run_crispr_workbench(c)
        self.assertEqual(result["lambda_calculation"]["candidate_count"], 0)
        self.assertIsNone(result["objective_parameters"]["scale_lambda"])
        self.assertEqual(result["lambda_calculation"]["status"], "empty_batch")
        self.assertEqual(result["top_candidates"], [])

    def test_nonpositive_winners_keep_zero_rank_but_are_not_selected(self):
        from itertools import islice

        generate = CrisprGate.generate_designs

        def selected(gate, trigger_set, constraints):
            return islice(
                generate(gate, trigger_set, constraints),
                1 if trigger_set.activators[0].length in (54, 56, 58) else 0,
            )

        # With constant JA, batch lambda makes the accessibility contribution
        # equal to mean |JE| = 2. This yields J = 0, -0.5, 1.5 respectively.
        energies = {54: 2, 56: 3, 58: -1}
        self.measure.side_effect = lambda gate, design: (
            asdict(
                CrisprObservables(
                    0.01, 0.8, 0.01, 0.01, energies[design.trigger_set.activators[0].length]
                )
            ),
        )
        with patch.object(CrisprGate, "generate_designs", selected):
            result = run_crispr_workbench(config())
        rows = [r for r in result["pairs"] if r["j_best"] is not None]
        self.assertEqual(len(rows), 3)
        self.assertEqual(result["summary"]["feasible_pairs"], 3)
        self.assertEqual(result["summary"]["selectable_pairs"], 1)
        self.assertEqual(len(result["top_candidates"]), 1)
        self.assertEqual(result["top_candidates"][0]["trigger"]["length"], 58)
        for row, expected in zip(rows, (0, -0.5, 1.5), strict=True):
            self.assertAlmostEqual(row["j_best"], expected)
            self.assertEqual(row["rejections"], [])
            if expected <= 0:
                self.assertEqual(row["phi"], 0)
                self.assertEqual(row["j_positive"], 0)
                self.assertFalse(row["selectable"])
                self.assertGreater(row["rank"], 1)

    def test_all_zero_scores_do_not_produce_a_recommended_winner(self):
        self.measure.side_effect = lambda *_: (asdict(CrisprObservables(0.01, 0.8, 0.01, 0.01, 0)),)
        result = run_crispr_workbench(config())
        self.assertEqual(result["status"], "no_positive_switch_candidates")
        self.assertEqual(result["top_candidates"], [])
        self.assertGreater(result["summary"]["feasible_pairs"], 0)
        self.assertEqual(result["summary"]["selectable_pairs"], 0)
        self.assertTrue(all(row["phi"] == 0 for row in result["pairs"]))

    def test_legacy_spacer_formula_mode_is_rejected(self):
        for mode in ("literal", "specificity"):
            c = config()
            c["objective"]["spacer_score_mode"] = mode
            with (
                self.subTest(mode=mode),
                self.assertRaisesRegex(ValueError, "Remove spacer_score_mode"),
            ):
                run_crispr_workbench(c)

    def test_missing_inputs_and_search_budget(self):
        for key in ("scaffold_reference", "objective", "target_dna"):
            c = config()
            c[key] = None
            with self.assertRaises(ValueError):
                run_crispr_workbench(c)
        c = config()
        c["transcripts"]["extra"] = c["transcripts"]["toy"]
        c["max_pairs"] = 1
        with self.assertRaises(ValueError):
            run_crispr_workbench(c)

    def test_missing_external_scores_not_fabricated(self):
        c = config()
        c["spacer_metrics"] = {}
        with self.assertRaisesRegex(ValueError, "Missing spacer_metrics"):
            run_crispr_workbench(c)
        self.assertEqual(self.measure.call_count, 0)

    def test_preflight_rejects_malformed_inputs_before_measurement(self):
        bad_inputs = (
            ("target_dna", 123),
            ("target_dna", "ACNT"),
            ("scaffold", []),
            ("scaffold_reference", 123),
            ("scaffold_reference", ".."),
            ("activation_window", "0:20"),
            ("activation_window", [0, 20.0]),
            ("activation_window", [False, 20]),
            ("activation_window", [20, 0]),
            ("activation_window", [0, 100000]),
            ("templates", {}),
            ("templates", [None]),
            ("templates", [{"unexpected": 1}]),
            ("objective", []),
            ("objective", {}),
            ("temperature_c", None),
            ("temperature_c", "37"),
            ("temperature_c", True),
            ("temperature_c", math.nan),
            ("temperature_c", -273.15),
            ("host", "unknown"),
            ("transcripts", []),
            ("transcripts", {1: "AAAA"}),
            ("transcripts", {"toy": []}),
            ("transcripts", {"toy": "ACGN"}),
            ("spacer_metrics", []),
            ("trigger_metrics", []),
            ("score_source", ""),
            ("calibration_source", None),
        )
        for key, value in bad_inputs:
            c = config()
            c[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                run_crispr_workbench(c)
        for bad in (None, [], "input"):
            with self.subTest(config=bad), self.assertRaisesRegex(ValueError, "JSON object"):
                run_crispr_workbench(bad)
        self.assertEqual(self.measure.call_count, 0)

    def test_preflight_requires_complete_normalized_upstream_scores(self):
        for table, identifier, key in (
            ("spacer_metrics", "0:20:+", "eta_on"),
            ("spacer_metrics", "0:20:+", "eta_off"),
            ("trigger_metrics", "toy:0:82", "q_trigger"),
        ):
            for value in (None, "0.8", True, -0.01, 1.01, math.nan, math.inf):
                c = config()
                c[table][identifier][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, table):
                    run_crispr_workbench(c)
            c = config()
            del c[table][identifier]
            with self.subTest(missing=identifier), self.assertRaisesRegex(ValueError, "Missing"):
                run_crispr_workbench(c)
        c = config()
        c["objective"]["w_on"] = None
        with self.assertRaisesRegex(ValueError, "w_on"):
            run_crispr_workbench(c)
        self.assertEqual(self.measure.call_count, 0)

    def test_no_feasible_candidate_is_successful_empty_result(self):
        c = config()
        c["objective"]["tau_on"] = 0.99
        r = run_crispr_workbench(c)
        self.assertEqual(r["status"], "no_feasible_candidates")
        self.assertFalse(r["top_candidates"])

    def test_conditional_on_matches_partition_ratio_without_concentrations(self):
        c = config()
        self.assertNotIn("guide_molar", c)
        self.assertNotIn("trigger_molar", c)
        result = run_crispr_workbench(c)
        self.assertEqual(result["model"], "off-g-on-connected-gT-v1")
        self.assertNotIn("bound_fraction", result["guide_audit"][0]["observables"])
        gate, design = self.measure.call_args_list[0].args
        with patch.object(
            FoldEngine,
            "heterodimer_equilibrium",
            side_effect=AssertionError("No concentration model in CRISPR"),
        ):
            obs = self.real_observables(gate, design)
        trigger = design.trigger_set.activators[0].sequence
        connected = design.sequence + "&" + trigger
        start, end = design.architecture["regions"]["spacer"]
        constraint = "." * start + "x" * (end - start)
        constraint += "." * (len(design.sequence) + len(trigger) - end)
        rt = 0.00198717 * (273.15 + gate.folder.temperature)
        expected_on = math.exp(
            (
                gate.folder.constrained_free_energy(connected)
                - gate.folder.constrained_free_energy(connected, constraint)
            )
            / rt
        )
        self.assertAlmostEqual(obs.a_on, expected_on)
        self.assertAlmostEqual(
            obs.d_on,
            gate.folder.region_defect(
                connected,
                gate.scaffold_reference,
                start=design.architecture["regions"]["scaffold"][0],
            ),
        )
        self.assertAlmostEqual(
            obs.dg_bind,
            (
                gate.folder.constrained_free_energy(connected)
                - gate.folder.constrained_free_energy(design.sequence)
                - gate.folder.constrained_free_energy(trigger)
            ),
        )

    def test_legacy_concentrations_are_not_silently_ignored(self):
        for key in ("guide_molar", "trigger_molar"):
            c = config()
            c[key] = 1e-8
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Remove guide_molar"):
                run_crispr_workbench(c)

    def test_measurement_failure_is_not_a_threshold_rejection(self):
        def fail_after_off(*_):
            yield {"a_off": 0.01}
            raise ArithmeticError("PF failed")

        self.measure.side_effect = fail_after_off
        result = run_crispr_workbench(config())
        self.assertEqual(result["status"], "measurement_incomplete")
        self.assertFalse(result["measurement_complete"])
        self.assertEqual(result["top_candidates"], [])
        self.assertEqual(result["guide_rejection_counts"], {})
        count = result["summary"]["evaluated_guides"]
        self.assertEqual(result["summary"]["measurement_failed_guides"], count)
        self.assertEqual(
            result["measurement_failure_counts"], {"ArithmeticError: PF failed": count}
        )
        for item in result["guide_audit"]:
            self.assertIsNone(item["feasible"])
            self.assertEqual(item["evaluation_status"], "measurement_failed")
            self.assertEqual(item["observables"]["a_off"], 0.01)
            self.assertIsNone(item["observables"]["d_off"])
            self.assertEqual(item["rejections"], [])
        self.assertTrue(all(row["rejections"] == [] for row in result["pairs"]))
        self.assertTrue(all(row["measurement_failures"] > 0 for row in result["pairs"]))

    def test_one_missing_measurement_blocks_global_scale_and_winners_even_without_audit(self):
        def mixed(gate, design):
            if (
                design.trigger_set.activators[0].length == 54
                and design.architecture["blocker_candidate_index"] == 1
            ):
                raise ValueError("Invalid probability a_on")
            yield asdict(CrisprObservables(0.01, 0.8, 0.01, 0.01, -10))

        self.measure.side_effect = mixed
        result = run_crispr_workbench(config() | {"guide_audit_limit": 0})
        self.assertEqual(result["summary"]["measurement_failed_guides"], 1)
        self.assertGreater(result["summary"]["inner_feasible_guides"], 0)
        self.assertEqual(result["status"], "measurement_incomplete")
        self.assertIsNone(result["objective_parameters"]["scale_lambda"])
        self.assertEqual(result["lambda_calculation"]["status"], "measurement_incomplete")
        self.assertEqual(result["top_candidates"], [])
        self.assertEqual(result["guide_audit"], [])
        self.assertTrue(
            all(row["j_best"] is None and row["phi"] is None for row in result["pairs"])
        )
        self.assertEqual(sum(row["measurement_failures"] for row in result["pairs"]), 1)
        self.assertEqual(sum(result["measurement_failure_counts"].values()), 1)

    def test_completed_threshold_rejection_is_distinct_from_measurement_failure(self):
        self.measure.side_effect = lambda *_: ({"a_off": 0.9},)
        result = run_crispr_workbench(config())
        self.assertEqual(result["status"], "no_feasible_candidates")
        self.assertTrue(result["measurement_complete"])
        self.assertEqual(result["measurement_failure_counts"], {})
        self.assertEqual(
            result["summary"]["threshold_rejected_guides"], result["summary"]["evaluated_guides"]
        )
        for item in result["guide_audit"]:
            self.assertFalse(item["feasible"])
            self.assertEqual(item["evaluation_status"], "rejected")
            self.assertIsNone(item["measurement_error"])
            self.assertEqual(item["rejections"], ["a_off > tau_off"])

    def test_selected_external_parameters_and_exact_risk_ceiling(self):
        c = config()
        expected = {
            "v_on": 0.4,
            "v_off": 0.6,
            "w_spacer": 0.6,
            "w_trigger": 0.4,
            "off_target_max": 0.2,
        }
        user = json.loads((ROOT / "examples/crispr/your_model.template.json").read_text())
        for name, value in expected.items():
            self.assertEqual(c["objective"][name], value)
            self.assertEqual(user["objective"][name], value)
        c["spacer_metrics"]["0:20:+"]["eta_off"] = 0.2
        accepted = run_crispr_workbench(c)
        self.assertEqual(accepted["status"], "ranked")
        self.assertGreater(self.measure.call_count, 0)
        for row in accepted["top_candidates"]:
            self.assertAlmostEqual(row["q_spacer"], 0.4 * 0.8 + 0.6 * (1 - 0.2))
            self.assertEqual(row["q_trigger"], 0.8)
            self.assertAlmostEqual(row["q_pair"], 0.6 * 0.8 + 0.4 * 0.8)
        self.measure.reset_mock()
        c["spacer_metrics"]["0:20:+"]["eta_off"] = math.nextafter(0.2, math.inf)
        rejected = run_crispr_workbench(c)
        self.assertEqual(self.measure.call_count, 0)
        self.assertEqual(rejected["guide_audit"], [])
        self.assertEqual(rejected["top_candidates"], [])
        self.assertTrue(
            all(row["rejections"] == ["eta_off > off_target_max"] for row in rejected["pairs"])
        )

    def test_offtarget_gate_runs_before_folding(self):
        c = copy.deepcopy(config())
        c["spacer_metrics"]["0:20:+"]["eta_off"] = 0.9
        r = run_crispr_workbench(c)
        self.assertEqual(r["guide_audit"], [])
        self.assertIn("eta_off > off_target_max", r["pairs"][0]["rejections"])


if __name__ == "__main__":
    unittest.main()
