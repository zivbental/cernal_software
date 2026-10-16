@echo off
REM How far the six barrier shards have got. Reads the files; touches nothing.
cd /d %~dp0..
uv run python tools\barrier_status.py
