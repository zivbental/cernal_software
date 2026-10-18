# Progress of whatever sweep is running. Read-only.
#   pwsh -File src/engine/gates/notebooks/toehold_and/status.ps1
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $root
$results = "src/engine/gates/notebooks/toehold_and/results"
$live = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -EA SilentlyContinue |
          Where-Object { $_.CommandLine -match 'full_sweep' })
Write-Host ""
Write-Host "  $($live.Count) sweep processes live  ($(Get-Date -Format 'HH:mm:ss'))"
Write-Host ""
foreach ($f in Get-ChildItem "$results/*_cheap_*.csv","$results/*_folded_*.csv" -EA SilentlyContinue |
         Group-Object { $_.BaseName -replace '_\d+$','' }) {
    $n = 0
    foreach ($file in $f.Group) {
        # FileShare::ReadWrite, because these files are open for writing right now and
        # the default share mode refuses them. A status tool that cannot read a live file
        # is a status tool that only works when nothing is happening.
        $c = 0
        $fs = [System.IO.File]::Open($file.FullName, [System.IO.FileMode]::Open,
              [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $sr = New-Object System.IO.StreamReader($fs)
        while ($null -ne $sr.ReadLine()) { $c++ }
        $sr.Close(); $fs.Close()
        $n += [Math]::Max(0, $c - 1)
    }
    $newest = ($f.Group | Sort-Object LastWriteTime | Select-Object -Last 1).LastWriteTime
    $age = [int]((Get-Date) - $newest).TotalSeconds
    $state = if ($age -lt 90) { "writing" } else { "idle ${age}s" }
    Write-Host ("  {0,-18} {1,10:N0} rows  {2} shards  {3}" -f $f.Name, $n, $f.Group.Count, $state)
}
Write-Host ""
Write-Host "  stage-1 max is 1,740,480 rows = 1036 pairs x 4 stems x 420 axis points"
Write-Host "  (420 = 6 closures x 5 upper3 x 7 lower3 x 2 island; lower3 gained wobble_GU)"
