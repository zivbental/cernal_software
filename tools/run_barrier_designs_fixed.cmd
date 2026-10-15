@echo off
REM The per-design landing barrier, recomputed with the corrected barrier.
REM
REM It writes to docs\assets\barrier_fixed\ and NOT to docs\assets\barrier\, which
REM matters: the runner resumes by reading the keys already in its own output file, so
REM pointing it at the old files would make it skip all 3,113 rows and write nothing.
REM The old run stays on disk so the two can be compared design by design.
REM
REM Six windows, change only the number. Measured at about 22 s per design per shard,
REM so roughly 3 hours for all six.
REM   tools\run_barrier_designs_fixed.cmd 0      (then 1, 2, 3, 4, 5)
cd /d %~dp0..
if not exist docs\assets\barrier_fixed mkdir docs\assets\barrier_fixed
uv run python -u tools\barrier_designs.py --out docs\assets\barrier_fixed\designs_%1.csv ^
  --per-cell 8 --shard %1/6
