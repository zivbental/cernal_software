@echo off
REM The 2x2: which cells the equilibrium rejects that a barrier would rescue.
REM Reads the shard files and the grid; writes nothing. Run it once the shards are done.
cd /d %~dp0..
uv run python tools\barrier_vs_leak.py
