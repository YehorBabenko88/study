param(
    [Parameter(Mandatory=$true)][string]$Python,
    [string]$SourceRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$SourceCommit = '',
    [string]$EvidenceRoot = (Join-Path $env:TEMP ('StudyQA-' + [guid]::NewGuid()))
)
$ErrorActionPreference = 'Stop'
# Dependencies must already exist. No installs, models, deletion, or global settings.
$Python = (Resolve-Path -LiteralPath $Python).Path
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
if (Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'prototype') -Recurse -File | Where-Object { $_.Name -match '\.(sqlite.*|db)$' }) {
    throw 'Source contains a database; use a clean checkout.'
}
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'EvidenceRoot must not exist; use a fresh directory.' }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$started = [DateTimeOffset]::UtcNow
$snapshot = Join-Path $EvidenceRoot 'snapshot'
New-Item -ItemType Directory -Path $snapshot | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceRoot 'prototype') -Destination $snapshot -Recurse
Copy-Item -LiteralPath $PSScriptRoot -Destination (Join-Path $snapshot 'qa') -Recurse
Get-ChildItem -LiteralPath $snapshot -Recurse -File | Where-Object { $_.Extension -in '.py','.js','.html','.ps1' } | ForEach-Object {
    @{ path=$_.FullName.Substring($snapshot.Length+1); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
} | ConvertTo-Json | Set-Content (Join-Path $EvidenceRoot 'source-manifest.json')
# Refuse a source containing application data instead of copying and modifying it.
if (Get-ChildItem -LiteralPath (Join-Path $snapshot 'prototype') -Filter '*.sqlite*') { throw 'Source contains a database; use a clean checkout.' }
Push-Location $snapshot
$oldComfy = $env:STUDY_COMFYUI_ENABLED
$oldE2E = $env:STUDY_E2E_URL
try {
    & $Python --version *> (Join-Path $EvidenceRoot 'python.log')
    & $Python -m pip freeze *> (Join-Path $EvidenceRoot 'packages.log')
    if ($SourceCommit) { $SourceCommit | Set-Content (Join-Path $EvidenceRoot 'commit.log') }
    else { & git -C $SourceRoot rev-parse HEAD *> (Join-Path $EvidenceRoot 'commit.log') }
    $env:STUDY_COMFYUI_ENABLED = '0'
    $env:STUDY_E2E_URL = ''
    & $Python -m unittest discover -s prototype -v *> (Join-Path $EvidenceRoot 'unittest.log')
    $unit = $LASTEXITCODE
    & $Python qa/windows_audit.py --browser *> (Join-Path $EvidenceRoot 'acceptance.log')
    $acceptance = $LASTEXITCODE
    @{ unittest_exit=$unit; acceptance_exit=$acceptance; evidence=$EvidenceRoot } | ConvertTo-Json | Set-Content (Join-Path $EvidenceRoot 'result.json')
    Get-Content (Join-Path $EvidenceRoot 'result.json')
    @{ started_utc=$started.ToString('o'); finished_utc=([DateTimeOffset]::UtcNow).ToString('o'); commands=@('python -m unittest discover -s prototype -v','python qa/windows_audit.py --browser') } | ConvertTo-Json | Set-Content (Join-Path $EvidenceRoot 'run.json')
    if ($unit -ne 0 -or $acceptance -ne 0) { throw 'Acceptance failed or has mandatory skips. Read retained evidence.' }
} finally {
    $env:STUDY_COMFYUI_ENABLED = $oldComfy
    $env:STUDY_E2E_URL = $oldE2E
    Pop-Location
}
