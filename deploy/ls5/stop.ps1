[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][ValidateSet('study','comfy')][string]$Service)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
$path=Join-Path $settings.app_root "run/$Service.json"
if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Write-Output 'No managed ownership record; no process was stopped.';return }
$record=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
if ($record.service -ne $Service -or $record.config_file -ine $settings.config_file) { throw 'Ownership record does not match selected service/configuration.' }
$expected=if ($Service -eq 'study') {$settings.study.python} else {$settings.comfy.python}
if ($record.executable -ine $expected) { throw 'Recorded executable differs from current configuration; refusing stop.' }
$process=Get-OwnedLS5Process $record
if ($PSCmdlet.ShouldProcess("$Service PID $($record.pid)",'Stop verified owned process and remove its ownership record')) {
    if ($process) { Get-OwnedLS5Process $record | Out-Null;Stop-Process -Id $record.pid -ErrorAction Stop;$deadline=(Get-Date).AddSeconds(15);while ((Get-OwnedLS5Process $record) -and (Get-Date) -lt $deadline) {Start-Sleep -Milliseconds 100};if (Get-OwnedLS5Process $record) {throw 'Owned process did not exit; ownership record retained.'} }
    Remove-Item -LiteralPath $path
}
