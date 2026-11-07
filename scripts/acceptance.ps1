param(
    [string]$Python = "python",
    [string]$BrowserUrl = "",
    [string]$LogDirectory = (Join-Path $env:TEMP ("study-acceptance-" + [guid]::NewGuid().ToString()))
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$LogDirectory = (Resolve-Path -LiteralPath $LogDirectory).Path
# Read-only test runner: fixtures own TemporaryDirectory instances; no cleanup of user paths.
$previousE2E = $env:STUDY_E2E_URL
$env:STUDY_E2E_URL = ""
Push-Location (Join-Path $repo "prototype")
try {
    & $Python (Join-Path $PSScriptRoot "acceptance_runner.py") static 2>&1 | Tee-Object (Join-Path $LogDirectory "static.log")
    if ($LASTEXITCODE -ne 0) { throw "Static/unit acceptance failed; see static.log" }
    if ($BrowserUrl) {
        $env:STUDY_E2E_URL = $BrowserUrl
        & $Python (Join-Path $PSScriptRoot "acceptance_runner.py") browser 2>&1 | Tee-Object (Join-Path $LogDirectory "browser.log")
        if ($LASTEXITCODE -ne 0) { throw "Browser acceptance failed; see browser.log" }
    } else { Write-Output "BROWSER NOT RUN: supply -BrowserUrl for an isolated Study server." }
} finally { $env:STUDY_E2E_URL = $previousE2E; Pop-Location }
Write-Output "Acceptance logs: $LogDirectory"
