@echo off
REM Launch the axis-characterisation run: six shards, one per core, at high priority.
REM
REM   tools\run_axes.cmd                 the PFAS run, ~10 h on six cores
REM   tools\run_axes.cmd control         the mCherry control, ~1.5 h
REM
REM Check on it at any time, from another window, without touching a running shard:
REM
REM   tools\axes_status.cmd
REM
REM Each shard writes results\axes_pfas_<i>.csv, flushed and fsynced every 100 rows. Kill any
REM window and run this file again: --resume reads the keys already on disk and continues, losing
REM at most the rows since the last flush. Re-running when nothing was killed is harmless -- every
REM shard finds its own keys present and exits.
REM
REM Sizing is measured, not assumed: 0.25-0.54 s per enumerated design on the real PFAS genes
REM (929-row timing run, 2026-10-06), and 12.9% of designs pass the open_11 <= 4.0 ceiling and get
REM all four tubes. 160 pairs per gene pair x 3 gene pairs x 2 geometries x 6 stems x 96 grid
REM points is ~553,000 designs, so ~71,000 fully measured over ~960 (pair, geometry) cells.

setlocal
cd /d "%~dp0.."

set PAIRS=160
set STEMS=6
set OUT=axes_pfas
set EXTRA=

if /i "%1"=="control" (
  set OUT=axes_mcherry
  set PAIRS=60
  set EXTRA=--control
)

echo Launching 6 shards: out=%OUT% pairs=%PAIRS% stems=%STEMS% %EXTRA%
echo.

for %%i in (0 1 2 3 4 5) do (
  start "axes %OUT% shard %%i" /high /min cmd /c ^
    "uv run python tools\characterise_axes.py --out %OUT% --shard %%i/6 --pairs %PAIRS% --stems %STEMS% %EXTRA% --resume > tools\logs\%OUT%_%%i.log 2>&1"
)

echo Six windows started, minimised, at high priority.
echo Logs:   tools\logs\%OUT%_*.log
echo Status: tools\axes_status.cmd
endlocal
