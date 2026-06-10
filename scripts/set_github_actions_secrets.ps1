# set_github_actions_secrets.ps1
# Sets the two GitHub Actions secrets the category-patrol workflow needs.
# Run from PowerShell:  .\scripts\set_github_actions_secrets.ps1
# You'll be prompted to paste each value (input is hidden, nothing is written
# to disk or shell history). Requires the GitHub CLI (gh), logged in.

$repo = "casey451/havasu-chat"

# --- preflight: gh installed and authenticated ------------------------------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GitHub CLI (gh) not found. Install it first:" -ForegroundColor Red
    Write-Host "    winget install GitHub.cli"
    Write-Host "then re-open PowerShell and re-run this script."
    exit 1
}

gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "gh is not logged in. Run:  gh auth login   (choose GitHub.com, HTTPS, browser)" -ForegroundColor Red
    exit 1
}

# --- prompt + set each secret ------------------------------------------------
function Set-RepoSecret([string]$name, [string]$hint) {
    Write-Host ""
    Write-Host "Paste value for $name" -ForegroundColor Cyan
    Write-Host "  ($hint)" -ForegroundColor DarkGray
    $secure = Read-Host -AsSecureString "  value (hidden)"
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if ([string]::IsNullOrWhiteSpace($plain)) {
        Write-Host "  empty value, skipping $name" -ForegroundColor Yellow
        return
    }
    $plain | gh secret set $name --repo $repo
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK - $name set on $repo" -ForegroundColor Green
    } else {
        Write-Host "  FAILED to set $name" -ForegroundColor Red
    }
}

Set-RepoSecret "OPENAI_API_KEY" "starts with sk- ; it's also on the first line of this repo's .env"
Set-RepoSecret "DATABASE_URL"   "prod Postgres URL from Railway > Postgres service > Variables. Use the PUBLIC/proxy URL (containing 'proxy.rlwy.net' or similar), NOT the .railway.internal one"

# --- verify -------------------------------------------------------------------
Write-Host ""
Write-Host "Secrets now on ${repo}:" -ForegroundColor Cyan
gh secret list --repo $repo
