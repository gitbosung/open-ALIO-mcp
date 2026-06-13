# Install repo pre-commit hook (copies into .git/hooks; does not change git config).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $PSScriptRoot "git-hooks\pre-commit"
$destDir = Join-Path $root ".git\hooks"
$dest = Join-Path $destDir "pre-commit"

if (-not (Test-Path $src)) {
    throw "Missing hook template: $src"
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -Force $src $dest
Write-Host "Installed pre-commit hook -> $dest"
Write-Host "Blocks: rawdata/, data/crawl/, .env*, *.pem, *.key"
