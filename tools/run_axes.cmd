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
REM     uv run python tools\analyse_levers.py --out axes_pfas
REM
REM  The second one is the conditional analysis: did each design decision help, asked only where
REM  the lever had work to do, and paired inside a (pair, geometry) cell. Safe to run while the
REM  shards are working -- it only reads.
REM
REM  Each shard writes results\axes_pfas_<i>.csv, flushed and fsynced every 100 rows. Kill any
REM  window and run the same line again: --resume reads the keys already on disk and continues,
REM  losing at most the rows since the last flush.
REM
REM  ---------------------------------------------------------------------------------------
REM  WHAT THIS RUN MEASURES THAT THE LAST ONE DID NOT
REM
REM   * the state-10 leak on EVERY design. `xstar_engA_10` and `mainpre_engA_10` used to be
REM     produced only after the open_11 ceiling passed, so no row carried them for a rejected
REM     design -- 0 of 2,408 in the sample. Measured since: Spearman -0.500 between open_11 and
REM     xstar_engA_10, so the ceiling is not independent of the leak it does not look at, and a
REM     threshold calibrated on survivors is calibrated on a population the ceiling shaped.
REM   * 21 metrics read off Green's and VISTA's published switches that the engine never
REM     computed, `ied_rbs_linker_{state}` first among them -- the strongest single metric on both
REM     Green libraries (+0.356 / +0.390). All free: the matrix per state was already built.
REM   * 14 lever columns, so a design decision's effect is estimable at all. Without
REM     `lower3_strong_before` the wobble lever reads as 17.7% against 16.4%, which is the 43.3%
REM     of designs it never touched diluting the 56.7% it did.
REM
REM  ---------------------------------------------------------------------------------------
REM  WHY THE CEILING IS 8.0 AND NOT 4.0. `open_11` is recorded for every design even when the
REM  ceiling stops it, so the whole distribution is known: median 5.41, and 30.0% of designs sit
REM  at or below 4.0 against 77.3% below 8.0. Two consequences.
REM
REM   * A threshold can only be swept DOWNWARD after the fact. At a ceiling of 4.0 nothing above
REM     it was ever fully measured, so "what would a ceiling of 8 have given" is unanswerable --
REM     and a sensitivity analysis is something the judging criteria ask for by name.
REM   * It is also the one open scientific question. The closures that GATE best are the ones the
REM     ceiling rejects: `closed_CAU` gates 34.1% of its survivors and survives only 7.5%, against
REM     `open_3x3` at 12.6% and 35.1%. Whether 4.0 is the right line cannot be decided from data
REM     in which everything above it is unmeasured.
REM
REM  Measured, not assumed: 0.861 s per design at ceiling 8.0 over 900 designs, against 0.957 s at
REM  ceiling 4.0 over the 431,916-design run. So raising it is NOT the 2.58x the pass-rate ratio
REM  suggests -- a design the ceiling stops still pays the expensive three-strand `open_11` fold
REM  and the state-10 matrix, and only the three OFF tubes and the barrier are saved.
REM
REM  SIZING. The per-design cost above is measured on 900 designs across 2 trigger pairs, which is
REM  a small sample of pairs; each shard prints its OWN rate every 100 rows and that is the one to
REM  read. 70 pairs per gene pair = 210 pairs x 864 designs = 181,440 designs, about 8 hours on
REM  six cores at 0.9 s. The old estimate-from-components line it replaces said 1.65 s and was
REM  wrong by nearly half.
REM
REM  (superseded) The per-design cost was an ESTIMATE FROM COMPONENTS, not a measured rate: 0.25 s for
REM  a design the ceiling stops, plus 0.86 s for the state-10 matrix it now always pays, plus
REM  3.5 s for a fully measured one (whose state-10 matrix is already cached) -- about 1.65 s per
REM  design at the measured 22.8% pass rate. Each shard prints its OWN rate every 100 rows; read
REM  that and not this.
REM
REM  --grid-stride 2 takes every second closure BLOCK and all six (upper3 x lower3) points
REM  inside it, with the offset rotating per shard. Blocks and not points: a design and its
REM  control differ in one axis and sit at ADJACENT grid positions, so no point stride can take
REM  both -- measured, a coprime point stride covered every level of every axis and left the
REM  conditional analysis with ZERO matched pairs. With blocks it is 100% of points, and the six
REM  shards cover all 16 closures between them.
REM
REM    designs per trigger pair = 2 geometries x ~9 stems x 48 grid points = 864
REM    120 pairs -> 103,680 designs -> about 48 core-hours -> about 8 hours on six cores
REM
REM  If it overruns, nothing is lost: kill the windows, the rows are on disk and analysable. If it
REM  finishes early, raise PAIRS and run the same line again -- resume keeps the work done.
REM ===========================================================================================

setlocal
cd /d "%~dp0.."
if not exist tools\logs mkdir tools\logs

set OUT=axes_c8
set PAIRS=70
set STRIDE=2
set CEIL=8.0
set EXTRA=

if /i "%1"=="control" (
  REM The mCherry control: both windows from one transcript, comparable with every earlier sweep.
  REM A cross-check, not a second dataset.
  set OUT=axes_mcherry
  set PAIRS=20
  set EXTRA=--control
)
if /i "%1"=="smoke" (
  REM Proves the six windows launch and write, in about a minute. Delete the files afterwards.
  set OUT=axes_smoke
  set PAIRS=1
  set STRIDE=4
  set EXTRA=--limit 60
)

echo Launching 6 shards:  out=%OUT%  pairs=%PAIRS% per gene pair  grid-stride=%STRIDE%  on-ceiling=%CEIL%  %EXTRA%
echo.

for %%i in (0 1 2 3 4 5) do start "axes %OUT% %%i" /high /min cmd /c "uv run python tools\characterise_axes.py --out %OUT% --shard %%i/6 --pairs %PAIRS% --grid-stride %STRIDE% --on-ceiling %CEIL% %EXTRA% --resume > tools\logs\%OUT%_%%i.log 2>&1"

echo Six windows started, minimised, at high priority.
echo   logs      tools\logs\%OUT%_*.log
echo   status    tools\axes_status.cmd %1
echo   analysis  uv run python tools\analyse_levers.py --out %OUT%
endlocal
