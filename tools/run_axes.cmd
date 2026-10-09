@echo off
REM ===========================================================================================
REM  The axis-characterisation run: six shards, one per core, at high priority, about 6 hours.
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
REM  ---------------------------------------------------------------------------------------
REM  SIZING, re-measured 2026-10-09 and NOT inherited. Three of the numbers this file used to
REM  carry were wrong, each because the sample that produced them was truncated:
REM
REM    * 0.991 s per enumerated design, from a 3,120-row strided run. The old 0.40 s came from
REM      the FIRST designs in generator order, which are the easy closures.
REM    * 22.8% pass the open_11 <= 4.0 ceiling. The old 12.9% and a later 1.7% were both bad
REM      samples -- the 1.7% was two trigger pairs.
REM    * stems per pair is now set by the DATA, not by --stems: stem_order=front_tops takes one
REM      stem per non-empty square of the 3x3 (lock x a_site) board plus the strongest stem on
REM      each of the three Pareto axes. Measured median 9 per cell, range 8 to 10, and the count
REM      lands in the stems_selected column.
REM
REM  So designs per trigger pair = 2 geometries x ~9 stems x ceil(96 / STRIDE) grid points.
REM
REM    STRIDE  grid pts  designs/pair  360 pairs  hours on six  fully measured per cell
REM         1        96         1,728    622,080          28.5                      196
REM         5        20           360    129,600           5.9                       41
REM         7        14           252     90,720           4.2                       28
REM
REM  STRIDE must be COPRIME with 96 or it aliases an axis: lower3 has period 2 in the grid index
REM  and upper3 period 6, so a stride of 6 pins both to one level -- measured, 4,927 rows with a
REM  single lower3 value and no wobble_GU at all. The script refuses a non-coprime stride and
REM  names the usable ones. 5, 7, 11 and 13 work; 2, 3, 4, 6, 8 and 12 do not.
REM
REM  If it overruns, nothing is lost: kill the windows and the rows written are already on disk and
REM  analysable. If it finishes early, raise PAIRS or lower STRIDE and run the same line again --
REM  resume keeps the work already done.
REM ===========================================================================================

setlocal
cd /d "%~dp0.."
if not exist tools\logs mkdir tools\logs

set OUT=axes_pfas
set PAIRS=120
set STRIDE=5
set EXTRA=

if /i "%1"=="control" (
  REM The mCherry control: both windows from one transcript, comparable with every earlier sweep.
  REM A cross-check, not a second dataset.
  set OUT=axes_mcherry
  set PAIRS=60
  set EXTRA=--control
)
if /i "%1"=="smoke" (
  REM Proves the six windows launch and write, in about a minute. Delete the files afterwards.
  set OUT=axes_smoke
  set PAIRS=2
  set STRIDE=7
  set EXTRA=--limit 60
)

echo Launching 6 shards:  out=%OUT%  pairs=%PAIRS% per gene pair  grid-stride=%STRIDE%  %EXTRA%
echo.

for %%i in (0 1 2 3 4 5) do start "axes %OUT% %%i" /high /min cmd /c "uv run python tools\characterise_axes.py --out %OUT% --shard %%i/6 --pairs %PAIRS% --grid-stride %STRIDE% %EXTRA% --resume > tools\logs\%OUT%_%%i.log 2>&1"

echo Six windows started, minimised, at high priority.
echo   logs    tools\logs\%OUT%_*.log
echo   status  tools\axes_status.cmd %1
endlocal
