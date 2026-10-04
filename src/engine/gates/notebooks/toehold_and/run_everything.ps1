<#
.SYNOPSIS
  One command. Six shards at a time, High priority, resumable, no manual steps.

.DESCRIPTION
  Runs, in order:

    1. the new ON metric    rbs_aug_open_11/_00 -- the JOINT cost of opening the Shine-Dalgarno,
                            main_z and the AUG as one contiguous 20-nt stretch, in tube 11
    2. the effective toehold eff_toehold_a and eff_run_a_g0/g1/g2 -- the longest real DUPLEX run
                            trigger A forms, contiguous on both strands, at each gap size, plus
                            eff_run_lo/hi so the run can be read against the domain map
    3. the rare-codon rescue -- designs the screen deletes, recovered by a wobble that keeps
                            trigger A's grip, then scored like any other design
    4. the panel and report rebuilt on the result

  Forced lower3 levels come back automatically: objective_panel now counts how many of the stem's
  bottom 3 each design costs trigger A and keeps the ones costing at most one. Nothing to pass.

  SAFETY. Each phase runs six processes, one per shard, and waits for them. They are never
  interleaved across phases, so at most six folding processes exist at once -- which is what keeps
  memory flat: each holds its own FoldEngine cache and nothing accumulates across phases. Every
  phase is resumable: complete_panel skips designs whose row already carries the metrics it was
  asked for, so re-running this script after a stop costs only what was not finished.

.PARAMETER Shards
  How many concurrent processes per phase. Default 6.

.PARAMETER SkipTo
  Start at a later phase: metrics, toehold, rescue, panel.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File src\engine\gates\notebooks\toehold_and\run_everything.ps1
#>
[CmdletBinding()]
param(
    [int]$Shards = 6,
    [ValidateSet('metrics', 'toehold', 'rescue', 'panel')]
    [string]$SkipTo = 'metrics',
    [switch]$NoPriority
)

$ErrorActionPreference = 'Stop'
$NB = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $NB '..\..\..\..\..')).Path
$Logs = Join-Path $NB 'results\logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

$phases = @('metrics', 'toehold', 'rescue', 'panel')
$from = [array]::IndexOf($phases, $SkipTo)

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 78)
    Write-Host "  $Text"
    Write-Host ('=' * 78)
}

