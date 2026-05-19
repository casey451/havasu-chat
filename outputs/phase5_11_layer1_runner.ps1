<#
.SYNOPSIS
  Phase 5.11 -- 1 Layer 1 pipeline runner.

.DESCRIPTION
  Drives the 4-or-5-step Google Places Layer 1 pipeline for Phase 5.11
  (pets) with operator-confirms-each-step pauses. Logs all output to
  outputs/phase5_11_layer1_runner.log via Start-Transcript.

  v2 (2026-05-17 fix): subprocess output now uses Out-Default + explicit
  argument-array call so it streams to the host AND gets captured by
  Start-Transcript. v1 used Invoke-Expression piped to Out-Null and
  swallowed all python stdout.

  Halts cleanly on any non-zero exit code or any operator decline. The
  1.3 load dry-run is a hard decision point: the script HALTS there and
  asks for the unmapped count -- if > 0, exits with instructions to run
  sustainability commit first; if 0, proceeds to live load with
  confirmation.

  Steps:
    1.1  python -m scripts.places_discovery --category pets --dry-run
         (free; print planned API calls)
    1.2  python -m scripts.places_discovery --category pets
         (~$0.05; live discovery)
    1.2b python -m scripts.places_enrichment --limit 200
         (~$0.05; cache-aware enrichment of new candidates)
    1.3  python -m scripts.places_load --category pets --dry-run
         (free; reports unmapped count -- sustainability decision point)
    1.4  python -m scripts.places_load --category pets
         (DB write; runs only after sustainability resolves to unmapped=0)

.PARAMETER StartAt
  Step to begin at (1.1, 1.2, 1.2b, 1.3, or 1.4). Default 1.1.
  Useful for resuming after a previous run halted partway.

.PARAMETER SkipConfirm
  Skip the [y/n/q] prompts between steps. NOT RECOMMENDED for the live
  steps; bypasses the cadence discipline. The 1.3 sustainability
  decision-point HALT cannot be bypassed.

.PARAMETER LogPath
  Override transcript log path. Default outputs/phase5_11_layer1_runner.log.

.EXAMPLE
  PS> .\outputs\phase5_11_layer1_runner.ps1

.EXAMPLE
  PS> .\outputs\phase5_11_layer1_runner.ps1 -StartAt 1.3
#>

[CmdletBinding()]
param(
    [ValidateSet('1.1', '1.2', '1.2b', '1.3', '1.4')]
    [string]$StartAt = '1.1',
    [switch]$SkipConfirm,
    [string]$LogPath = 'outputs/phase5_11_layer1_runner.log'
)

$ErrorActionPreference = 'Continue'

# --- Pre-flight ---------------------------------------------------------
if (-not (Test-Path 'scripts/places_discovery.py')) {
    Write-Host "ERROR: must run from repo root (havasu-chat). Current PWD: $PWD" -ForegroundColor Red
    exit 2
}
if (-not (Test-Path '.env')) {
    Write-Host "ERROR: .env not found. Google Places API key required." -ForegroundColor Red
    exit 2
}

# Start logging --------------------------------------------------------
Start-Transcript -Path $LogPath -Append | Out-Null
Write-Host ""
Write-Host ("#" * 78)
Write-Host "# Phase 5.11 -- 1 Layer 1 Pipeline Runner (v2)"
Write-Host "# Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "# Start step: $StartAt"
Write-Host "# Skip confirmations: $SkipConfirm"
Write-Host "# Log: $LogPath"
Write-Host ("#" * 78)
Write-Host ""

