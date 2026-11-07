[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param(
    [ValidateSet('Plan','Menu','Audit','Install','Update','Rollback','Launch','Stop','Restart','Status','Backup','Restore','Uninstall')][string]$Action='Plan',
    [ValidateSet('Managed','External','Disabled')][string]$Mode='Disabled',
    [string]$Config,
    [string]$Manifest,
    [string]$Audit,
    [string]$BootstrapApprovalFile,
    [string]$ApprovalFile,
    [string]$PlanFile,
    [ValidateSet('study','comfy')][string]$Service='study',
    [string]$Destination,
    [string]$Backup,
    [string]$Release,
    [string]$RollbackTransactionId,
    [ValidateRange(0,300)][int]$MonitorSeconds=0
)
$ErrorActionPreference='Stop'
# Windows PowerShell 5.1 can evaluate parameter defaults before PSScriptRoot is
# available. Resolve script-relative defaults only after parameter binding.
if (-not $Config) {$Config=Join-Path $PSScriptRoot 'config.example.json'}
if (-not $Manifest) {
    $bundledManifest=Join-Path $PSScriptRoot '../../release_manifest.json'
    $Manifest=if (Test-Path -LiteralPath $bundledManifest -PathType Leaf) {$bundledManifest} else {Join-Path $PSScriptRoot 'release_catalog.json'}
}

function Read-SetupJson([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {return $null}
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}
function Get-SetupDigest([string]$Text) {
    $hash=[Security.Cryptography.SHA256]::Create()
    try {return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()} finally {$hash.Dispose()}
}
function Get-SetupFileDigest([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$hash=[Security.Cryptography.SHA256]::Create()
    try {return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-','').ToLowerInvariant()} finally {$hash.Dispose();$stream.Dispose()}
}
function Get-BootstrapPlan($Catalog,$Settings,[string]$ConfigPath,[string]$ManifestPath,[string]$AuditPath) {
    $artifact=$Catalog.bootstrap_python
    $root=$null
    if ($Settings.app_root) {
        $root=[string]$Settings.app_root
        if (-not [IO.Path]::IsPathRooted($root)) {$root=Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($ConfigPath))) $root}
        $root=[IO.Path]::GetFullPath($root)
    }
    $auditHash=if ($AuditPath -and (Test-Path -LiteralPath $AuditPath -PathType Leaf)) {Get-SetupFileDigest $AuditPath} else {$null}
    $manifestHash=if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {Get-SetupFileDigest $ManifestPath} else {$null}
    return [ordered]@{schema_version=1;phase='bootstrap';target_host='LS5';app_root=$root;manifest_sha256=$manifestHash;audit_sha256=$auditHash;artifact=$artifact;network_scope='one pinned official Python embedded ZIP only';changes='app-owned staging/runtime only; no system Python, drivers or registry';license_acceptance_required=$true;download_confirmation_required=$true}
}
function Assert-BootstrapAudit($Inventory) {
    if (-not $Inventory -or $Inventory.status -ne 'COLLECTED_READ_ONLY' -or $Inventory.hostname -ine 'LS5') {throw 'A fresh successful read-only LS5 audit is required.'}
    $when=[DateTimeOffset]::Parse($Inventory.collected_at_utc).ToUniversalTime()
    $age=([DateTimeOffset]::UtcNow-$when).TotalSeconds
    if ($age -lt -30 -or $age -gt 1800) {throw 'LS5 audit must be fresh (at most 30 minutes old).'}
    if (-not $Inventory.os -or $Inventory.os[0].Caption -notmatch 'Windows 11 Pro' -or $Inventory.os[0].OSArchitecture -notmatch '64' -or [int]$Inventory.os[0].BuildNumber -lt 22000) {throw 'Bootstrap requires audited Windows 11 Pro 64-bit compatibility.'}
}
function Assert-BootstrapPin($Artifact) {
    if (-not $Artifact -or $Artifact.runtime_kind -ne 'embedded' -or $Artifact.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $Artifact.sha256 -match '^([a-fA-F0-9])\1{63}$' -or [long]$Artifact.size_bytes -le 0 -or [long]$Artifact.size_bytes -gt 50000000 -or $Artifact.python_executable -ne 'python.exe') {throw 'Complete verified official Python embed pin is required; execution is blocked.'}
    $uri=[Uri]$Artifact.url
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('www.python.org','python.org') -or -not $uri.AbsolutePath.StartsWith('/ftp/python/') -or -not $uri.AbsolutePath.EndsWith('-embed-amd64.zip') -or $uri.Query -or $uri.Fragment -or $uri.UserInfo) {throw 'Bootstrap requires the pinned official Python HTTPS embed artifact.'}
    if (-not $Artifact.license_id) {throw 'Bootstrap license metadata is incomplete.'}
}
function Assert-BootstrapApproval($Approval,[string]$Digest) {
    if (-not $Approval -or $Approval.schema_version -ne 1 -or $Approval.phase -ne 'bootstrap' -or $Approval.approved -isnot [bool] -or $Approval.approved -ne $true -or $Approval.plan_sha256 -cne $Digest -or $Approval.license_accepted -isnot [bool] -or $Approval.license_accepted -ne $true -or $Approval.large_download_approved -isnot [bool] -or $Approval.large_download_approved -ne $true) {throw 'Explicit bootstrap plan hash, license and download approval is required.'}
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    if ([long]$Approval.expires_at -le $now -or [long]$Approval.expires_at -gt $now+1800) {throw 'Bootstrap approval must expire within the next 30 minutes.'}
}
function Assert-SetupLocalPath([string]$Path) {
    $cursor=[IO.Path]::GetFullPath($Path)
    if ($cursor.StartsWith('\\')) {throw 'UNC application paths are refused.'}
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'Linked application/runtime paths are refused.'}
        $parent=Split-Path -Parent $cursor
        if ($parent -eq $cursor) {break}
        $cursor=$parent
    }
}
function Assert-SetupTarget {
    if ([Net.Dns]::GetHostName() -ine 'LS5') {throw 'PC1 is development only. Execution requires actual LS5 hostname.'}
}
function Assert-ManagedActiveComponent($Descriptor,[string]$Component,[string]$AppRoot) {
    if (-not $Descriptor -or $Descriptor.owner -ne 'study-installer' -or $Descriptor.mode -ne 'managed') {throw 'Selected component has no installer-owned managed active descriptor.'}
    $root=[IO.Path]::GetFullPath($Descriptor.root)
    Assert-SetupLocalPath $root
    $releases=[IO.Path]::GetFullPath((Join-Path $AppRoot 'releases'))+'\'
    if (-not $root.StartsWith($releases,[StringComparison]::OrdinalIgnoreCase)) {throw 'Active component root escapes owned releases.'}
    $marker=Read-SetupJson (Join-Path $root '.study-managed-component.json')
    if (-not $marker -or $marker.schema_version -ne 1 -or $marker.owner -ne 'study-installer' -or $marker.component -ne $Component -or $marker.transaction_id -cne $Descriptor.transaction_id -or $marker.manifest_sha256 -cne $Descriptor.manifest_sha256 -or ([IO.Path]::GetFullPath($marker.component_root)) -ine $root) {throw 'Active component ownership marker does not match its descriptor.'}
    foreach ($member in @('code','python','entrypoint')) {if (-not ([IO.Path]::GetFullPath($Descriptor.$member)).StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Active component descriptor path escapes its root.'}}
    return $root
}
function Get-SetupWebResponse($Request) {return $Request.GetResponse()}
function Receive-SetupBootstrapArchive($Artifact,[string]$Archive) {
    Assert-SetupTarget
    $partial=$Archive+'.part';Assert-SetupLocalPath $partial
    $expected=[long]$Artifact.size_bytes
    $offset=if (Test-Path -LiteralPath $partial) {(Get-Item -LiteralPath $partial).Length} else {0L}
    if ($offset -ge $expected) {
        if ($offset -eq $expected -and (Get-SetupFileDigest $partial) -ceq $Artifact.sha256.ToLowerInvariant()) {[IO.File]::Move($partial,$Archive);return}
        [IO.File]::Move($partial,$partial+'.rejected-'+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds());$offset=0L
    }
    $request=[Net.HttpWebRequest]::Create([Uri]$Artifact.url)
    $request.AllowAutoRedirect=$false;$request.Timeout=180000;$request.ReadWriteTimeout=30000
    $timer=[Diagnostics.Stopwatch]::StartNew()
    if ($offset -gt 0) {$request.AddRange($offset)}
    $response=Get-SetupWebResponse $request
    try {
        $status=[int]$response.StatusCode
        if ($offset -gt 0 -and $status -eq 200) {[IO.File]::Move($partial,$partial+'.restart-'+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds());$offset=0L}
        if (($offset -eq 0 -and $status -ne 200) -or ($offset -gt 0 -and ($status -ne 206 -or $response.Headers['Content-Range'] -notmatch ('^bytes '+$offset+'-[0-9]+/'+$expected+'$')))) {throw 'Bootstrap resume status/range mismatch.'}
        if ($response.ContentLength -ge 0 -and $response.ContentLength -ne $expected-$offset) {throw 'Bootstrap response byte size mismatch.'}
        $input=$response.GetResponseStream();$output=[IO.File]::Open($partial,$(if ($offset -gt 0) {[IO.FileMode]::Append} else {[IO.FileMode]::CreateNew}),[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {$buffer=New-Object byte[] 65536;$total=$offset;while (($count=$input.Read($buffer,0,$buffer.Length)) -gt 0) {if ($timer.Elapsed.TotalSeconds -gt 180) {throw 'Bootstrap total time limit reached; partial retained.'};$total+=$count;if ($total -gt $expected) {throw 'Bootstrap exceeded approved byte size.'};$output.Write($buffer,0,$count)}} finally {$output.Dispose();$input.Dispose()}
    } finally {$response.Dispose()}
    if ((Get-Item -LiteralPath $partial).Length -ne $expected) {throw 'Bootstrap interrupted; owned partial retained for bounded Range resume.'}
    if ((Get-SetupFileDigest $partial) -cne $Artifact.sha256.ToLowerInvariant()) {[IO.File]::Move($partial,$partial+'.rejected-'+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds());throw 'Bootstrap complete digest mismatch; rejected bytes retained, nothing executes.'}
    [IO.File]::Move($partial,$Archive)
}
function Get-VerifiedBootstrap($Plan,[string]$Digest) {
    Assert-SetupTarget
    Assert-BootstrapPin $Plan.artifact
    $base=[IO.Path]::GetFullPath($Plan.app_root)
    if ($base.StartsWith('\\') -or $base -eq [IO.Path]::GetPathRoot($base)) {throw 'A dedicated local application root is required.'}
    Assert-SetupLocalPath $base
    $staging=Join-Path $base 'staging';Assert-SetupLocalPath $staging
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $lockPath=Join-Path $staging ('bootstrap-'+$Plan.artifact.sha256+'.lock');Assert-SetupLocalPath $lockPath
    # The file persists, but ownership is the exclusive OS handle, never a PID
    # or an existence check. A terminated process releases the handle itself.
    $bootstrapLock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
    $stage=Join-Path $base ('staging/bootstrap-'+$Plan.artifact.sha256)
    Assert-SetupLocalPath $stage
    $owned=Join-Path $stage 'bootstrap-owned.json'
    Assert-SetupLocalPath $owned
    if (Test-Path -LiteralPath $stage) {
        $record=Read-SetupJson $owned
        if (-not $record -or $record.owner -ne 'study-installer-bootstrap-v1' -or $record.sha256 -cne $Plan.artifact.sha256) {throw 'Existing bootstrap staging is not owned by this installer.'}
    } else {
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        @{owner='study-installer-bootstrap-v1';sha256=$Plan.artifact.sha256;approved_plan_sha256=$Digest} | ConvertTo-Json | Set-Content -LiteralPath $owned -Encoding UTF8
    }
    foreach ($path in @($base,(Split-Path -Parent $stage),$stage)) {if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked application/staging paths are refused.'}}
    $archive=Join-Path $stage 'python-embed.zip'
    Assert-SetupLocalPath $archive
    if (-not (Test-Path -LiteralPath $archive)) {
        Receive-SetupBootstrapArchive $Plan.artifact $archive
    }
    if ((Get-Item -LiteralPath $archive).Length -ne [long]$Plan.artifact.size_bytes -or (Get-SetupFileDigest $archive) -cne $Plan.artifact.sha256.ToLowerInvariant()) {throw 'Bootstrap ZIP byte count/hash mismatch. Preserved for diagnosis; nothing will execute.'}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $runtime=Join-Path $stage 'python'
    if (Test-Path -LiteralPath $runtime) {if ((Get-Item -LiteralPath $runtime).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked bootstrap runtime refused.'}} else {New-Item -ItemType Directory -Path $runtime | Out-Null}
    $zip=[IO.Compression.ZipFile]::OpenRead($archive)
    $listed=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    try {
        $unpacked=0L
        foreach ($entry in $zip.Entries) {
            $name=$entry.FullName.Replace('/','\');$unpacked+=$entry.Length
            if ($unpacked -gt 200000000 -or $name.Contains(':') -or $name.Split('\') -contains '..' -or [IO.Path]::IsPathRooted($name) -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {throw 'Unsafe bootstrap ZIP entry.'}
            $target=[IO.Path]::GetFullPath((Join-Path $runtime $name))
            if (-not $target.StartsWith($runtime+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Bootstrap ZIP path escape.'}
            if ($entry.Name -eq '') {continue}
            if (-not $listed.Add($target)) {throw 'Duplicate bootstrap ZIP path.'}
            $parent=Split-Path -Parent $target
            Assert-SetupLocalPath $parent
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            $cursor=$parent
            while ($cursor.Length -ge $runtime.Length) {if ((Get-Item -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked bootstrap entry refused.'};if ($cursor -eq $runtime) {break};$cursor=Split-Path -Parent $cursor}
            $source=$entry.Open();$sha=[Security.Cryptography.SHA256]::Create();try {$expected=([BitConverter]::ToString($sha.ComputeHash($source))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose();$source.Dispose()}
            if (-not (Test-Path -LiteralPath $target)) {
                $parts=Join-Path $stage 'extract-parts';Assert-SetupLocalPath $parts
                New-Item -ItemType Directory -Path $parts -Force | Out-Null
                $part=Join-Path $parts ((Get-SetupDigest $entry.FullName)+'.part');Assert-SetupLocalPath $part
                if ((Test-Path -LiteralPath $part) -and ((Get-Item -LiteralPath $part).Length -ne $entry.Length -or (Get-SetupFileDigest $part) -cne $expected)) {
                    [IO.File]::Move($part,$part+'.interrupted-'+[Guid]::NewGuid().ToString('N'))
                }
                if (-not (Test-Path -LiteralPath $part)) {
                    $source=$entry.Open();$sink=[IO.File]::Open($part,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                    try {$source.CopyTo($sink);$sink.Flush($true)} finally {$sink.Dispose();$source.Dispose()}
                }
                if ((Get-Item -LiteralPath $part).Length -ne $entry.Length -or (Get-SetupFileDigest $part) -cne $expected) {throw 'Incomplete extracted bootstrap entry retained; no runtime file published.'}
                [IO.File]::Move($part,$target)
            }
            if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked bootstrap file refused.'}
            if ((Get-Item -LiteralPath $target).Length -ne $entry.Length -or (Get-SetupFileDigest $target) -cne $expected) {throw 'Extracted bootstrap runtime changed; execution refused.'}
        }
        foreach ($file in Get-ChildItem -LiteralPath $runtime -Force -Recurse) {if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked bootstrap runtime entry refused.'};if (-not $file.PSIsContainer -and -not $listed.Contains($file.FullName)) {throw 'Unlisted bootstrap runtime file; execution refused.'}}
    } finally {$zip.Dispose()}
    $python=Join-Path $runtime 'python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {throw 'Verified archive has no Python executable.'}
    return $python
    } finally {$bootstrapLock.Dispose()}
}

# Dot-sourcing exposes pure validation functions to isolated fixture tests only.
if ($MyInvocation.InvocationName -eq '.') {return}
if ($Action -eq 'Menu') {
    Write-Host 'Study LS5: 1 Plan (read-only), 2 Install, 3 Update, 4 Launch, 5 Stop, 6 Status, 7 Restart, 8 Backup, 9 Restore, 10 Rollback, 11 Uninstall, 12 Read-only audit, 0 Exit'
    $choices=@{'1'='Plan';'2'='Install';'3'='Update';'4'='Launch';'5'='Stop';'6'='Status';'7'='Restart';'8'='Backup';'9'='Restore';'10'='Rollback';'11'='Uninstall';'12'='Audit'}
    $choice=Read-Host 'Choose an action; Enter keeps read-only Plan'
    if ($choice -eq '0') {return}
    $Action=if ($choices.ContainsKey($choice)) {$choices[$choice]} else {'Plan'}
    if ($Action -in @('Plan','Install','Update')) {
        $selectedMode=Read-Host "Comfy mode: 1 Disabled, 2 External API only, 3 Managed; Enter keeps $Mode"
        if ($selectedMode -eq '1') {$Mode='Disabled'} elseif ($selectedMode -eq '2') {$Mode='External'} elseif ($selectedMode -eq '3') {$Mode='Managed'}
    }
}
$catalog=Read-SetupJson $Manifest;$settings=Read-SetupJson $Config;$inventory=Read-SetupJson $Audit
$bootstrap=Get-BootstrapPlan $catalog $settings $Config $Manifest $Audit
$bootstrapJson=$bootstrap | ConvertTo-Json -Depth 30 -Compress
$digest=Get-SetupDigest $bootstrapJson
if ($Action -eq 'Plan') {
    [ordered]@{status='READ_ONLY';actual_host=[Net.Dns]::GetHostName();mode=$Mode.ToLowerInvariant();network_performed=$false;filesystem_mutation=$false;artifact_metadata_eligible=$catalog.release_ready;runtime_acceptance='not_tested';physical_acceptance='NOT_PERFORMED';bootstrap_plan_sha256=$digest;bootstrap_plan=$bootstrap;audit=$inventory;artifacts=$catalog.artifacts;next='Execution needs fresh LS5 audit, separate bootstrap hash/license/size approval, then exact engine plan approval. Missing dependency locks/pins block affected components.'} | ConvertTo-Json -Depth 40
    return
}
Assert-SetupTarget
if ($settings.target_host -ine 'LS5') {throw 'Configuration target must be LS5.'}
if ($Action -eq 'Audit') {& (Join-Path $PSScriptRoot 'audit-readonly.ps1');return}
if ($Action -eq 'Uninstall' -and $Service -eq 'comfy' -and $Mode -ne 'Managed') {throw 'External/Disabled Comfy is never removed.'}
if ($Action -in @('Launch','Stop','Restart','Status','Backup','Restore')) {
    if ($Service -eq 'comfy' -and $Mode -ne 'Managed' -and $Action -in @('Launch','Stop','Restart','Uninstall')) {throw 'External/Disabled Comfy is never started, stopped or removed by Study setup.'}
    $lifecycleConfig=[IO.Path]::GetFullPath($Config)
    if ($Action -in @('Launch','Stop','Restart')) {
        $activePath=Join-Path $bootstrap.app_root 'run/active.json'
        $active=Read-SetupJson $activePath
        if ($Service -eq 'comfy' -and $Action -in @('Launch','Restart') -and $active.comfy_mode -ne 'managed') {throw 'The authoritative active plan has Comfy disabled or external; managed startup requires an explicitly enabled managed plan.'}
        $descriptor=if ($active) {$active.components.$Service} else {$null}
        $root=Assert-ManagedActiveComponent $descriptor $Service $bootstrap.app_root
        foreach ($section in @('study','comfy')) {
            foreach ($key in $(if ($section -eq 'study') {@('python','release_dir','data_dir')} else {@('python','directory')})) {
                if (-not [IO.Path]::IsPathRooted($settings.$section.$key)) {$settings.$section.$key=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $lifecycleConfig) $settings.$section.$key))}
            }
        }
        $settings.app_root=$bootstrap.app_root
        foreach ($section in @('study','comfy')) {
            $item=$active.components.$section
            if ($item -and $item.owner -eq 'study-installer' -and $item.mode -eq 'managed') {
                $settings.$section.python=$item.python
                if ($section -eq 'study') {$settings.study.release_dir=$item.code}
                else {$settings.comfy.directory=$item.code;$settings.comfy.enabled=($item.enabled -is [bool] -and $item.enabled -eq $true);$settings.comfy.checkpoint=[IO.Path]::GetFileName($item.checkpoint);if ($item.checkpoint) {$settings.comfy | Add-Member -NotePropertyName checkpoint_path -NotePropertyValue $item.checkpoint -Force};if ($item.extra_model_paths) {$settings.comfy | Add-Member -NotePropertyName extra_model_paths -NotePropertyValue $item.extra_model_paths -Force}}
            }
        }
        if ($active.comfy_mode -eq 'disabled' -or -not $active.components.comfy) {$settings.comfy.enabled=$false}
        elseif ($active.comfy_mode -eq 'external') {
            $external=$active.components.comfy
            $settings.comfy.enabled=($external.owner -eq 'external' -and $external.enabled -is [bool] -and $external.enabled -eq $true -and $external.requires_external_acceptance -eq $false)
            $settings.comfy.checkpoint=[string]$external.checkpoint_name
        }
        $text=$settings | ConvertTo-Json -Depth 30
        $lifecycleConfig=Join-Path $bootstrap.app_root ('run/lifecycle-config-'+(Get-SetupDigest $text)+'.json')
        if (-not $PSCmdlet.ShouldProcess($lifecycleConfig,'Use validated managed active component descriptors for selected lifecycle action')) {return}
        if (-not (Test-Path -LiteralPath $lifecycleConfig)) {[IO.File]::WriteAllText($lifecycleConfig,$text,[Text.UTF8Encoding]::new($false))}
        elseif ([IO.File]::ReadAllText($lifecycleConfig) -cne $text) {throw 'Existing lifecycle configuration differs from its expected content.'}
    }
    switch ($Action) {
        'Launch' {& (Join-Path $PSScriptRoot 'start.ps1') -Config $lifecycleConfig -Service $Service}
        'Stop' {& (Join-Path $PSScriptRoot 'stop.ps1') -Config $lifecycleConfig -Service $Service}
        'Restart' {& (Join-Path $PSScriptRoot 'stop.ps1') -Config $lifecycleConfig -Service $Service;if (Test-Path -LiteralPath (Join-Path $bootstrap.app_root "run/$Service.json")) {throw 'Stop was not completed; restart refused.'};& (Join-Path $PSScriptRoot 'start.ps1') -Config $lifecycleConfig -Service $Service}
        'Status' {$deadline=(Get-Date).AddSeconds($MonitorSeconds);do {& (Join-Path $PSScriptRoot 'diagnose.ps1') -Config $lifecycleConfig;if ($MonitorSeconds -eq 0 -or (Get-Date) -ge $deadline) {break};Start-Sleep -Seconds 2} while ((Get-Date) -lt $deadline)}
        'Backup' {if (-not $Destination) {$Destination=Read-Host 'New backup destination'};& (Join-Path $PSScriptRoot 'backup.ps1') -Config $lifecycleConfig -Destination $Destination}
        'Restore' {if (-not $Backup) {$Backup=Read-Host 'Verified backup directory'};if (-not $Destination) {$Destination=Read-Host 'New empty restore destination'};& (Join-Path $PSScriptRoot 'restore.ps1') -Config $lifecycleConfig -Backup $Backup -Destination $Destination}
    }
    return
}
Assert-BootstrapAudit $inventory
if ($Action -eq 'Rollback' -and -not $PlanFile -and -not $RollbackTransactionId) {$RollbackTransactionId=Read-Host 'Exact transaction ID to restore';if (-not $RollbackTransactionId) {throw 'No rollback target selected.'}}
Assert-BootstrapPin $bootstrap.artifact
Write-Host ($bootstrap | ConvertTo-Json -Depth 30)
Write-Host "Bootstrap plan SHA256: $digest"
$approval=Read-SetupJson $BootstrapApprovalFile
if (-not $approval) {
    if ((Read-Host 'Type the exact bootstrap plan SHA256 to approve this app-local bootstrap') -cne $digest) {throw 'Bootstrap not approved.'}
    if ((Read-Host "Type ACCEPT $($bootstrap.artifact.license_id) to accept its license") -cne "ACCEPT $($bootstrap.artifact.license_id)") {throw 'License not accepted.'}
    if ((Read-Host "Type DOWNLOAD $($bootstrap.artifact.size_bytes) to approve the stated bytes") -cne "DOWNLOAD $($bootstrap.artifact.size_bytes)") {throw 'Download not approved.'}
    $approval=[pscustomobject]@{schema_version=1;phase='bootstrap';approved=$true;plan_sha256=$digest;license_accepted=$true;large_download_approved=$true;expires_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()+900}
}
Assert-BootstrapApproval $approval $digest
if (-not $PSCmdlet.ShouldProcess($bootstrap.app_root,'Bootstrap the approved pinned official Python ZIP into owned app-local staging only')) {return}
$python=Get-VerifiedBootstrap $bootstrap $digest
$receipt=Join-Path (Split-Path -Parent (Split-Path -Parent $python)) ('approval-'+$digest+'-'+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()+'.json')
[IO.File]::WriteAllText($receipt,(@{plan=$bootstrap;approval=$approval} | ConvertTo-Json -Depth 35),[Text.UTF8Encoding]::new($false))
$arguments=@('-B','-S',(Join-Path $PSScriptRoot 'installer_cli.py'),'--action',$Action.ToLowerInvariant(),'--mode',$Mode.ToLowerInvariant(),'--config',[IO.Path]::GetFullPath($Config),'--manifest',[IO.Path]::GetFullPath($Manifest),'--audit',[IO.Path]::GetFullPath($Audit))
if ($PlanFile) {$arguments+=@('--plan-file',[IO.Path]::GetFullPath($PlanFile))}
if ($ApprovalFile) {$arguments+=@('--approval-file',[IO.Path]::GetFullPath($ApprovalFile))}
if ($Action -eq 'Uninstall') {$arguments+=@('--component',$Service)}
if ($RollbackTransactionId) {$arguments+=@('--rollback-transaction-id',$RollbackTransactionId)}
& $python @arguments
if ($LASTEXITCODE -ne 0) {throw 'Installer did not complete; preserved transaction/staging state is available for diagnosis.'}
