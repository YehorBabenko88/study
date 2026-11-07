[CmdletBinding()]
param([Parameter(Mandatory)][string]$Config,[ValidateSet('study','comfy','both')][string]$Service='both')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
foreach ($name in @('study','comfy')) {
    if ($Service -ne 'both' -and $Service -ne $name) {continue}
    $path=Join-Path $settings.app_root "run/$name.json"
    $owned=$false;$message='No ownership record'
    if (Test-Path -LiteralPath $path -PathType Leaf) {try {$record=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json;$owned=$null -ne (Get-OwnedLS5Process $record);$message=if ($owned) {'Verified process running'} else {'Recorded process exited'}} catch {$message=$_.Exception.Message}}
    $port=if ($name -eq 'study') {8766} else {8188}
    [pscustomobject]@{service=$name;owned_process=$owned;port=$port;listeners=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess);status=$message;lifecycle_lock_present=(Test-Path -LiteralPath (Join-Path $settings.app_root 'run/lifecycle.lock'));logs=(Join-Path $settings.app_root 'logs')}
}
