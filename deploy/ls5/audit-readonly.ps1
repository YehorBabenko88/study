<# Read-only LS5 inventory. JSON stdout only. No installs, service starts or model imports. #>
[CmdletBinding()]
param([string[]]$SearchRoots = @('C:\ComfyUI','C:\AI\ComfyUI','C:\Study','C:\AI\Study'))

$ErrorActionPreference = 'Stop'
$actualHost = [Environment]::MachineName
# Guard before every hardware, registry, executable, service or port query.
if ($actualHost -ine 'LS5') {
    [pscustomobject]@{schema_version=1;status='BLOCKED';reason='target_hostname_mismatch';expected_hostname='LS5';observed_hostname=$actualHost;hardware_collected=$false} | ConvertTo-Json -Depth 4 -Compress
    return
}
$notes = [System.Collections.Generic.List[string]]::new()
function Read-Cim([string]$Class) {
    try { @(Get-CimInstance -ClassName $Class -ErrorAction Stop) }
    catch { $notes.Add("CIM unavailable: $Class"); @() }
}
function Invoke-MetadataProcess([string]$Executable,[string]$Arguments) {
    $process = [System.Diagnostics.Process]::new()
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$Executable; $start.Arguments=$Arguments
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    $process.StartInfo=$start
    try {
        $null=$process.Start()
        $stdout=$process.StandardOutput.ReadToEndAsync()
        $stderr=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(10000)) {
            $process.Kill(); $notes.Add('Metadata executable exceeded 10-second limit'); return $null
        }
        if ($process.ExitCode -ne 0) { $notes.Add('Metadata executable returned nonzero exit status'); return $null }
        return $stdout.Result
    } catch { $notes.Add('Metadata executable could not be queried'); return $null }
    finally { $process.Dispose() }
}
$os = @(Read-Cim 'Win32_OperatingSystem')
$cpus = @(Read-Cim 'Win32_Processor')
$system = @(Read-Cim 'Win32_ComputerSystem')
$controllers = @(Read-Cim 'Win32_VideoController')
$disks = @(Read-Cim 'Win32_LogicalDisk')

