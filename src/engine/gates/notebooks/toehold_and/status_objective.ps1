<#
Progress of the background objective run.

    .\status.ps1            one snapshot
    .\status.ps1 -Watch     refresh every 60 s until Ctrl-C

Reports the rate actually measured over the last interval rather than the rate I estimated,
because those have differed by 2x: five shards on six physical cores give about a 2x speed-up,
not 5x.
#>
param([switch]$Watch, [int]$Every = 60)

# Moved here from the repo root, and renamed: a DIFFERENT status.ps1 already lived in this
# directory. That one reports whatever sweep is running; this one watches the objective run
# and measures the rate over the last interval. Both are kept because they answer different
# questions, and a name collision would have silently replaced one with the other.
#
# `results` is now a sibling of this file rather than five directories down.
$res = Join-Path $PSScriptRoot 'results'

$closed = @('closed_CAU','closed_CGU','closed_UAU','pair1_CCC','pair2_CCU')

function Get-Snapshot {
  $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
           Where-Object { $_.CommandLine -match 'objective_energy' }

  $stage = 'idle'
  $family = '?'
  if ($procs) {
    $family = if ($procs[0].CommandLine -match '--from (\S+)') { $matches[1] } else { '?' }
    $stage  = if ($procs.CommandLine -match 'access-only') { 'accessibility table' } else { 'scoring' }
  }

  $scored = @{}
  foreach ($f in Get-ChildItem "$res\obj_full_*.csv" -ErrorAction SilentlyContinue) {
    if ($f.Name -match 'obj_full_([a-z0-9]+)_\d+\.csv') {
      $fam = $matches[1]
      $n = [Math]::Max(0, (Get-Content $f.FullName -ReadCount 0).Count - 1)
      $scored[$fam] = ($scored[$fam] + $n)
    }
  }

  [pscustomobject]@{
    When    = Get-Date
    Procs   = ($procs | Measure-Object).Count
    Family  = $family
    Stage   = $stage
    Scored  = $scored
    Total   = ($scored.Values | Measure-Object -Sum).Sum
    Access  = if (Test-Path "$res\accessibility_penalty.csv") {
                [Math]::Max(0,(Get-Content "$res\accessibility_penalty.csv" -ReadCount 0).Count - 1)
              } else { 0 }
    CPU     = [Math]::Round((($procs | ForEach-Object {
                (Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue).CPU
              } | Measure-Object -Sum).Sum), 0)
  }
}

# Designs remaining per family in phase 1, so the estimate is against real work and not a guess.
function Get-Remaining {
  $sql = @"
SELECT regexp_extract(filename, '([a-z0-9]+)_folded', 1) AS fam, count(*) AS n
FROM read_csv_auto('$($res -replace '\\','/')/*_folded_*.csv', union_by_name=true, filename=true)
WHERE switch IS NOT NULL AND scheme NOT IN ('A-anchored','unlocked')
  AND closure IN ('$($closed -join "','")')
GROUP BY 1
"@
  try {
    $py = "import duckdb;[print(f'{r[0]}={r[1]}') for r in duckdb.connect().execute('''$sql''').fetchall()]"
    $out = & uv run python -c $py 2>$null
    $h = @{}
    foreach ($line in $out) { if ($line -match '^(\w+)=(\d+)$') { $h[$matches[1]] = [int]$matches[2] } }
    return $h
  } catch { return @{} }
}

$plan = Get-Remaining
$prev = $null

do {
  $s = Get-Snapshot
  if ($Watch) { try { Clear-Host } catch { } }
  Write-Host "A0 objective run - $($s.When.ToString('HH:mm:ss'))" -ForegroundColor Cyan
  Write-Host ("  {0} python process(es)   stage: {1}   family: {2}   accessibility rows: {3}" -f `
              $s.Procs, $s.Stage, $s.Family, $s.Access)
  if ($s.Procs -eq 0) { Write-Host '  NOTHING RUNNING' -ForegroundColor Yellow }
  Write-Host ''
  Write-Host ("  {0,-8} {1,10} {2,10} {3,8}" -f 'family','scored','phase 1','done')
  foreach ($fam in @('p3','p1','k1','p2','wob','prev')) {
    $done = [int]$s.Scored[$fam]
    $want = if ($plan.ContainsKey($fam)) { $plan[$fam] } else { 0 }
    $pct  = if ($want) { '{0,6:N1}%' -f (100.0 * $done / $want) } else { '     -' }
    Write-Host ("  {0,-8} {1,10:N0} {2,10:N0} {3,8}" -f $fam, $done, $want, $pct)
  }
  $wantAll = ($plan.Values | Measure-Object -Sum).Sum
  Write-Host ("  {0,-8} {1,10:N0} {2,10:N0}" -f 'TOTAL', $s.Total, $wantAll)

  if ($prev) {
    $dt = ($s.When - $prev.When).TotalMinutes
    $dn = $s.Total - $prev.Total
    if ($dt -gt 0 -and $dn -gt 0) {
      $rate = $dn / $dt
      $left = [Math]::Max(0, $wantAll - $s.Total)
      Write-Host ''
      Write-Host ("  measured rate: {0:N0} designs/min   remaining: {1:N0}   ETA phase 1: {2:N1} h" -f `
                  $rate, $left, ($left / $rate / 60)) -ForegroundColor Green
    }
  } else {
    Write-Host ''
    Write-Host '  (rate appears after the second reading)' -ForegroundColor DarkGray
  }
  $prev = $s

  if ($Watch) { Start-Sleep -Seconds $Every }
} while ($Watch)
