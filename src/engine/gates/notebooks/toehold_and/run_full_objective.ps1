<#
Score the A0 sweep with the energy objective, most informative designs first.

    .\run_full_objective.ps1

That is the whole command, from PowerShell in the repo root. The .sh version needs Git Bash;
this one does not, which is why it exists.

    .\run_full_objective.ps1 -Shards 4      fewer processes if the machine swaps
    .\run_full_objective.ps1 -Phase phase1  stop after the closed closures

Default is 5 shards, chosen for this machine: 6 PHYSICAL cores (12 logical are hyperthreads,
which buy little on CPU-bound folding) and about 3 GB of free RAM against roughly 400 MB per
process. Five leaves a core for everything else. Ten would oversubscribe and swap.

Timing at 1.47 s/design measured: phase 1 of p3 is about 3.4 h on 5 shards, and a panel is
written after every family, so the first usable panel lands then. Everything streams to CSV
and resumes, so Ctrl-C is safe and re-running continues from where it stopped.

Ordering, and why: A-anchored and unlocked are skipped (0 of 4,330 and 0 of 384 gating, with a
known mechanism). Families go by measured gating rate, p3 first at 75%. The five closed
closures (~55% gating) come before open_3x3 (14.3%, but 17% of the sweep).
#>
param(
  [int]$Shards = 5,
  [ValidateSet('all','phase1')] [string]$Phase = 'all'
)

$ErrorActionPreference = 'Stop'
# Moved here from the repo root, where it used to sit beside the thing it drives. Its paths
# are relative to the REPO ROOT, which is five directories up from this file -- the same
# anchor run_fill.ps1 and status.ps1 use.
Set-Location -Path (Resolve-Path "$PSScriptRoot\..\..\..\..\..").Path

$obj    = 'src/engine/gates/notebooks/toehold_and/objective_energy.py'
$panel  = 'src/engine/gates/notebooks/toehold_and/objective_panel.py'
$res    = 'src/engine/gates/notebooks/toehold_and/results'
$fasta  = 'mCherry_original.txt'
$closed = 'closed_CAU,closed_CGU,closed_UAU,pair1_CCC,pair2_CCU'
$fams   = @('p3','p1','k1','p2','wob','prev')

function Invoke-Family {
  param([string]$Family, [string]$Closures, [string]$Label)

  Write-Host ''
  Write-Host "=== $Family [$Label] ===" -ForegroundColor Cyan

  # The accessibility table first, single-threaded. Every shard appends to one shared CSV and
  # concurrent appends corrupt it. Restricted to this family, so it is minutes rather than an hour.
  & uv run python $obj --from $Family --out "obj_full_$Family" --fasta $fasta `
      --closure $Closures --access-only

  $jobs = @()
  foreach ($i in 0..($Shards - 1)) {
    $log = Join-Path $env:TEMP "obj_${Family}_${Label}_$i.log"
    $jobs += Start-Process -FilePath 'uv' -PassThru -NoNewWindow `
      -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
      -ArgumentList @('run','python',$obj,'--from',$Family,'--out',"obj_full_$Family",
                      '--fasta',$fasta,'--closure',$Closures,'--shard',"$i/$Shards")
  }
  # High priority, as asked. Set here rather than by hand because each family starts new processes.
  Start-Sleep -Seconds 3
  foreach ($j in $jobs) {
    try { (Get-Process -Id $j.Id).PriorityClass = 'High' } catch { }
  }
  $jobs | Wait-Process

  $rows = (Get-ChildItem "$res/obj_full_${Family}_*.csv" -ErrorAction SilentlyContinue |
           Get-Content | Where-Object { $_ -notlike 'switch,*' }).Count
  Write-Host "--- $Family done, rows so far: $rows"
  & uv run python $panel --want 12 --out panel_energy | Select-Object -Last 20
  Write-Host "--- panel refreshed: $res/panel_energy.csv" -ForegroundColor Green
}

Write-Host "###### phase 1: the closed closures ($Shards shards) ######" -ForegroundColor Yellow
foreach ($f in $fams) { Invoke-Family -Family $f -Closures $closed -Label 'closed' }

if ($Phase -eq 'phase1') {
  Write-Host ''
  Write-Host 'stopping after phase 1 as asked'
  exit 0
}

Write-Host ''
Write-Host '###### phase 2: open_3x3 ######' -ForegroundColor Yellow
foreach ($f in $fams) { Invoke-Family -Family $f -Closures 'open_3x3' -Label 'open3x3' }

Write-Host ''
Write-Host '###### done ######' -ForegroundColor Yellow
& uv run python $panel --want 12 --out panel_energy | Select-Object -Last 20
