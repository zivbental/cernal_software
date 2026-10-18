<#
.SYNOPSIS
  Measure the main_z + aug window in all four tubes, then score it against Green's 168.

.DESCRIPTION
  One command, six shards at High priority, resumable, and NOT subject to any background time limit
  because you are running it yourself in your own terminal.

  Two steps:

    1. complete_panel --metrics aug_z over the whole feasible set. The window is main_z (the 6 nt
       between the Shine-Dalgarno and the AUG) plus the AUG itself -- 9 contiguous nucleotides --
       as a JOINT opening cost in kcal/mol, in tubes 00, 01, 10 and 11, plus aug_z_sep, the worst
       OFF tube's cost minus the ON tube's.

    2. window_vs_green.py, which scores it against Green's 168 built-and-measured switches. The arm
       it would replace, f1, scores -0.107 there. This window has the same SHAPE as that failed
       separation, so resemblance to our own metrics proves nothing and only the external set
       decides. Nothing ranks on the new column until step 2 has an answer.

  RESUMABLE. Every shard skips designs whose row already carries both columns, so stopping this with
  Ctrl-C and running it again costs only what was unfinished. It writes to a fresh output name
  (completionswin_*) because a re-run into the existing completion files has twice failed to attempt
  designs the resume logic reports as unfinished -- that cause is still unexplained, and a fresh file
  measures everything by construction.

  COST, measured rather than estimated: 30 designs in 46.9 s is 1.56 s per design, so 7,238 designs
  is 3.1 hours on one core and about 31 MINUTES on six. One focused metric set, not --metrics all:
  everything here reads the same four tubes, where `all` would recompute a dozen columns already at
  100% coverage -- among them aug11_mean, which reproduces the stored aug_11 at rho +1.000.

  WHAT IT FILLS. Twelve columns, in two families that share their folds:
    aug_z_open_00/01/10/11 + aug_z_sep   the 9-nt main_z+aug window in all four tubes, kcal/mol
    eff_run_a_g0/g1/g2                   the longest duplex trigger A forms ANYWHERE in the switch
    land_run_g0/g1/g2 + land_site_nt     the same, restricted to sec_z + x* -- the 20 nt trigger
                                         B's binding frees, which is A's actual landing site

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File src/engine/gates/notebooks/toehold_and/run_window.ps1
#>
[CmdletBinding()]
param(
    [int]$Shards = 6,
    [switch]$SkipGreen,
    [switch]$NoPriority
)

$ErrorActionPreference = 'Stop'
$NB = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $NB '..\..\..\..\..')).Path
$Logs = Join-Path $NB 'results\logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

Write-Host ''
Write-Host ('=' * 78)
Write-Host '  Step 1 of 2  --  the window AND the effective toehold, in one pass'
Write-Host ('=' * 78)

$procs = @()
for ($i = 0; $i -lt $Shards; $i++) {
    $log = Join-Path $Logs "win_$i.log"
    $argv = @('run', 'python', (Join-Path $NB 'complete_panel.py'),
        '--metrics', 'window_and_toehold', '--out', 'completionswin', '--shard', "$i/$Shards")
    $p = Start-Process -FilePath 'uv' -ArgumentList $argv -WorkingDirectory $Repo `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -NoNewWindow -PassThru
    if (-not $NoPriority) { try { $p.PriorityClass = 'High' } catch { } }
    $procs += $p
    Write-Host ("  shard {0}/{1} started, pid {2}" -f $i, $Shards, $p.Id)
}
Write-Host "  waiting. Progress: Get-Content $Logs\win_0.log -Tail 3 -Wait"
$procs | Wait-Process

$failed = @($procs | Where-Object { $_.ExitCode -ne 0 })
foreach ($p in $failed) {
    Write-Warning ("  pid {0} exited {1} -- see results\logs" -f $p.Id, $p.ExitCode)
}
if ($failed.Count -eq $procs.Count) {
    throw 'every shard failed; not scoring a column that was never measured'
}
Write-Host ("  {0} of {1} shards finished cleanly" -f ($procs.Count - $failed.Count), $procs.Count)

# Coverage before anything reads a number off the column. A metric can be computed, written, and
# still be invisible -- it has happened three times in this notebook, at three different gates -- so
# the count is checked here rather than assumed.
Write-Host ''
Write-Host '  coverage on the gating set:'
Push-Location $Repo
try {
    & uv run python -c @'
import sys
from pathlib import Path
NB = Path("src/engine/gates/notebooks/toehold_and").resolve()
sys.path.insert(0, str(NB.parents[4] / "src")); sys.path.insert(0, str(NB))
import objective_panel as op
rank = op.gating(op.population(NB / "results", quiet=True))
for column in ("aug_z_open_00", "aug_z_open_01", "aug_z_open_10", "aug_z_open_11",
               "aug_z_sep", "eff_run_a_g0", "eff_run_a_g1", "eff_run_a_g2",
               "land_site_nt", "land_run_g0", "land_run_g1", "land_run_g2"):
    n = sum(1 for r in rank if r.get(column) is not None)
    flag = "" if n >= len(rank) * 0.99 else "   <- GAP"
    print(f"    {column:16s}{n:>7,} of {len(rank):,}  {100 * n / max(len(rank), 1):5.1f}%{flag}")
'@
}
finally { Pop-Location }

if ($SkipGreen) {
    Write-Host ''
    Write-Host '  -SkipGreen: stopping before the validation. The column ranks nothing until it has'
    Write-Host '  been scored against Green, so run window_vs_green.py before using it.'
    exit 0
}

Write-Host ''
Write-Host ('=' * 78)
Write-Host "  Step 2 of 2  --  against Green's 168 measured switches"
Write-Host ('=' * 78)
Push-Location $Repo
try {
    & uv run python (Join-Path $NB 'window_vs_green.py')
}
finally { Pop-Location }

Write-Host ''
Write-Host '  Done. The verdict to read: does the new window beat f1 (-0.107) on Green''s 168?'
Write-Host '  If it does not, it stays reported and ranks nothing.'
