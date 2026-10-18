@echo off
REM One shard of the state-10 landing barrier, over the cells the grid contains.
REM Six windows, change only the number. Safe to kill and restart: each shard skips
REM keys already written.
REM   tools\run_barrier.cmd 0      (then 1, 2, 3, 4, 5)
cd /d %~dp0..
uv run python -u tools\barrier_landing.py --out docs\assets\barrier\landing_%1.csv --shard %1/6
