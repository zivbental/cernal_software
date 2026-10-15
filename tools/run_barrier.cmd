@echo off
REM Six shards of the state-10 landing barrier. One window each; change only the number.
REM Safe to kill and restart: --resume is implicit, each shard skips keys already written.
REM   tools\run_barrier.cmd 0      (then 1, 2, 3, 4, 5 in five more windows)
cd /d %~dp0..
uv run python -u tools\barrier_landing.py --out docs\assets\barrier\landing_%1.csv --shard %1/6
