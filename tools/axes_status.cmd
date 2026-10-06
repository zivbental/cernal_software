@echo off
REM Progress of the axis-characterisation run. Read-only: safe while shards are running.
REM
REM   tools\axes_status.cmd              the PFAS run
REM   tools\axes_status.cmd control      the mCherry control
REM
REM Prints each shard's row count, file size and last write time -- a shard whose last write is
REM more than five minutes old is marked idle, which is how a dead shard shows itself -- then the
REM total, how many designs were measured in full, and why the rest stopped.

setlocal
cd /d "%~dp0.."

set OUT=axes_pfas
if /i "%1"=="control" set OUT=axes_mcherry

uv run python tools\characterise_axes.py --out %OUT% --shard 0/6 --status
endlocal
