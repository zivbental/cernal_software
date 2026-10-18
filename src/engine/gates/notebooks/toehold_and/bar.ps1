# One progress bar for whatever is running, refreshing in place.
#   pwsh -File src/engine/gates/notebooks/toehold_and/bar.ps1
# Ctrl+C stops watching, never the run.
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $root
$results = "src/engine/gates/notebooks/toehold_and/results"
function Count($pattern) {
    $n = 0
    foreach ($f in Get-ChildItem "$results/$pattern" -EA SilentlyContinue) {
        # Shared read: these files are open for writing.
        $fs = [System.IO.File]::Open($f.FullName, 'Open', 'Read', 'ReadWrite')
        $sr = New-Object System.IO.StreamReader($fs)
        $c = 0; while ($null -ne $sr.ReadLine()) { $c++ }
        $sr.Close(); $fs.Close(); $n += [Math]::Max(0, $c - 1)
    }
    $n
}
$last = 0; $lastAt = Get-Date
while ($true) {
    $live = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -EA SilentlyContinue |
              Where-Object { $_.CommandLine -match 'full_sweep' })
    # Whichever set is being written now; targets are rows, not designs. Stage-1
    # targets are the MAXIMUM: 1036 pairs x 4 stems x 420 axis points. The grid is
    # 420 and not 360 because lower3 gained wobble_GU -- 6 x 5 x 7 x 2. A target
    # left at the old 360 makes a finished run read as 117% complete.
    $jobs = @(
        @{ n = "a1 stage1"; p = "a1_cheap_*.csv";  t = 1740480 },
        @{ n = "a1 fold";   p = "a1_folded_*.csv"; t = 198912  },  # 4144 pair-stems x 48 fold axes
        @{ n = "k1 stage1"; p = "k1_cheap_*.csv";  t = 1750560 },
        @{ n = "k1 fold";   p = "k1_folded_*.csv"; t = 200064  }
    )
    $active = $jobs | Where-Object { (Get-ChildItem "$results/$($_.p)" -EA SilentlyContinue) } |
              Select-Object -Last 1
    if (-not $active) { Write-Host "`r  nothing running                    " -NoNewline; Start-Sleep 10; continue }
    $n = Count $active.p
    $pct = [Math]::Min(100, 100 * $n / $active.t)
    $fill = [int]($pct * 0.4)
    $bar = ("#" * $fill) + ("." * (40 - $fill))
    $secs = ((Get-Date) - $lastAt).TotalSeconds
    $rate = if ($secs -gt 5 -and $n -gt $last) { ($n - $last) / $secs } else { 0 }
    if ($secs -gt 5) { $last = $n; $lastAt = Get-Date }
    $eta = if ($rate -gt 0) { [TimeSpan]::FromSeconds(($active.t - $n) / $rate).ToString("hh\:mm") } else { "--:--" }
    Write-Host ("`r  {0,-10} [{1}] {2,5:N1}%  {3,9:N0}/{4:N0}  eta {5}  {6} proc  " -f `
        $active.n, $bar, $pct, $n, $active.t, $eta, $live.Count) -NoNewline
    Start-Sleep 10
}