# Launches one process per shard, raises them to High, and blocks until all have exited.
#
# Why Start-Process and not a job: a job would marshal every line of output back through the
# runspace, and these phases print a progress line per 500 designs across six shards. The output
# goes to its own file per shard instead, so nothing is buffered in memory and a stopped run leaves
# a readable log.
function Invoke-Shards {
    param(
        [string]$Label,
        [string]$Script,
        [string[]]$CommonArgs,
        [int]$Count
    )
    $procs = @()
    for ($i = 0; $i -lt $Count; $i++) {
        $log = Join-Path $Logs "$Label`_$i.log"
        $argv = @('run', 'python', (Join-Path $NB $Script)) + $CommonArgs + @(
            '--out', "completions_$i", '--shard', "$i/$Count")
        $p = Start-Process -FilePath 'uv' -ArgumentList $argv -WorkingDirectory $Repo `
            -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
            -NoNewWindow -PassThru
        if (-not $NoPriority) {
            # Set after launch: Start-Process has no priority parameter. Wrapped because a shard
            # that finishes in under a few milliseconds is already gone, and that is not an error.
            try { $p.PriorityClass = 'High' } catch { }
        }
        $procs += $p
        Write-Host ("  shard {0}/{1} started, pid {2}, log {3}" -f $i, $Count, $p.Id, (Split-Path $log -Leaf))
    }
    Write-Host '  waiting...'
    $procs | Wait-Process
    $failed = @($procs | Where-Object { $_.ExitCode -ne 0 })
    foreach ($p in $failed) {
        Write-Warning ("  pid {0} exited {1} -- see results\logs" -f $p.Id, $p.ExitCode)
    }
    if ($failed.Count -eq $procs.Count) {
        throw "every $Label shard failed; stopping rather than building a panel on nothing"
    }
    Write-Host ("  {0}: {1} of {2} shards finished cleanly" -f $Label, ($procs.Count - $failed.Count), $procs.Count)
}

# --- 1. the contiguous RBS-through-AUG opening, and 2. the effective toehold -------------------
#
# Two phases rather than one --metrics all, deliberately. `all` also recomputes columns we already
# have -- aug11_mean reproduces the stored aug_11 at rho +1.000 -- and each phase here is resumable
# on its own, so a stop in the middle of the toehold does not put the first phase's work at risk.
if ($from -le 0) {
    Write-Step 'Phase 1 of 4  --  the contiguous RBS-through-AUG opening (rbs_aug_open_11/_00)'
    Invoke-Shards -Label 'rbs_aug' -Script 'complete_panel.py' -Count $Shards `
        -CommonArgs @('--metrics', 'rbs_aug')
}

if ($from -le 1) {
    Write-Step 'Phase 2 of 4  --  the effective toehold of trigger A (gap 0, 1 and 2)'
    Invoke-Shards -Label 'toehold' -Script 'complete_panel.py' -Count $Shards `
        -CommonArgs @('--metrics', 'toehold_a')
}

# --- 3. the rare-codon rescue -----------------------------------------------------------------
if ($from -le 2) {
    Write-Step 'Phase 3 of 4  --  rescuing rare-codon designs with a wobble, then scoring them'
    $log = Join-Path $Logs 'rescue.log'
    & uv run python (Join-Path $NB 'rare_codon_rescue.py') --shards $Shards --out rescued_cheap `
        2>&1 | Tee-Object -FilePath $log
    $shardFiles = Get-ChildItem (Join-Path $NB 'results') -Filter 'rescued_cheap_*.csv' -ErrorAction SilentlyContinue
    if (-not $shardFiles) {
        Write-Warning '  nothing was rescued; skipping the scoring of rescued designs'
    }
    else {
        # TWO stages, not one, and the first was missing. The pipeline is
        #   X_cheap_*  --(full_sweep --stage fold --out X)-->  X_folded_*  --(objective_energy
        #   --from X)-->  objective rows
        # so `objective_energy --from rescued_cheap` looked for `rescued_cheap_folded_*.csv`, found
        # nothing, printed one line and exited 0 -- while the driver reported "rescued designs
        # scored". The rescue writes `rescued_cheap_i.csv`, which is exactly what
        # `--stage fold --out rescued` reads, so only the stage itself was absent.
        #
        # --closures is restricted to the six levels stage 1 actually wrote. The fold stage verifies
        # that every requested axis level is PRESENT in the cheap files and refuses the run if not,
        # which is correct -- a level added to the constants after a sweep ran is not in its rows --
        # and the ten closure cells added since would trip it on every call.
        Write-Host '  folding the rescued designs (stage 2)...'
        $procs = @()
        for ($i = 0; $i -lt $Shards; $i++) {
            $flog = Join-Path $Logs "rescued_fold_$i.log"
            $argv = @('run', 'python', (Join-Path $NB 'full_sweep.py'),
                '--stage', 'fold', '--fasta', (Join-Path $NB 'mCherry_original.txt'),
                '--out', 'rescued', '--pairs', '0', '--shard', "$i/$Shards",
                '--closures', 'open_3x3,closed_UAU,closed_CAU,closed_CGU,pair2_CCU,pair1_CCC')
            $p = Start-Process -FilePath 'uv' -ArgumentList $argv -WorkingDirectory $Repo `
                -RedirectStandardOutput $flog -RedirectStandardError "$flog.err" `
                -NoNewWindow -PassThru
            if (-not $NoPriority) { try { $p.PriorityClass = 'High' } catch { } }
            $procs += $p
            Write-Host ("  folding shard {0}/{1}, pid {2}" -f $i, $Shards, $p.Id)
        }
        $procs | Wait-Process
        if (-not (Get-ChildItem (Join-Path $NB 'results') -Filter 'rescued_folded*.csv' `
                    -ErrorAction SilentlyContinue)) {
            Write-Warning '  the fold stage produced no rescued_folded*.csv -- see results\logs'
        }

        # Then the scorer, on the FOLDED files: same objective_energy, same ON ceiling, same scheme
        # skips as the original sweep, so a rescued design is comparable with every other design.
        Write-Host '  scoring the rescued designs (stage 3)...'
        $procs = @()
        for ($i = 0; $i -lt $Shards; $i++) {
            $slog = Join-Path $Logs "rescued_score_$i.log"
            $argv = @('run', 'python', (Join-Path $NB 'objective_energy.py'),
                '--from', 'rescued', '--shard', "$i/$Shards", '--out', 'rescued_objective')
            $p = Start-Process -FilePath 'uv' -ArgumentList $argv -WorkingDirectory $Repo `
                -RedirectStandardOutput $slog -RedirectStandardError "$slog.err" `
                -NoNewWindow -PassThru
            if (-not $NoPriority) { try { $p.PriorityClass = 'High' } catch { } }
            $procs += $p
            Write-Host ("  scoring shard {0}/{1}, pid {2}" -f $i, $Shards, $p.Id)
        }
        Write-Host '  waiting...'
        $procs | Wait-Process
        Write-Host '  rescued designs scored'
    }
}

# --- 4. the panel and the report ---------------------------------------------------------------
if ($from -le 3) {
    Write-Step 'Phase 4 of 4  --  rebuilding both panels and the report'
    Push-Location $Repo
    try {
        $panel = Join-Path $NB 'objective_panel.py'
        & uv run python $panel --six --geometry kim --out panel_six 2>&1 |
            Tee-Object -FilePath (Join-Path $Logs 'panel_six.log') | Select-Object -Last 24
        & uv run python $panel --six --geometry kim --lower3 wobble_GU,trigger_derived `
            --out panel_lower3 2>&1 | Tee-Object -FilePath (Join-Path $Logs 'panel_lower3.log') |
            Select-Object -Last 4
        & uv run python (Join-Path $NB 'report\panel_data.py') panel_six panel_lower3 2>&1 |
            Select-Object -Last 4
        & uv run python (Join-Path $NB 'build_report.py') 2>&1 | Select-Object -Last 4
    }
    finally { Pop-Location }
}

Write-Step 'Done'
Write-Host "  logs: $Logs"
Write-Host '  re-run this script to resume -- every phase skips the designs it already measured.'
