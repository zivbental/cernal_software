# Finish the RBS-open completions across all six shards.
#
#   pwsh -File run_completions.ps1              # score what is missing
#   pwsh -File run_completions.ps1 -Rejoin      # refresh the joins only, no folding
#   pwsh -File run_completions.ps1 -Status      # how far it has got
#
# WHY A SCRIPT. Six manual invocations is six chances to mistype a shard index, and the one
# command that failed did so on a path: the script must be launched from the repo ROOT, which
# this file guarantees by cd-ing there itself rather than trusting where it was called from.
#
# Shards run CONCURRENTLY, one process each. Safe to fork: nothing in complete_panel.py touches
# RNA.cvar, and the temperature travels on an explicit RNA.md() inside FoldEngine. Each shard
# writes its own completions_<i>.csv, so there are no concurrent appends to one file.
#
# Everything resumes. Re-run it after a kill and it picks up where it stopped.

param(
    [int]$Shards = 6,
    [switch]$Rejoin,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
# Moved here from the repo root, where it used to sit beside the thing it drives. Its paths
# are relative to the REPO ROOT, which is five directories up from this file -- the same
# anchor run_fill.ps1 and status.ps1 use.
$root = (Resolve-Path "$PSScriptRoot\..\..\..\..\..").Path
Set-Location $root
$script = "src/engine/gates/notebooks/toehold_and/complete_panel.py"

if (-not (Test-Path $script)) {
    Write-Host "cannot find $script -- is this the repo root?" -ForegroundColor Red
    exit 1
}

if ($Status) {
    & uv run python $script --status
    exit $LASTEXITCODE
}

# --rejoin rewrites each shard's file in place, so it must NOT run while a scoring pass is
# writing to the same files.
$live = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -EA SilentlyContinue |
          Where-Object { $_.CommandLine -like "*complete_panel*" })
if ($live.Count -gt 0) {
    Write-Host "$($live.Count) complete_panel process(es) already running." -ForegroundColor Yellow
    Write-Host "Stop them first, or use -Status to watch." -ForegroundColor Yellow
    exit 1
}

$mode = if ($Rejoin) { "refreshing joins" } else { "scoring rbs11_open" }
Write-Host "$mode across $Shards shards" -ForegroundColor Cyan

$procs = @()
foreach ($i in 0..($Shards - 1)) {
    $argv = @("run", "python", $script, "--shard", "$i/$Shards")
    if ($Rejoin) { $argv += "--rejoin" }
    $p = Start-Process -FilePath "uv" -ArgumentList $argv -PassThru -WindowStyle Hidden `
         -RedirectStandardOutput "completions_$i.log" -RedirectStandardError "completions_$i.err"
    $procs += $p
    Write-Host ("  shard {0} -> pid {1}" -f $i, $p.Id)
}

Write-Host ""
Write-Host "Logs: completions_<i>.log   Progress: pwsh -File run_completions.ps1 -Status"
Write-Host "Waiting..." -ForegroundColor Cyan
$procs | Wait-Process
Write-Host ""
& uv run python $script --status
