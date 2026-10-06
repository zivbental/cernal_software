@echo off
REM ===========================================================================================
REM  Progress of the axis-characterisation run. READ-ONLY: safe to run while shards are working.
REM
REM  Copy one of these into a terminal (cmd.exe or PowerShell, either works):
REM
REM     tools\axes_status.cmd
REM     tools\axes_status.cmd control
REM     tools\axes_status.cmd smoke
REM
REM  Prints each shard's row count, file size and last write time. A shard whose last write is more
REM  than five minutes old is marked idle, which is how a dead shard shows itself. Then the total,
REM  how many designs were measured in full, and which filter stopped the rest.
REM ===========================================================================================

setlocal
cd /d "%~dp0.."

set OUT=axes_pfas
if /i "%1"=="control" set OUT=axes_mcherry
if /i "%1"=="smoke" set OUT=axes_smoke

uv run python tools\characterise_axes.py --out %OUT% --shard 0/6 --status
echo.
echo   tail of shard 0's log:
if exist tools\logs\%OUT%_0.log powershell -NoProfile -Command "Get-Content tools\logs\%OUT%_0.log -Tail 3"
endlocal
