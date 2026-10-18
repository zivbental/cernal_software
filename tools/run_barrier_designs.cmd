@echo off
REM One shard of the per-design landing barrier. Six windows, change only the number.
REM Each design is rebuilt with its own levers, so its barrier sits beside its own leak.
REM Resumable: kill and rerun the same line, it skips what it wrote.
REM   tools\run_barrier_designs.cmd 0      (then 1, 2, 3, 4, 5)
cd /d %~dp0..
uv run python -u tools\barrier_designs.py --out docs\assets\barrier\designs_%1.csv ^
  --per-cell 8 --shard %1/6
