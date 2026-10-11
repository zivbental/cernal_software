@echo off
REM ============================================================================
REM Finish the grid the overnight run left half-measured.
REM
REM WHAT HAPPENED. The overnight run used --grid-stride 2, which makes each shard
REM walk every second CLOSURE BLOCK. Jobs are split across shards as
REM jobs[index::shards], so each cell is handled by exactly one shard -- measured,
REM 0 of 420 cells were touched by more than one -- and that shard covered only
REM half of that cell's closure blocks. The result is a table that looks complete
REM and is not:
REM
REM     150,700 designs, 110,018 fully measured, 420 cells, all 16 closures
REM     but per cell: min 32, median 48, max 64 of the 96 grid points
REM     17,984 of 40,320 grid points missing  ->  44.6% of the grid
REM
REM The closures all APPEAR because different shards covered different blocks.
REM What is missing is the within-cell comparison: a paired test needs a design
REM and its control in the same cell, and half the cell is absent.
REM
REM WHAT THIS DOES. The same run with --grid-stride 1, so each shard walks all 16
REM closure blocks for its own cells. --resume keys on the full axis tuple --
REM gene_a>gene_b|x_start|xstar_start|len_x|geom|stem_index|closure|upper3|lower3
REM -- so every row already on disk is skipped and only the gaps are built.
REM
REM EVERY OTHER SETTING IS IDENTICAL AND MUST STAY THAT WAY. The job list, the
REM window pairs and the stems selected per pair all depend on --pairs,
REM --pair-order and --stems. Change one and --resume stops matching, the shards
REM build different cells, and the table becomes two datasets in one file.
REM
REM SIZE, measured rather than estimated: about 152,000 designs to build, which is
REM the same order as the run that just finished -- so expect 9 to 18 hours across
REM six shards, not an evening. It is safe to stop and restart: --resume loses at
REM most the design in flight.
REM ============================================================================
setlocal
cd /d "%~dp0.."
if not exist tools\logs mkdir tools\logs

REM Identical to tools\run_axes.cmd except STRIDE.
set OUT=axes_c8
set PAIRS=70
set STRIDE=1
set CEIL=8.0

echo.
echo   Completing the grid for %OUT%.
echo     pairs=%PAIRS% per gene pair   grid-stride=%STRIDE% (the whole grid)   on-ceiling=%CEIL%
echo     --resume skips every row already on disk; only the gaps are built.
echo.
echo   Measured gap: 17,984 of 40,320 grid points, about 152,000 designs.
echo   This is a long run. Stopping and restarting is safe.
echo.

for %%i in (0 1 2 3 4 5) do start "complete %OUT% %%i" /high /min cmd /c "uv run python tools\characterise_axes.py --out %OUT% --shard %%i/6 --pairs %PAIRS% --grid-stride %STRIDE% --on-ceiling %CEIL% --resume > tools\logs\%OUT%_complete_%%i.log 2>&1"

echo   Six windows started, minimised, at high priority.
echo     logs      tools\logs\%OUT%_complete_*.log
echo     status    tools\axes_status.cmd
echo     coverage  uv run python tools\audit_grid_coverage.py --out %OUT%
echo     analysis  uv run python tools\analyse_levers.py --out %OUT%
echo.
endlocal
