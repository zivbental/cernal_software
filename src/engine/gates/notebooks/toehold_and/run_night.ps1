# One command for an unattended night on the A0 sweep.
#
#   pwsh -File src/engine/gates/notebooks/toehold_and/run_night.ps1
#
# Three folding phases on six cores, with analysis after each. Everything resumes, so this
# script is safe to re-run: after a crash, a reboot or a Ctrl-C it picks up where it stopped
# and re-folds at most the last 25 designs per shard.
#
# WHAT IT DOES, AND WHY IN THIS ORDER
#
#   Phase 1  B-anchored pair-stems x 36 axis points (closure 6, upper3 AUA/UAU,
#            lower3 2S1W, island trigger-derived). Breadth: every B-anchored pair-stem,
#            which is exactly what block A could not sample -- it drew its top 12 from 3.
#   Phase 2  The same grid on the MIXED scheme. This is the control on "B-anchored for
#            now": the two schemes differ by 5.2 kcal/mol at the A-site while their locks
#            match, and nothing has measured whether that matters.
#   Phase 3  The 150 leading pair-stems from phases 1 and 2, against the FULL 360-point
#            grid. The narrow grid buys breadth; this buys the axis resolution back on the
#            designs that earned it.
#
# Roughly 9.2 + 5.9 + 5.6 hours of folding, measured at the 0.45 designs/s per shard this
# machine sustains with six shards running. That is ~21 h of a 24 h budget.
#
# WHAT IT DELIBERATELY DOES NOT DO
#
#   The 20-nt secondary arm (invasion 17, AUA cap) and the toehold_trim axis both change a
#   domain LENGTH, which is a change to the gate's layout rather than a patch to a built
#   switch. Neither is implemented or validated, and neither belongs in an unattended run.
#   The toehold is MEASURED here instead: toehold_metric.py reports how open r2's 3' end is
#   without changing the molecule.

param(
    # Stop any sweep already running and take over. Without this the script refuses to start
    # on top of a live run, because two writers on one shard file interleave rows silently.
    [switch]$StopRunning
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $root

$fasta   = "src/engine/gates/notebooks/toehold_and/mCherry original.txt"
$sweep   = "src/engine/gates/notebooks/toehold_and/full_sweep.py"
$results = "src/engine/gates/notebooks/toehold_and/results"
$logs    = "$results/logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# One shard per physical core. Hyperthreads do not help a CPU-bound fold and cost memory.
$shards = 6

function Say($text) {
    Write-Host ""
    Write-Host "=== $(Get-Date -Format 'HH:mm:ss')  $text ==="
    Write-Host ""
}

# Two processes appending to one shard file interleave their rows and the damage is silent:
# the file still parses, it just holds nonsense. So a live sweep either stops first or this
# script does not start.
function Get-LiveSweeps {
    @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -match 'full_sweep' })
}

$live = Get-LiveSweeps
if ($live.Count -gt 0) {
    if (-not $StopRunning) {
        Write-Host ""
        Write-Host "REFUSING TO START: $($live.Count) full_sweep process(es) are already running."
        Write-Host "Two writers on one shard file corrupt it silently."
        Write-Host ""
        Write-Host "Re-run with -StopRunning to stop them and take over:"
        Write-Host ""
        Write-Host "    pwsh -File src/engine/gates/notebooks/toehold_and/run_night.ps1 -StopRunning"
        Write-Host ""
        Write-Host "Every phase resumes, so stopping costs at most the last 25 designs per"
        Write-Host "shard -- about a minute of folding."
        exit 1
    }
    Say "stopping $($live.Count) running sweep process(es)"
    foreach ($p in $live) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  stopped pid $($p.ProcessId)"
    }
    # Windows releases the file handles a moment after the process dies; appending before
    # that yields a sharing violation and would kill the phase on its first batch.
    Start-Sleep -Seconds 5
    $still = Get-LiveSweeps
    if ($still.Count -gt 0) {
        Write-Host "  ** $($still.Count) process(es) survived; stop them by hand before retrying **"
        exit 1
    }
    Write-Host "  all stopped"
}