# --- Helper: confirmation prompt --------------------------------------
function Confirm-Step {
    param(
        [string]$StepName,
        [string]$Cost,
        [string[]]$Cmd
    )
    Write-Host ""
    Write-Host ("=" * 78)
    Write-Host "STEP $StepName  $Cost"
    Write-Host ("=" * 78)
    Write-Host ("Command: " + ($Cmd -join ' '))
    Write-Host ""

    if ($SkipConfirm) {
        Write-Host "[SkipConfirm] auto-proceeding"
        return $true
    }

    while ($true) {
        $reply = Read-Host "Run? [y]es / [n]o-skip / [q]uit"
        switch ($reply.ToLower()) {
            'y'    { return $true }
            'yes'  { return $true }
            ''     { return $true }
            'n'    { Write-Host "Skipping step $StepName."; return $false }
            'no'   { Write-Host "Skipping step $StepName."; return $false }
            'q'    { Write-Host "Aborted by operator."; Stop-Transcript | Out-Null; exit 0 }
            'quit' { Write-Host "Aborted by operator."; Stop-Transcript | Out-Null; exit 0 }
            default { Write-Host "Reply y, n, or q." }
        }
    }
}

function Invoke-PythonStep {
    param(
        [string]$StepName,
        [string]$Cost,
        [string[]]$Cmd
    )
    $proceed = Confirm-Step -StepName $StepName -Cost $Cost -Cmd $Cmd
    if (-not $proceed) {
        return
    }
    Write-Host ""
    Write-Host "--- BEGIN OUTPUT of $StepName at $(Get-Date -Format 'HH:mm:ss') ---"

    # Run python with redirected stderr -> stdout, then pipe to Out-Default
    # so the output streams to the host AND is captured by Start-Transcript.
    # Using the call operator '&' with an argument array avoids both
    # Invoke-Expression pipeline-swallow and quoting issues.
    & $Cmd[0] $Cmd[1..($Cmd.Length-1)] 2>&1 | Out-Default
    $exit = $LASTEXITCODE

    Write-Host "--- END OUTPUT of $StepName (exit=$exit) at $(Get-Date -Format 'HH:mm:ss') ---"
    Write-Host ""
    if ($exit -ne 0) {
        Write-Host ""
        Write-Host ("!" * 78) -ForegroundColor Red
        Write-Host "STEP $StepName FAILED with exit code $exit. Halting." -ForegroundColor Red
        Write-Host "Resume from $StepName via:" -ForegroundColor Yellow
        Write-Host "  .\outputs\phase5_11_layer1_runner.ps1 -StartAt $StepName" -ForegroundColor Yellow
        Write-Host ("!" * 78) -ForegroundColor Red
        Stop-Transcript | Out-Null
        exit $exit
    }
}

# --- Step ordering -----------------------------------------------------
$stepOrder = @('1.1', '1.2', '1.2b', '1.3', '1.4')
$startIndex = $stepOrder.IndexOf($StartAt)
if ($startIndex -lt 0) {
    Write-Host "ERROR: invalid StartAt value '$StartAt'." -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 2
}

# --- Step 1.1: dry-run discovery (free) -------------------------------
if ($startIndex -le $stepOrder.IndexOf('1.1')) {
    Invoke-PythonStep -StepName '1.1' `
        -Cost '(free; dry-run, no API spend)' `
        -Cmd @('python', '-m', 'scripts.places_discovery', '--category', 'pets', '--dry-run')
}

# --- Step 1.2: live discovery (~$0.05) --------------------------------
if ($startIndex -le $stepOrder.IndexOf('1.2')) {
    Write-Host ""
    Write-Host "REVIEW the 1.1 dry-run output above. Expected: 4 labels x 10-15 hits each."
    Write-Host "If anything looks off (wrong labels, unexpected counts), abort with q."
    Invoke-PythonStep -StepName '1.2' `
        -Cost '(LIVE; ~$0.05 in API spend)' `
        -Cmd @('python', '-m', 'scripts.places_discovery', '--category', 'pets')
}

# --- Step 1.2b: enrichment (~$0.05) -----------------------------------
if ($startIndex -le $stepOrder.IndexOf('1.2b')) {
    Write-Host ""
    Write-Host "REVIEW the 1.2 discovery output. Note raw hit count."
    Invoke-PythonStep -StepName '1.2b' `
        -Cost '(LIVE; ~$0.05 in API spend, cache-aware)' `
        -Cmd @('python', '-m', 'scripts.places_enrichment', '--limit', '200')
}

