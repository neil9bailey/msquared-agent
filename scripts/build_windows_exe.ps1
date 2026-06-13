param(
    [switch]$AllowLocalEnv
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$blockedRuntimePaths = @("dist\data")
if (-not $AllowLocalEnv) {
    $blockedRuntimePaths += "dist\.env"
}

foreach ($relativePath in $blockedRuntimePaths) {
    $candidate = Join-Path $projectRoot $relativePath
    if (Test-Path $candidate) {
        throw "Refusing to build while runtime credential/data path exists: $candidate. Move it, remove it, or use the explicit local-only override."
    }
}

python -m pip install -e . --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    throw "Package dependency install failed."
}

python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller install failed."
    }
}

$runningApp = Get-Process MSquaredAgent -ErrorAction SilentlyContinue
if ($runningApp) {
    throw "MSquaredAgent.exe is running. Close it before building."
}

$exePath = Join-Path $projectRoot "dist\MSquaredAgent.exe"
if (Test-Path $exePath) {
    Remove-Item -LiteralPath $exePath -Force
}

python -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --windowed `
    --name MSquaredAgent `
    --paths src `
    --add-data "config;config" `
    --add-data "prompts;prompts" `
    src\msquared_agent\desktop_ui.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Write-Host "Built $exePath"
