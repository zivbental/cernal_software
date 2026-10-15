@echo off
REM The state-10 landing barrier over the grid's cells, recomputed with the corrected
REM barrier. This is the run behind the "arbitrary stem" column of 7.6.
REM
REM It writes to docs\assets\barrier_fixed\ and NOT to docs\assets\barrier\: each shard
REM resumes by reading the keys already in its own output file, so pointing it at the
REM old files would make it skip all 420 rows and write nothing. Keeping them apart also
REM leaves the old run on disk for barrier_compare.py to join against.
REM
REM Six windows, change only the number. 420 rows in total, so well under an hour.
REM   tools\run_barrier_fixed.cmd 0      (then 1, 2, 3, 4, 5)
cd /d %~dp0..
if not exist docs\assets\barrier_fixed mkdir docs\assets\barrier_fixed
uv run python -u tools\barrier_landing.py --out docs\assets\barrier_fixed\landing_%1.csv ^
  --shard %1/6