# --- Step 1.3: load dry-run (SUSTAINABILITY DECISION POINT) -----------
if ($startIndex -le $stepOrder.IndexOf('1.3')) {
    Write-Host ""
    Write-Host "REVIEW the 1.2b enrichment output. Note new-enrichments count."
    Invoke-PythonStep -StepName '1.3' `
        -Cost '(free; dry-run load; SUSTAINABILITY DECISION POINT)' `
        -Cmd @('python', '-m', 'scripts.places_load', '--category', 'pets', '--dry-run')

    Write-Host ""
    Write-Host ("*" * 78) -ForegroundColor Yellow
    Write-Host "1.3 SUSTAINABILITY DECISION POINT" -ForegroundColor Yellow
    Write-Host ("*" * 78) -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Look at the 1.3 dry-run output above. Find this line:"
    Write-Host "  'category_id unmapped (operator queue): <N>'"
    Write-Host ""
    Write-Host "If N == 0  -> no sustainability commit needed; proceed to 1.4"
    Write-Host "If N >  0  -> halt here. Surface unmapped primary_types to the agent;"
    Write-Host "             agent authors sustainability commit; you push it via"
    Write-Host "             bundle workflow; then re-run -StartAt 1.3 to re-verify"
    Write-Host "             unmapped == 0; then proceed."
    Write-Host ""

    if ($SkipConfirm) {
        Write-Host "[SkipConfirm] cannot bypass sustainability decision-point. Halting."
        Stop-Transcript | Out-Null
        exit 0
    }

    while ($true) {
        $unmapped = Read-Host "How many unmapped rows did 1.3 report? (number, or 'q' to halt)"
        if ($unmapped -eq 'q' -or $unmapped -eq 'quit') {
            Write-Host "Halted at sustainability decision point. Resume with -StartAt 1.3."
            Stop-Transcript | Out-Null
            exit 0
        }
        if ($unmapped -match '^\d+$') {
            $unmappedInt = [int]$unmapped
            break
        }
        Write-Host "Reply with a number or 'q'."
    }

    if ($unmappedInt -gt 0) {
        Write-Host ""
        Write-Host "Unmapped count is $unmappedInt > 0. Sustainability commit needed BEFORE 1.4." -ForegroundColor Yellow
        Write-Host "Halting cleanly. Steps to resume:"
        Write-Host "  1. Paste the 1.3 dry-run output to agent so it can see which primary_types are unmapped"
        Write-Host "  2. Agent authors + commits sustainability layer in /sessions clone"
        Write-Host "  3. Agent writes bundle to outputs/phase5_11_sustainability.bundle"
        Write-Host "  4. You: git fetch outputs/phase5_11_sustainability.bundle main:bundle_sustain"
        Write-Host "         git merge --ff-only bundle_sustain"
        Write-Host "         git push origin main"
        Write-Host "  5. Re-run this script: .\outputs\phase5_11_layer1_runner.ps1 -StartAt 1.3"
        Stop-Transcript | Out-Null
        exit 0
    }

    Write-Host ""
    Write-Host "Unmapped == 0. No sustainability commit needed. Proceeding to 1.4." -ForegroundColor Green
}

# --- Step 1.4: live load (DB writes) ----------------------------------
if ($startIndex -le $stepOrder.IndexOf('1.4')) {
    Write-Host ""
    Write-Host "REVIEW: confirmed unmapped == 0 in 1.3. Proceeding to live load."
    Write-Host "PRE-FLIGHT: stop FastAPI dev server if running (events.db lock)."
    Invoke-PythonStep -StepName '1.4' `
        -Cost '(LIVE; DB writes to data/events.db)' `
        -Cmd @('python', '-m', 'scripts.places_load', '--category', 'pets')
}

# --- Completion --------------------------------------------------------
Write-Host ""
Write-Host ("#" * 78)
Write-Host "# Phase 5.11 -- 1 Layer 1 Pipeline complete"
Write-Host "# Finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "# Log: $LogPath"
Write-Host ("#" * 78)
Write-Host ""
Write-Host "Next: re-run outputs/phase5_11_db_spot_check.py to capture post-load"
Write-Host "      cat-11 entry count; surface to agent for 2 audit dispatch."
Write-Host ""

Stop-Transcript | Out-Null
exit 0
