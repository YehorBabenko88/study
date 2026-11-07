[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][string]$Backup,[Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
if ($PSCmdlet.ShouldProcess($Destination,'Restore verified backup into a NEW EMPTY destination only; configuration is not switched automatically')) { Invoke-LS5Helper $settings @('restore','--source',[IO.Path]::GetFullPath($Backup),'--destination',[IO.Path]::GetFullPath($Destination)) }
