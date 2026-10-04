# Live view of whatever run_night.ps1 is doing. Read-only: Ctrl+C stops watching, never the run.
#   pwsh -File src/engine/gates/notebooks/toehold_and/watch.ps1
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $root
$results = "src/engine/gates/notebooks/toehold_and/results"
$targets = @{ p1 = 91908; p2 = 57276; p3 = 54000 }   # rough totals, for the percentage only
while ($true) {
    Clear-Host
    Write-Host "  A0 sweep  --  $(Get-Date -Format 'HH:mm:ss')`n"
    foreach ($phase in @("p1", "p2", "p3")) {
        $files = @(Get-ChildItem "$results/${phase}_folded_*.csv" -ErrorAction SilentlyContinue)
        if (-not $files) { continue }
        # [System.IO.File]::ReadLines streams; Get-Content would load whole files each tick.
        $n = 0
        foreach ($f in $files) {
            $c = 0
            foreach ($line in [System.IO.File]::ReadLines($f.FullName)) { $c++ }
            $n += [Math]::Max(0, $c - 1)
        }
        $pct = if ($targets[$phase]) { 100 * $n / $targets[$phase] } else { 0 }
        $bar = "#" * [Math]::Min(30, [int]($pct * 0.3)) + "." * [Math]::Max(0, 30 - [int]($pct * 0.3))
        Write-Host ("  {0}  [{1}] {2,6:N1}%  {3,8:N0} designs  ({4} shards)" -f $phase, $bar, $pct, $n, $files.Count)
    }
    $live = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -EA SilentlyContinue |
              Where-Object { $_.CommandLine -match 'full_sweep' })
    Write-Host "`n  $($live.Count) folding processes live"
    $log = Get-ChildItem "$results/logs/p*_0.log" -EA SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($log) {
        $last = (Get-Content $log.FullName -Tail 1)
        Write-Host "  $($log.BaseName): $($last.Trim().Substring(0, [Math]::Min(100, $last.Trim().Length)))"
    }
    Write-Host "`n  refreshing every 30s -- Ctrl+C to stop watching (the run keeps going)"
    Start-Sleep -Seconds 30
}
