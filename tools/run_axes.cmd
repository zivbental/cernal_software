@echo off
REM ===========================================================================================
REM  The axis-characterisation run: six shards, one per core, at high priority, about 8 hours.
REM
REM  Copy ONE of these lines into a terminal (cmd.exe or PowerShell, either works):
REM
REM     tools\run_axes.cmd
REM     tools\run_axes.cmd control
REM     tools\run_axes.cmd smoke
REM
REM  Then, from any other window, as often as you like:
REM
REM     tools\axes_status.cmd
REM
REM  Each shard writes results\axes_pfas_<i>.csv, flushed and fsynced every 100 rows. Kill any
REM  window and run the same line again: --resume reads the keys already on disk and continues,
REM  losing at most the rows since the last flush. Re-running when nothing was killed is harmless;
REM  every shard finds its keys present and exits.
REM
REM  SIZING, measured and not assumed. On the real PFAS genes a 929-row timing run gave 0.25 to
REM  0.54 s per enumerated design, and 12.9% of designs pass the open_11 <= 4.0 ceiling and get all
REM  four tubes. Six shards for 8 hours is 48 core-hours, so at 0.40 s that is about 432,000
REM  designs. One trigger pair costs 2 geometries x 6 stems x 96 grid points = 1,152 designs, so
REM  the budget is about 375 pairs, and 120 per gene pair x 3 gene pairs = 360 is just inside it.
REM  Expect roughly 46,000 designs measured in full over about 720 (pair, geometry) cells.
REM
REM  If it overruns, nothing is lost: kill the windows and the rows written are already on disk and
REM  analysable. If it finishes early, raise PAIRS and run the same line again -- resume keeps the
REM  work already done.
REM ===========================================================================================

setlocal
cd /d "%~dp0.."
if not exist tools\logs mkdir tools\logs

set OUT=axes_pfas
set PAIRS=120
set STEMS=6
set EXTRA=

if /i "%1"=="control" (
  REM The mCherry control: both windows from one transcript, comparable with every earlier sweep.
  REM 60 pairs is about 1.5 hours on six cores and is a cross-check, not a second dataset.
  set OUT=axes_mcherry
  set PAIRS=60
  set EXTRA=--control
)
if /i "%1"=="smoke" (
  REM Proves the six windows launch and write, in about a minute. Delete the files afterwards.
  set OUT=axes_smoke
  set PAIRS=2
  set STEMS=2
  set EXTRA=--limit 60
)

echo Launching 6 shards:  out=%OUT%  pairs=%PAIRS%  stems=%STEMS%  %EXTRA%
echo.

for %%i in (0 1 2 3 4 5) do start "axes %OUT% %%i" /high /min cmd /c "uv run python tools\characterise_axes.py --out %OUT% --shard %%i/6 --pairs %PAIRS% --stems %STEMS% %EXTRA% --resume > tools\logs\%OUT%_%%i.log 2>&1"

echo Six windows started, minimised, at high priority.
echo   logs    tools\logs\%OUT%_*.log
echo   status  tools\axes_status.cmd %1
endlocal