function Fold-Phase($name, $extra) {
    Say "$name : launching $shards shards"
    $jobs = @()
    for ($i = 0; $i -lt $shards; $i++) {
        # The FASTA name contains a space. Start-Process joins -ArgumentList with spaces and
        # quotes nothing, so paths must carry their own quotes or argparse sees two
        # arguments and every shard dies on startup.
        $argv = @("run", "python", "`"$sweep`"", "--fasta", "`"$fasta`"",
                  "--stage", "fold", "--out", $name, "--block", "C",
                  "--shard", "$i/$shards", "--resume") + $extra
        $jobs += Start-Process -FilePath "uv" -ArgumentList $argv -PassThru -NoNewWindow `
            -RedirectStandardOutput "$logs/${name}_$i.log" `
            -RedirectStandardError  "$logs/${name}_$i.err"
    }
    Write-Host "  pids: $($jobs.Id -join ', ')   (tail $logs/${name}_0.log to watch)"
    $jobs | Wait-Process
    $done = 0
    for ($i = 0; $i -lt $shards; $i++) {
        $f = "$results/${name}_folded_$i.csv"
        if (Test-Path $f) { $done += ((Get-Content $f | Measure-Object -Line).Lines - 1) }
        $err = "$logs/${name}_$i.err"
        if ((Test-Path $err) -and (Get-Item $err).Length -gt 0) {
            Write-Host "  ** shard $i wrote to stderr; first lines: **"
            Get-Content $err -TotalCount 5 | ForEach-Object { Write-Host "     $_" }
        }
    }
    Say "$name : finished, $done designs folded"
}

function Analyse($name, $tail) {
    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --out $name `
        *> "$logs/${name}_analysis.log"
    Get-Content "$logs/${name}_analysis.log" -Tail $tail
}

$cheap = "$results/sweep_cheap.csv"
if (-not (Test-Path $cheap)) { throw "$cheap not found -- run --stage cheap first" }
# Each phase gets its own copy of the stage-1 file, so a folded output can always be traced
# back to the sweep it came from without guessing.
foreach ($p in @("p1", "p2")) {
    if (-not (Test-Path "$results/${p}_cheap.csv")) { Copy-Item $cheap "$results/${p}_cheap.csv" }
}

Say "TOEHOLD ACCESSIBILITY (a measurement, not an axis)"
uv run python src/engine/gates/notebooks/toehold_and/toehold_metric.py `
    --fasta "$fasta" --out toehold *> "$logs/toehold.log"
Get-Content "$logs/toehold.log" -Tail 14

$narrow = @("--upper3", "WWW_AUA,WWW_UAU", "--lower3", "SSW,SWS,WSS",
            "--island", "trigger_derived")

Fold-Phase "p1" (@("--scheme", "B-anchored") + $narrow)
Analyse "p1" 45

Fold-Phase "p2" (@("--scheme", "mixed") + $narrow)
Analyse "p2" 45

Say "PICKING LEADERS from phases 1 and 2"
uv run python src/engine/gates/notebooks/toehold_and/pick_leaders.py `
    --from p1,p2 --source sweep --top 150 --out p3 *> "$logs/leaders.log"
Get-Content "$logs/leaders.log"

# Phase 3 takes no scheme filter and no axis restriction: the full 360-point grid, on the
# 150 pair-stems that earned it, drawn from whichever scheme produced them.
Fold-Phase "p3" @()
Analyse "p3" 70

Say "ALL PHASES COMPLETE"
Write-Host "  p1_folded_*.csv   B-anchored breadth, 36 axes"
Write-Host "  p2_folded_*.csv   mixed scheme, same grid -- the control on 'B-anchored for now'"
Write-Host "  p3_folded_*.csv   150 leading pair-stems, full 360-axis grid"
Write-Host "  toehold.csv       r2 3'-end openness per trigger pair, joins on the pair key"
Write-Host ""
Write-Host "  Re-read any of them with:"
Write-Host "    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --out p3"
