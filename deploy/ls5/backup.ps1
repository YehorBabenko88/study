[CmdletBinding(SupportsShouldProcess=$true)]
param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
if ($PSCmdlet.ShouldProcess($Destination,'Create consistent offline Study data backup; Study must already be stopped')) { Invoke-LS5Helper $settings @('backup','--destination',[IO.Path]::GetFullPath($Destination)) }
