@echo off
REM One shard of the landing barrier on the stem the design rule prefers:
REM per cell, the unlevered design with the highest lock_minus_a_site.
REM Six windows, change only the number. Resumable.
REM   tools\run_barrier_best.cmd 0      (then 1, 2, 3, 4, 5)
cd /d %~dp0..
uv run python -u tools\barrier_designs.py --out docs\assets\barrier\best_%1.csv ^
  --select best-lock --shard %1/6
