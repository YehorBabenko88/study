# LS5 audit and model gate

The LS5 audit is **BLOCKED at authentication**. The coordinator observed the LS5 Tailscale peer online at `100.103.160.110` and TCP 22 open. The existing IP ED25519 host key was verified as `SHA256:QH5GA2rZo6kXqYRYwIJQRLGNW8MRid1TWyugB15JJoQ`. The Windows user is `LS-5`; its identity is distinct from the target hostname **LS5**. Strict hostname checking had no matching alias for `ls5`, and an IP-based batch login failed with `Permission denied (publickey,password,keyboard-interactive)`. Local SSH material reportedly consisted only of `known_hosts`; no usable key/config or running agent was available.

These observations establish connectivity, not hardware or usable application access. The JSON and text audit reports record every unknown explicitly. No further login/key guessing, host-key exception, credential/security alteration, remote service start, installation, model download, or PC1 hardware inventory is authorized by this audit task. The collector has not been run against actual LS5 hardware.

## Read-only collector

`deploy/ls5/audit-readonly.ps1` asserts the actual Windows machine name is exactly `LS5` (case-insensitive) **before** hardware, registry, port, service, or executable queries. Another hostname returns one BLOCKED JSON object. A username or alias `LS-5` does not satisfy that guard.

On LS5 it reads OS build, CPU cores/threads, physical RAM bytes, local fixed-disk capacity/free bytes, GPU names/drivers, selected display-driver registry values, listening TCP 8188/8766, matching services, known installation markers, and existing Python package metadata. It prints one JSON report to stdout and does not persist reports, change settings, start services, install packages, invoke a model, import Torch, or allocate GPU memory. Existing `nvidia-smi.exe` and discovered existing Python executables may run only to query inventory; Python uses `-B -I -S` to disable bytecode writes, isolate paths, and avoid site initialization. Launcher/Windows Store aliases are not executed. Metadata helpers are hidden, bounded to ten seconds, and their spawned process alone is stopped if it exceeds that limit.

The search is intentionally bounded to explicit known directories, portable package location when available, PATH Python executables, standard Python install locations, and common embedded/venv interpreter paths. It does not scan the whole disk. Missing installation/package evidence means **not detected in the searched scope**, not proof of absence. Source markers do not prove a working runtime. No CUDA availability/kernel test is performed.

Isolated `-S` execution on Python 3.12 can leave `sysconfig` pointing at the base interpreter even for a venv executable. The collector therefore also inspects `Lib\site-packages` relative to the actual executable directory, and for `Scripts\python.exe` inspects its parent venv's `Lib\site-packages`, without importing `site` or Torch. It reports every candidate directory and whether inspection succeeded, was unavailable/incomplete, or found no directory. Metadata detection never proves runtime importability: base/user packages may not be visible to an isolated venv. Undetected metadata leaves runtime availability unknown.

## Collect only after existing access is restored

An operator can run the script locally in an already-approved LS5 session without changing execution policy:

```powershell
& .\deploy\ls5\audit-readonly.ps1
# Optional: actual already-existing locations, if known
& .\deploy\ls5\audit-readonly.ps1 -SearchRoots @('C:\AI\ComfyUI_windows_portable','C:\AI\ComfyUI_windows_portable\ComfyUI','C:\Study')
```

If policy prevents the file from running, stop and use the established operator process; do not weaken execution policy or security settings. Do not execute this inventory on PC1.

After an existing approved SSH authentication path works again, the following streams the collector into LS5 PowerShell and returns JSON to the caller without copying a script file onto LS5. It is a prepared command, **not a login retry performed during this task**:

```powershell
Get-Content -Raw .\deploy\ls5\audit-readonly.ps1 |
  ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 -l LS-5 100.103.160.110 'powershell.exe -NoProfile -NonInteractive -Command -'
```

Retain strict host-key verification. A new or changed fingerprint is a separate trust issue; this document does not authorize accepting it. Any authentication error leaves the audit blocked. The caller may explicitly save the returned JSON on PC1 for review; the collector itself writes no report.

## Hardware evidence required before model selection

There is currently **no model selected**. Do not infer LS5 hardware from PC1 or from a generic Windows/Tailscale observation. Review actual GPU model, dedicated VRAM, driver, CPU, RAM, free disk, existing Python/Torch versions, and current ComfyUI/Study state first.

For NVIDIA, the collector queries `nvidia-smi` for GPU index, model, driver, total and currently free memory in MiB. Preserve that source and unit; an unavailable/N/A field is unresolved, not zero. Current free VRAM is a momentary observation. For AMD, available `HardwareInformation.qwMemorySize` registry evidence is recorded in bytes with explicit driver/staleness ambiguity. WMI `Win32_VideoController.AdapterRAM` is only a 32-bit field: truncation, shared/integrated memory, or reporting behavior must never become an assumed 4-GB discrete GPU. If reliable dedicated VRAM remains unavailable, obtain trusted local driver/hardware evidence before choosing a model.

After hardware review, any model/workflow choice needs its actual memory/runtime/storage requirements checked against that evidence. No recommendations or downloads are made here, and no image-conditioned workflow is claimed. The current Study generation path remains explicitly text-to-image until real reference-image upload and workflow wiring are implemented and tested.

## Verification performed without PC1 hardware queries

`../venv/Scripts/python.exe deploy/ls5/test_audit_readonly.py` runs the actual Windows PowerShell parser, a hostname-guard fixture whose inventory commands throw if reached, and an LS5 fixture with every hardware/process query mocked. It verifies JSON output, driver-reported NVIDIA MiB, AMD 64-bit byte values, the WMI ambiguity warning, and no-change/model-pending flags. These are collector tests, not an LS5 inventory or GPU acceptance test.

Additional Python-only fixtures create fake Torch `dist-info` under simulated venv, base, and embedded executable locations and execute only the extracted metadata block with `-B -I -S`. They verify executable-relative detection, scope reporting, no Torch import, and no bytecode cache writes. Running these fixture tests in the development venv does not inventory LS5 or PC1 hardware.
