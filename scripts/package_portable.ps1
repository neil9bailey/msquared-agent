param(
    [switch]$IncludeLocalEnv
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$blockedReleaseInputs = @("dist\data")
if (-not $IncludeLocalEnv) {
    $blockedReleaseInputs += "dist\.env"
}

foreach ($relativePath in $blockedReleaseInputs) {
    $candidate = Join-Path $projectRoot $relativePath
    if (Test-Path $candidate) {
        throw "Refusing to package while runtime credential/data path exists: $candidate. Move it, remove it, or use the explicit local-only override."
    }
}

if ($IncludeLocalEnv) {
    Write-Warning "Including dist\.env in the portable folder and zip. Use this only for a private local build."
    & "$PSScriptRoot\build_windows_exe.ps1" -AllowLocalEnv
} else {
    & "$PSScriptRoot\build_windows_exe.ps1"
}
if ($LASTEXITCODE -ne 0) {
    throw "Executable build failed."
}

$distRoot = Join-Path $projectRoot "dist"
$resolvedDist = (Resolve-Path $distRoot).Path
$packageDir = Join-Path $resolvedDist "MSquaredAgent-portable"
$packageFullPath = [System.IO.Path]::GetFullPath($packageDir)

if (-not $packageFullPath.StartsWith($resolvedDist, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to package outside dist folder: $packageFullPath"
}

if (Test-Path $packageFullPath) {
    Remove-Item -LiteralPath $packageFullPath -Recurse -Force
}

New-Item -ItemType Directory -Path $packageFullPath | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageFullPath "config") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageFullPath "docs") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageFullPath "data") | Out-Null

Copy-Item -LiteralPath (Join-Path $distRoot "MSquaredAgent.exe") -Destination $packageFullPath
Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $packageFullPath ".env.example")
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $packageFullPath
Copy-Item -LiteralPath (Join-Path $projectRoot "config\feature_flags.yaml") -Destination (Join-Path $packageFullPath "config")
Copy-Item -LiteralPath (Join-Path $projectRoot "config\persona.yaml") -Destination (Join-Path $packageFullPath "config")
Copy-Item -Path (Join-Path $projectRoot "docs\*.md") -Destination (Join-Path $packageFullPath "docs")

if ($IncludeLocalEnv) {
    $sourceEnv = Join-Path $distRoot ".env"
    if (-not (Test-Path -LiteralPath $sourceEnv)) {
        throw "IncludeLocalEnv was requested, but no dist\.env file exists."
    }
    Copy-Item -LiteralPath $sourceEnv -Destination (Join-Path $packageFullPath ".env") -Force
    Write-Warning "Copied local credentials into $packageFullPath\.env"
}

if (-not $IncludeLocalEnv) {
    $forbiddenPackagedFiles = @(
        (Join-Path $packageFullPath ".env")
    )
    foreach ($forbidden in $forbiddenPackagedFiles) {
        if (Test-Path $forbidden) {
            throw "Refusing to package credential file: $forbidden"
        }
    }
}

$packagedDataFiles = Get-ChildItem -LiteralPath (Join-Path $packageFullPath "data") -Force -File -Recurse
if ($packagedDataFiles) {
    throw "Refusing to package runtime data files under $packageFullPath\data"
}

$zipPath = Join-Path $resolvedDist "MSquaredAgent-portable.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $packageFullPath -DestinationPath $zipPath

Write-Host "Packaged $packageFullPath"
Write-Host "Created $zipPath"
