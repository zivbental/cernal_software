# Rebuild everything downstream of the panel, in dependency order.
#
#   pwsh -File refresh_panel.ps1
#
# WHY THIS EXISTS. The panel is upstream of two things that silently go stale when it changes:
# the codon variants (built per panel row, so a new panel means the old variants describe designs
# that are no longer on the page) and the report JSON. Running them by hand in the right order is
# a step that gets forgotten, and a report showing last week's variants beside this week's gates
# is worse than one showing none.
#
# Order matters: panel -> variants -> JSON -> page. Each reads the previous one's output.

param(
    [int]$Pairs = 2,
    [int]$PerCell = 3,
    [switch]$SkipVariants
)

$ErrorActionPreference = "Stop"
# Moved here from the repo root, where it used to sit beside the thing it drives. Its paths
# are relative to the REPO ROOT, which is five directories up from this file -- the same
# anchor run_fill.ps1 and status.ps1 use.
$root = (Resolve-Path "$PSScriptRoot\..\..\..\..\..").Path
Set-Location $root
$nb = "src/engine/gates/notebooks/toehold_and"

Write-Host "1/3  panel" -ForegroundColor Cyan
& uv run python "$nb/objective_panel.py" --pairs $Pairs --per-cell $PerCell --out panel_three
if ($LASTEXITCODE -ne 0) { throw "panel failed" }

if (-not $SkipVariants) {
    Write-Host "`n2/3  codon variants (four mCherry transcripts -- the step that goes stale)" -ForegroundColor Cyan
    & uv run python "$nb/codon_variants.py" --panel panel_three --out variants
    if ($LASTEXITCODE -ne 0) { throw "variants failed" }
} else {
    Write-Host "`n2/3  variants SKIPPED -- variants.csv now describes a panel that may have changed" -ForegroundColor Yellow
}

Write-Host "`n3/3  report data and page" -ForegroundColor Cyan
# Both builders live in the repo now. They used to sit in a session scratchpad, which meant the
# report could only be rebuilt while that session was alive.
& uv run python "$nb/report/panel_data.py"
if ($LASTEXITCODE -ne 0) { throw "panel_data failed" }
& uv run python "$nb/report/panel_page.py"
if ($LASTEXITCODE -ne 0) { throw "panel_page failed" }

Write-Host "`ndone. Page: $nb/report/panel.html" -ForegroundColor Green
Write-Host "Ask Claude to publish it, or open it locally."
