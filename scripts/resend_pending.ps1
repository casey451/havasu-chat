# resend_pending.ps1 — one-shot: post ALL findings blocked by the stale sandbox token.
# Runs resend_driftwood.ps1 (2 findings, gather 6/04) then resend_eightlotus_tue.ps1
# (5 findings, continuation 6/04). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\resend_pending.ps1
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Write-Host "FAIL: run from the repo root (no .env found in current directory)."
    exit 1
}
if (-not (Get-Content .env | Where-Object { $_ -match '^INGEST_API_TOKEN=' })) {
    Write-Host "FAIL: no INGEST_API_TOKEN in .env"
    exit 1
}

Write-Host "=== Driftwood Acres (2 findings) ==="
& "$PSScriptRoot\resend_driftwood.ps1"

Write-Host ""
Write-Host "=== Eight Lotus Tuesday lineup (5 findings) ==="
& "$PSScriptRoot\resend_eightlotus_tue.ps1"

Write-Host ""
Write-Host "Done. Expected: 7x 'queued' (auto-publish is OFF)."
Write-Host "'duplicate' = already posted previously - safe to ignore."
Write-Host "HTTP 401 = token mismatch: check INGEST_API_TOKEN in .env vs Railway."
