#!/usr/bin/env bash
# Score the A0 sweep with the energy objective, most informative designs first.
#
#   ./run_full_objective.sh
#
# That is the whole command. It runs for about 16 hours, writes a usable panel roughly every
# two hours along the way, streams every result to CSV and resumes from where it stopped, so
# Ctrl-C is safe and re-running continues. Read results whenever you like; nothing waits for
# the end.
#
# Optional, only if you want them:
#   SHARDS=6 ./run_full_objective.sh     fewer parallel processes (default 10)
#   ./run_full_objective.sh phase1       stop after the closed closures, skip open_3x3
#
# --- why this order ---------------------------------------------------------------------
# A-anchored and unlocked are skipped: 0 of 4,330 and 0 of 384 gating, with a known mechanism
# (they spend lock strength on trigger A's own site, so A alone opens the stem). They are only
# 1.3% of the sweep, so that is cleanliness rather than speed.
#
# What actually gets candidates sooner is ordering:
#   * families by measured gating rate, p3 first at 75%, then p1 43%, k1 49%, p2, wob, prev
#   * the five CLOSED closures (~55% gating) before open_3x3 (14.3%, but 17% of the sweep)
#   * the accessibility table per family, just before that family, not all of it up front
#   * a panel after EVERY family, not only at the end
#
# p3 needs 2.7 min of accessibility plus 2.1 h of scoring, so the first real panel lands at
# about 2.2 h. Doing all the accessibility first would have delayed it to 3.1 h and the panel
# to 13 h, which is what an earlier version of this script did.
set -u
# Moved here from the repo root. Its paths are relative to the REPO ROOT, five directories
# up from this file.
cd "$(dirname "$0")/../../../../.."
SHARDS="${SHARDS:-10}"
PHASE="${1:-all}"
OBJ=src/engine/gates/notebooks/toehold_and/objective_energy.py
PANEL=src/engine/gates/notebooks/toehold_and/objective_panel.py
RES=src/engine/gates/notebooks/toehold_and/results
FASTA=mCherry_original.txt
CLOSED="closed_CAU,closed_CGU,closed_UAU,pair1_CCC,pair2_CCU"
FAMS="p3 p1 k1 p2 wob prev"

run_family () {   # family, closure-list, label
  local fam="$1" closures="$2" label="$3"
  echo
  echo "=== $fam [$label] ==="
  # Accessibility first and single-threaded: every shard appends to one shared CSV and
  # concurrent appends corrupt it. Restricted to this family's windows, so it is minutes.
  uv run python "$OBJ" --from "$fam" --out "obj_full_$fam" --fasta "$FASTA" \
    --closure "$closures" --access-only
  for i in $(seq 0 $((SHARDS - 1))); do
    uv run python "$OBJ" --from "$fam" --out "obj_full_$fam" --fasta "$FASTA" \
      --closure "$closures" --shard "$i/$SHARDS" > "/tmp/obj_${fam}_${label}_$i.log" 2>&1 &
  done
  wait
  echo "--- $fam done, rows: $(cat $RES/obj_full_${fam}_*.csv 2>/dev/null | grep -vc '^switch' || echo 0)"
  uv run python "$PANEL" --want 12 --out panel_energy | tail -20
  echo "--- panel refreshed: $RES/panel_energy.csv"
}

echo "###### phase 1: the closed closures ######"
for fam in $FAMS; do run_family "$fam" "$CLOSED" closed; done

if [ "$PHASE" = "phase1" ]; then
  echo; echo "stopping after phase 1 as asked"; exit 0
fi

echo; echo "###### phase 2: open_3x3 ######"
for fam in $FAMS; do run_family "$fam" "open_3x3" open3x3; done

echo; echo "###### done ######"
uv run python "$PANEL" --want 12 --out panel_energy | tail -20
