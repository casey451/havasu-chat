# set_railway_auth_secrets.ps1 — one-shot setup for the PR #142 secrets gate.
# Does everything: CLI install check -> login -> link -> generate + set secrets
# -> optional ADMIN_PASSWORD rotation. Interactive where it must be (browser
# auth, project picker, password entry); automatic everywhere else.
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File C:\Users\casey\projects\havasu-chat\scripts\set_railway_auth_secrets.ps1

$ErrorActionPreference = "Stop"
$repo = "C:\Users\casey\projects\havasu-chat"

Write-Host "== Railway secrets setup for PR #142 ==" -ForegroundColor Cyan

# --- 1. Railway CLI installed? ---
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "[1/5] Railway CLI not found - installing via npm..." -ForegroundColor Yellow
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm not found. Install Node.js first (https://nodejs.org), then re-run this script."
    }
    npm i -g @railway/cli
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        Write-Error "Install finished but 'railway' still not on PATH. Open a NEW PowerShell window and re-run."
    }
} else {
    Write-Host "[1/5] Railway CLI found." -ForegroundColor Green
}

# Probe native commands via cmd so stderr output can't trip ErrorActionPreference=Stop
function Test-NativeOk([string]$cmdLine) {
    cmd /c "$cmdLine >nul 2>&1"
    return ($LASTEXITCODE -eq 0)
}

# --- 2. Logged in? ---
if (-not (Test-NativeOk "railway whoami")) {
    Write-Host "[2/5] Not logged in - opening browser login (approve it there)..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    railway login
    $ErrorActionPreference = "Stop"
    if (-not (Test-NativeOk "railway whoami")) { Write-Error "railway login failed." }
} else {
    Write-Host "[2/5] Already logged in." -ForegroundColor Green
}

# --- 3. Linked to the project? ---
Set-Location $repo
if (-not (Test-NativeOk "railway status")) {
    Write-Host "[3/5] Not linked - pick your havasu-chat project / production environment / app service:" -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    railway link
    $ErrorActionPreference = "Stop"
    if (-not (Test-NativeOk "railway status")) { Write-Error "railway link failed." }
} else {
    Write-Host "[3/5] Already linked:" -ForegroundColor Green
    $ErrorActionPreference = "Continue"
    railway status
    $ErrorActionPreference = "Stop"
}

# --- 4. Optional ADMIN_PASSWORD rotation (collected BEFORE the single set call) ---
$extraArgs = @()
$rotate = Read-Host "[4/5] Rotate ADMIN_PASSWORD too? Recommended since the old one doubled as the session signing key. (y/N)"
if ($rotate -match '^[Yy]') {
    while ($true) {
        $pw1 = Read-Host -AsSecureString "  New ADMIN_PASSWORD (16+ chars, hidden)"
        $pw2 = Read-Host -AsSecureString "  Confirm"
        $plain1 = [System.Net.NetworkCredential]::new("", $pw1).Password
        $plain2 = [System.Net.NetworkCredential]::new("", $pw2).Password
        if ($plain1 -ne $plain2)       { Write-Host "  Passwords don't match, try again." -ForegroundColor Red; continue }
        if ($plain1.Length -lt 16)     { Write-Host "  Too short (16+ chars), try again." -ForegroundColor Red; continue }
        if ($plain1 -eq "changeme")    { Write-Host "  'changeme' is the forbidden default, try again." -ForegroundColor Red; continue }
        break
    }
    $extraArgs = @("--set", "ADMIN_PASSWORD=$plain1")
}

# --- 5. Generate session secret + apply everything in ONE call (= one redeploy) ---
$b = [byte[]]::new(48)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($b)
$rng.Dispose()
$s = [Convert]::ToBase64String($b)

Write-Host "[5/5] Setting variables (single call -> single redeploy)..." -ForegroundColor Yellow
$railArgs = @("variables",
    "--set", "HAVA_SESSION_SECRET=$s",
    "--set", "RAILWAY_ENVIRONMENT=production") + $extraArgs
$ErrorActionPreference = "Continue"
& railway @railArgs 2>&1 | Out-Host
$ok = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $ok) { Write-Error "railway variables failed - is the link pointing at the right service?" }

Set-Clipboard -Value $s
Remove-Variable s, b, plain1, plain2, pw1, pw2 -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host " - HAVA_SESSION_SECRET set; the value is IN YOUR CLIPBOARD - save it to your password manager NOW."
Write-Host " - RAILWAY_ENVIRONMENT=production set."
if ($extraArgs.Count -gt 0) { Write-Host " - ADMIN_PASSWORD rotated (as entered)." }
Write-Host " - Railway is redeploying; existing user sessions are now invalid (expected)."
Write-Host " - When the deploy is healthy, give Claude the go-ahead to merge #142."
