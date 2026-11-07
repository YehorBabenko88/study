function Get-LS5Config {
    param([Parameter(Mandatory)][string]$Config)
    if ((([Net.Dns]::GetHostName()).ToUpperInvariant()) -ne 'LS5') { throw 'LS5 only. PC1 is development only; no local service operation is permitted.' }
    $path = (Resolve-Path -LiteralPath $Config -ErrorAction Stop).Path
    $value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if (($value.target_host.ToUpperInvariant()) -ne 'LS5') { throw 'Configuration target must be LS5.' }
    if ($value.version -ne 1) { throw 'Unsupported configuration version.' }
    $base = Split-Path -Parent $path
    foreach ($item in @(@{obj=$value;key='app_root'},@{obj=$value.study;key='python'},@{obj=$value.study;key='release_dir'},@{obj=$value.study;key='data_dir'},@{obj=$value.comfy;key='python'},@{obj=$value.comfy;key='directory'})) {
        $raw = [string]$item.obj.($item.key)
        if ([string]::IsNullOrWhiteSpace($raw)) { throw "Missing configuration path $($item.key)." }
        if (-not [IO.Path]::IsPathRooted($raw)) { $raw = Join-Path $base $raw }
        $item.obj.($item.key) = [IO.Path]::GetFullPath($raw)
    }
    $value | Add-Member -NotePropertyName config_file -NotePropertyValue $path
    return $value
}
function Invoke-LS5Helper {
    param($Settings,[string[]]$Arguments,[string]$Python)
    if (-not $Python) {$Python=$Settings.study.python}
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Configured existing Study Python is missing. No environment will be installed.' }
    $result = & $Python (Join-Path $PSScriptRoot 'portable_ops.py') @Arguments --config $Settings.config_file
    if ($LASTEXITCODE -ne 0) { throw 'Lifecycle validation failed; no further operation was performed.' }
    return ($result | ConvertFrom-Json)
}
function Get-OwnedLS5Process {
    param($Record)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" -ErrorAction Stop
    if (-not $process) { return $null }
    $created = $process.CreationDate.ToUniversalTime().ToString('o')
    if ($process.ExecutablePath -ine $Record.executable -or $process.CommandLine -cne $Record.command_line -or $created -cne $Record.created_utc) { throw 'PID identity does not match recorded executable, command line and creation time. Refusing to stop an unrelated process.' }
    return $process
}
function Write-LS5LockOwner {
    param([Parameter(Mandatory)][IO.FileStream]$Lock)
    $owner=[Text.Encoding]::ASCII.GetBytes([string]$PID)
    $Lock.Write($owner,0,$owner.Length)
    $Lock.Flush($true)
}
