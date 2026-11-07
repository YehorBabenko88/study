[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][string]$Release)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
$checked=Invoke-LS5Helper $settings @('uninstall-check','--release',[IO.Path]::GetFullPath($Release))
if ($PSCmdlet.ShouldProcess($checked.release,'Remove ONLY verified configured code release; retain data, Python environments, Comfy and models')) {
    $run=Join-Path $settings.app_root 'run'
    New-Item -ItemType Directory -Force -Path $run | Out-Null
    $lockPath=Join-Path $run 'lifecycle.lock'
    $lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
    Write-LS5LockOwner $lock
    $again=Invoke-LS5Helper $settings @('uninstall-check','--release',$checked.release)
    if ($again.release -cne $checked.release) {throw 'Resolved release changed during confirmation.'}
    Remove-Item -LiteralPath $again.release -Recurse
    } finally {$lock.Dispose();Remove-Item -LiteralPath $lockPath}
}