$nvidia = @()
$smi = @(Get-Command 'nvidia-smi.exe' -CommandType Application -All -ErrorAction SilentlyContinue)
if (-not $smi) {
    $candidate = Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $smi = @([pscustomobject]@{Source=$candidate}) }
}
if ($smi.Count -gt 0) {
    $raw = Invoke-MetadataProcess $smi[0].Source '--query-gpu=index,name,driver_version,memory.total,memory.free --format=csv,noheader,nounits'
    if ($raw) {
        try {
            $nvidia = @($raw | ConvertFrom-Csv -Header index,name,driver_version,total_mib,free_mib | ForEach-Object {
                [pscustomobject]@{index=$_.index.Trim();name=$_.name.Trim();driver_version=$_.driver_version.Trim();dedicated_vram_total_mib=$_.total_mib.Trim();dedicated_vram_free_mib_at_audit=$_.free_mib.Trim();source='nvidia-smi';precision='driver_reported_MiB'}
            })
        } catch { $notes.Add('nvidia-smi output could not be parsed; VRAM unresolved') }
    }
}
$amdRegistry = @()
try {
    foreach ($device in @(Get-ChildItem -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Video' -ErrorAction Stop)) {
        foreach ($entry in @(Get-ChildItem -LiteralPath $device.PSPath -ErrorAction SilentlyContinue | Where-Object {$_.PSChildName -match '^\d{4}$'})) {
            $props = Get-ItemProperty -LiteralPath $entry.PSPath -ErrorAction SilentlyContinue
            if (-not $props) { continue }
            $description = [string]$props.DriverDesc; $provider = [string]$props.ProviderName
            if (($description+' '+$provider) -notmatch '(?i)AMD|ATI|Radeon|Advanced Micro Devices') { continue }
            $memory = $props.'HardwareInformation.qwMemorySize'; $preciseBytes = $null
            if ($memory -is [byte[]] -and $memory.Length -eq 8) { $preciseBytes=[BitConverter]::ToUInt64($memory,0) }
            elseif ($memory -is [uint64] -or $memory -is [long] -or $memory -is [int]) {
                if ($memory -ge 0) { $preciseBytes=[uint64]$memory }
            }
            $amdRegistry += [pscustomobject]@{description=$description;provider=$provider;dedicated_memory_bytes_if_reported=$preciseBytes;source='display_driver_registry_qwMemorySize';interpretation='Driver registry may be stale/ambiguous; confirm hardware. Never infer 4 GB from WMI.'}
        }
    }
} catch { $notes.Add('AMD display-driver registry values unavailable') }
$ports = @()
try {
    $ports = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in @(8188,8766)} | ForEach-Object {
        [pscustomobject]@{local_address=$_.LocalAddress;local_port=$_.LocalPort;owning_process_id=$_.OwningProcess}
    })
} catch { $notes.Add('Listening-port query unavailable') }
$services = @()
try {
    $services = @(Get-Service -ErrorAction Stop | Where-Object {($_.Name+' '+$_.DisplayName) -match '(?i)Study|Comfy|Python|Torch|Tailscale'} | Select-Object Name,DisplayName,@{Name='status';Expression={$_.Status.ToString()}})
} catch { $notes.Add('Service query unavailable') }
$pythonPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($command in @(Get-Command python.exe,python3.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
    if ($command.Source -notmatch '(?i)\\WindowsApps\\') { $null=$pythonPaths.Add($command.Source) }
}
$launchers = @(Get-Command py.exe -CommandType Application -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
foreach ($pattern in @((Join-Path $env:ProgramFiles 'Python*\python.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*\python.exe'))) {
    foreach ($item in @(Get-Item -Path $pattern -ErrorAction SilentlyContinue)) { $null=$pythonPaths.Add($item.FullName) }
}
$roots = @($SearchRoots)
if ($PSScriptRoot) { $roots += [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')) }
$installations = @()
foreach ($root in @($roots | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
    $comfy = (Test-Path -LiteralPath (Join-Path $root 'main.py') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $root 'comfy') -PathType Container)
    $study = (Test-Path -LiteralPath (Join-Path $root 'prototype\web_app.py') -PathType Leaf) -or (Test-Path -LiteralPath (Join-Path $root 'web_app.py') -PathType Leaf)
    $installations += [pscustomobject]@{path=$root;comfy_source_markers_present=$comfy;study_source_marker_present=$study;marker_presence_is_not_runtime_verification=$true}
    foreach ($relative in @('python.exe','python_embeded\python.exe','python_embedded\python.exe','.venv\Scripts\python.exe','venv\Scripts\python.exe')) {
        $candidate=Join-Path $root $relative
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $null=$pythonPaths.Add($candidate) }
    }
}
$metadataCode = @'
import json,sys,sysconfig,os,importlib.metadata as m
from pathlib import Path
paths=[sysconfig.get_path('purelib'),sysconfig.get_path('platlib')]
try: paths.append(sysconfig.get_path('purelib',scheme='nt_user'))
except (KeyError,AttributeError): pass
# -S on Python <=3.13 may leave venv prefixes pointing at the base interpreter.
# Use the executable location, not site initialization, to inspect venv metadata.
executable_dir=Path(sys.executable).parent
paths.extend([str(executable_dir/'Lib'/'site-packages'),str(executable_dir/'site-packages')])
if executable_dir.name.casefold()=='scripts': paths.append(str(executable_dir.parent/'Lib'/'site-packages'))
paths=list(dict.fromkeys(str(Path(p)) for p in paths if p))
wanted={'torch','torchvision','torchaudio','transformers','diffusers','comfyui','study','pillow'}
packages=[]
search=[]
for path in paths:
 entry={'path':path,'status':'unknown'}
 try:
  with os.scandir(path) as directory: next(directory,None)
  entry['status']='inspected_metadata_directory'
  for dist in m.distributions(path=[path]):
   name=dist.metadata.get('Name','')
   if name.lower().replace('_','-') in wanted: packages.append({'name':name,'version':dist.version,'metadata_path':str(dist.locate_file(''))})
 except FileNotFoundError: entry['status']='directory_not_found'
 except (OSError,ValueError): entry['status']='inspection_unavailable_or_incomplete'
 search.append(entry)
torch_detected=any(p['name'].lower().replace('_','-')=='torch' for p in packages)
print(json.dumps({'executable':sys.executable,'version':sys.version,'packages':packages,'package_search_paths':search,'torch_metadata_detection':'detected' if torch_detected else 'not_detected_in_inspected_metadata_paths; runtime availability unknown','runtime_importability':'not_tested; base/user metadata may not be visible to an isolated venv runtime','torch_module_loaded':'torch' in sys.modules,'bytecode_writes_disabled':sys.dont_write_bytecode,'inspection':'distribution metadata only; no site/torch import; no CUDA allocation; no claim of absence outside inspected paths'}))
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($metadataCode))
$python = @()
foreach ($executable in @($pythonPaths | Sort-Object)) {
    $arguments = '-B -I -S -c "exec(__import__(''base64'').b64decode('''+$encoded+'''))"'
    $raw = Invoke-MetadataProcess $executable $arguments
    if ($raw) {
        try { $python += ($raw | ConvertFrom-Json) }
        catch { $notes.Add('Python metadata result was not valid JSON') }
    }
}
[pscustomobject]@{
    schema_version=1;status='COLLECTED_READ_ONLY';hostname=$actualHost;collected_at_utc=[DateTime]::UtcNow.ToString('o')
    os=@($os | Select-Object Caption,Version,BuildNumber,OSArchitecture)
    cpu=@($cpus | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    ram=@($system | Select-Object TotalPhysicalMemory)
    disks=@($disks | Where-Object {$_.DriveType -eq 3} | Select-Object DeviceID,FileSystem,Size,FreeSpace)
    gpu=[pscustomobject]@{nvidia_smi=$nvidia;amd_registry=$amdRegistry;wmi=@($controllers | Select-Object Name,DriverVersion,AdapterRAM,PNPDeviceID);wmi_adapter_ram_warning='Win32_VideoController.AdapterRAM is a 32-bit field and may truncate/misreport discrete/shared memory; never infer a 4-GB GPU or model fit from this field alone.'}
    python_executables_discovered=@($pythonPaths | Sort-Object);python_executable_metadata=$python;python_launchers_not_executed=$launchers;installations=$installations
    searched_roots=$roots;search_scope='Explicit known roots and known interpreter locations only; not a whole-disk inventory.'
    listening_ports_8188_8766=$ports;matching_services=$services;notes=@($notes)
    model_selection='PENDING_HARDWARE_REVIEW';changes_performed=@();torch_imported=$false;gpu_allocation_attempted=$false
} | ConvertTo-Json -Depth 12
