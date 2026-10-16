# Tonight's run. k1 first and at full coverage, a1 reduced to a check.
#   pwsh -File src/engine/gates/notebooks/toehold_and/run_variants.ps1
#
# WHY THIS SHAPE
#
#   k1  Kim's secondary hairpin: 20-nt arm, 17-nt invasion, AUA cap. Untested, and the
#       geometry changes the LOCK rather than trading it away. Full pair-stem coverage,
#       ~20 h, and it runs first so an overrun costs the cheaper job and not this one.
#       NOT Kim's 1x1 bulge at position 12 -- scheme C already generates 0 to 11 unpaired
#       positions across the arm, so a hand-placed bulge would pin one instance of
#       something the enumeration already explores.
#
#   a1  A-anchored stems, reduced from every pair-stem to 100, one per trigger pair.
#       Measured on 5 trigger pairs and 960 designs, this corner does not gate AT ALL:
#       best mean_separation 0.000000, best A_M_gain 0.0, best separation 0.0, and A_M(10)
#       equal to A_M(11) to three decimals. Selecting on a_site buys trigger-A grip (-42.4
#       against -15.2) by spending the lock (-6.2 against -22.3), and a lock that weak does
#       not hold state 10 shut. The 100 exist to test whether those five pairs were
#       unlucky, not to find a winner. ~0.3 h.
#
# Both fold the 48-axis grid: closure 6 x upper3 2 x lower3 4 (three 2S1W arrangements plus
# wobble_GU) x island 1. Compare PER TRIGGER PAIR, never per row -- k1 builds a 165-nt switch
# from a different pair set, so rows do not align.
#
# Everything resumes. Safe to re-run.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))))
Set-Location $root
$fasta = "src/engine/gates/notebooks/toehold_and/mCherry original.txt"
$sweep = "src/engine/gates/notebooks/toehold_and/full_sweep.py"
$logs  = "src/engine/gates/notebooks/toehold_and/results/logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$shards = 6
$grid = @("--upper3","WWW_AUA,WWW_UAU",
          "--lower3","SSW,SWS,WSS,wobble_GU",
          "--island","trigger_derived")

function Say($t) { Write-Host "`n=== $(Get-Date -Format 'HH:mm:ss')  $t ===`n" }

# Two writers on one shard file interleave rows and the damage is silent.
$live = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" -EA SilentlyContinue |
          Where-Object { $_.CommandLine -match 'full_sweep' })
if ($live.Count -gt 0) {
    Write-Host "`nREFUSING TO START: $($live.Count) full_sweep process(es) already running."
    Write-Host "Stop them, then re-run. Every phase resumes, so you lose at most a minute."
    exit 1
}

function Run-Sharded($name, $stage, $extra) {
    Say "$name : $stage across $shards shards"
    $jobs = @()
    for ($i = 0; $i -lt $shards; $i++) {
        # The FASTA name has a space; Start-Process joins -ArgumentList without quoting.
        $argv = @("run","python","`"$sweep`"","--fasta","`"$fasta`"","--stage",$stage,
                  "--out",$name,"--shard","$i/$shards","--resume") + $extra
        $jobs += Start-Process uv -ArgumentList $argv -PassThru -NoNewWindow `
            -RedirectStandardOutput "$logs/${name}_${stage}_$i.log" `
            -RedirectStandardError  "$logs/${name}_${stage}_$i.err"
    }
    Write-Host "  pids: $($jobs.Id -join ', ')"
    $jobs | Wait-Process
    for ($i = 0; $i -lt $shards; $i++) {
        $err = "$logs/${name}_${stage}_$i.err"
        if ((Test-Path $err) -and (Get-Item $err).Length -gt 0) {
            Write-Host "  ** shard $i wrote to stderr: **"
            Get-Content $err -TotalCount 4 | ForEach-Object { Write-Host "     $_" }
        }
    }
    Say "$name : $stage done"
}

function Analyse($name) {
    uv run python src/engine/gates/notebooks/toehold_and/fold_analysis.py --out $name `
        *> "$logs/${name}_analysis.log"
    Get-Content "$logs/${name}_analysis.log" -Tail 50
}

# --- k1 first: the priority, full coverage. Its own stage 1, since the geometry changes
# --- which trigger pairs exist at all.
Run-Sharded "k1" "cheap" @("--pairs","0","--stems","4","--kim-arm")
Run-Sharded "k1" "fold"  (@("--block","C","--kim-arm") + $grid)
Analyse "k1"

# --- a1: 100 pair-stems, carved already into a1top_cheap.csv. No stage 1 needed.
Run-Sharded "a1top" "fold" (@("--block","C","--stems-by","a_site_energy") + $grid)
Analyse "a1top"

Say "DONE"
Write-Host "  k1_folded_*.csv     Kim 20/17/AUA, full coverage, 165-nt switch"
Write-Host "  a1top_folded_*.csv  A-anchored, 100 pair-stems, one per trigger pair"
Write-Host ""
Write-Host "  Then, for a panel that includes both:"
Write-Host "    uv run python src/engine/gates/notebooks/toehold_and/candidates.py \\"
Write-Host "      --from p1,p2,p3,k1,a1top --pairs 3 --opens-pct 90 \\"
Write-Host "      --fasta `"$fasta`" --out panel_after_variants"
