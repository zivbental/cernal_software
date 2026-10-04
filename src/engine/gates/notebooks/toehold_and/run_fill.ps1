# One command that fills every gap the report currently shows, then rebuilds and republishes it.
#
#     powershell -ExecutionPolicy Bypass -File src\engine\gates\notebooks\toehold_and\run_fill.ps1
#
# What it fills, and what it cannot:
#
#   ied_off        the two OFF tubes `ied_gain` never had, so the gain can be taken against the
#                  WORST OFF state instead of against the switch alone. Six shards, ~4 min wall
#                  clock on six cores (20 min on one, measured).
#   accessibility  `l_local` for every window the report shows. The table was built when the
#                  population was smaller, so rows added since -- 507/65/5 among them -- have no
#                  accessibility at all. This is the script that fills them, from main's own
#                  FoldProfiler through `git show`, which is why the provenance columns in the
#                  output say `origin/main`.
#
#   d_off          NOT filled here, and it cannot be. It is written by the SWEEP
#                  (`full_sweep.py`), not by any completion pass, so the 49.3% coverage is a gap
#                  in the sweep's own output and closing it means re-folding those designs. It is
#                  reported rather than filtered for that reason.
#
# Each step is resumable on its own, so a kill and a rerun costs only the shard that was running.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..\..\..\..").Path
Set-Location $root

Write-Host "`n=== 1/4  the two missing IED OFF tubes, six shards in parallel" -ForegroundColor Cyan
$jobs = 0..5 | ForEach-Object {
    Start-Process -FilePath "uv" -PassThru -NoNewWindow -ArgumentList @(
        "run", "python",
        "src/engine/gates/notebooks/toehold_and/complete_panel.py",
        # `--shard` takes "i/n" as ONE argument. Written as two (`--shards 6 --shard 0`) argparse
        # rejects it with "unrecognized arguments" and the run produces nothing at all.
        "--metrics", "ied_off", "--shard", "$_/6",
        "--out", "completions_ied"
    )
}
$jobs | ForEach-Object { $_.PriorityClass = "High" }
$jobs | Wait-Process
Write-Host "  six shards done" -ForegroundColor Green

Write-Host "`n=== 2/4  accessibility for every window the report shows" -ForegroundColor Cyan
# `--from-ref origin/main` loads main's FoldProfiler through `git show` -- nothing is checked out
# and no file in the repo changes, which is why the output's provenance columns say origin/main.
uv run python tools/accessibility_local.py --from-ref origin/main --out accessibility_local
if ($LASTEXITCODE -ne 0) { throw "accessibility_local failed" }

Write-Host "`n=== 3/4  rebuild every panel, then its variants" -ForegroundColor Cyan
# The panels, each with the recipe that defines it. `panel_best` first: it is the page's default.
$panels = @(
    @{ name = "panel_best";    args = @("--arm3", "opening SEP", "--bench-floor", "-2.0", "--pin", "53/605/5,414/361/4") },
    @{ name = "panel_assign2"; args = @("--arm3", "opening SEP", "--pair-arms", "IED gain,A_M ratio|opening SEP", "--bench-floor", "-2.0", "--distinct-arms") },
    @{ name = "panel_bench";   args = @("--arm3", "opening SEP", "--bench-floor", "-2.0", "--distinct-arms") },
    @{ name = "panel_assign";  args = @("--arm3", "opening SEP", "--pair-arms", "IED gain,A_M ratio|opening SEP") },
    @{ name = "panel_three";   args = @() },
    @{ name = "panel_sep3";    args = @("--arm3", "opening SEP") },
    @{ name = "panel_nine";    args = @("--arm4", "opening SEP") }
)
foreach ($p in $panels) {
    Write-Host "  $($p.name)"
    & uv run python src/engine/gates/notebooks/toehold_and/objective_panel.py --six @($p.args) --out $p.name
    if ($LASTEXITCODE -ne 0) { throw "$($p.name) failed" }
    # The variants AFTER the panel, because the recoder reads the panel's own windows and, when
    # the role swap is in play, the plan the panel recorded. `panel_nine` is skipped: its fourth
    # arm's rows are a view for reading and carry no transcripts.
    if ($p.name -ne "panel_nine") {
        & uv run python src/engine/gates/notebooks/toehold_and/codon_variants.py --panel $p.name --out "variants_$($p.name)"
        if ($LASTEXITCODE -ne 0) { throw "variants for $($p.name) failed" }
    }
}

Write-Host "`n=== 4/4  the report" -ForegroundColor Cyan
$names = ($panels | ForEach-Object { $_.name })
& uv run python src/engine/gates/notebooks/toehold_and/report/panel_data.py @names
if ($LASTEXITCODE -ne 0) { throw "panel_data failed" }
uv run python src/engine/gates/notebooks/toehold_and/report/panel_page.py
if ($LASTEXITCODE -ne 0) { throw "panel_page failed" }
uv run python src/engine/gates/notebooks/toehold_and/report/check_order_sheet.py

Write-Host "`nreport/panel.html rebuilt. Publish it to the artifact to share it." -ForegroundColor Green
