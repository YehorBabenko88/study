[CmdletBinding()]
param([Parameter(Mandatory)][string]$Config,[Parameter(Mandatory)][ValidateSet('study','comfy')][string]$Service,[ValidateRange(5,120)][int]$ReadyTimeoutSeconds=45)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
$settings=Get-LS5Config $Config
$plan=Invoke-LS5Helper $settings @('launch-plan','--service',$Service) -Python $settings.$Service.python
$run=Split-Path -Parent $plan.pid_file
New-Item -ItemType Directory -Force -Path $run | Out-Null
$lockPath=Join-Path $run 'lifecycle.lock'
$lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {
Write-LS5LockOwner $lock
if (Test-Path -LiteralPath $plan.pid_file) { throw 'A service ownership record already exists. Diagnose/stop that service before restarting.' }
$port=if ($Service -eq 'study') {8766} else {8188}
if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw 'Target port is already occupied. Existing listeners will not be stopped.' }
$run=Split-Path -Parent $plan.pid_file
$logs=Join-Path $settings.app_root 'logs'
New-Item -ItemType Directory -Force -Path $run,$logs | Out-Null
foreach ($directory in $plan.create_dirs) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
$process=Start-Process -FilePath $plan.executable -ArgumentList $plan.argument_line -WorkingDirectory $plan.working_directory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "$Service-$stamp.stdout.log") -RedirectStandardError (Join-Path $logs "$Service-$stamp.stderr.log") -PassThru
$observed=$null
for ($attempt=0;$attempt -lt 20 -and -not $observed;$attempt++) { $observed=Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)";if (-not $observed) {Start-Sleep -Milliseconds 100} }
if (-not $observed -or $observed.ExecutablePath -ine $plan.executable -or $observed.ParentProcessId -ne $PID -or -not $observed.CommandLine.EndsWith($plan.argument_line,[StringComparison]::Ordinal)) { throw 'Could not verify launched process executable, parent and planned arguments; inspect logs and diagnose before further action.' }
$record=@{service=$Service;pid=$process.Id;executable=$observed.ExecutablePath;command_line=$observed.CommandLine;created_utc=$observed.CreationDate.ToUniversalTime().ToString('o');config_file=$settings.config_file}
$record | ConvertTo-Json | Set-Content -LiteralPath $plan.pid_file -Encoding UTF8
$deadline=(Get-Date).AddSeconds($ReadyTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (-not (Get-OwnedLS5Process $record)) { throw 'Launched process exited before readiness. Ownership record retained; inspect diagnose/logs.' }
    $listeners=@(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    if ($listeners.Count -and @($listeners | Where-Object { $_.OwningProcess -ne $record.pid -or $_.LocalAddress -ne '127.0.0.1' }).Count) { throw 'Listener identity/binding does not match the recorded process. Readiness refused; inspect process ownership before stopping.' }
    if (-not $listeners.Count) {Start-Sleep -Milliseconds 500;continue}
    try { $response=Invoke-WebRequest -Uri $plan.health_url -UseBasicParsing -TimeoutSec 2;if ($response.StatusCode -eq 200) { Write-Output "$Service ready at $($plan.health_url); PID $($record.pid)";return } } catch {}
    Start-Sleep -Milliseconds 500
}
throw 'Readiness timed out. Process was not killed automatically; inspect diagnose/logs, then stop the selected owned service explicitly.'

} finally { $lock.Dispose();Remove-Item -LiteralPath $lockPath }
