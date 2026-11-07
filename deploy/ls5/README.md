# LS5 lifecycle source preparation

These are prepared source files, **not an installed or validated LS5 deployment**. No Windows service, Scheduled Task, startup entry, firewall change, package installation, or model download has been performed. PC1 is development only. LS5 audit and explicit user confirmation are required before installation or service execution.

The actual target hostname must be exactly `LS5`, case insensitive. `LS-5` may be an SSH username; it is not an accepted hostname. There is no PC1 override.

## Unified setup entry point

`setup.ps1` is the operator entry point; it does not require manually installed Python for its default read-only plan. `setup.ps1 -Action Menu` presents the action menu and explicit Disabled / External / Managed choice. Enter retains the read-only/default selection; it never approves a download or installation. `-Action Audit` invokes the guarded read-only LS5 collector and prints its JSON report.

Execution has two independent approval boundaries. First, a fresh LS5 Windows 11 Pro x64 audit and exact bootstrap-plan hash, PSF license acceptance and byte-count confirmation permit one pinned official Python embedded ZIP in app-owned staging. ZIP size/hash, extraction paths and every reused runtime file are checked before Python can execute. No system Python, registry setting, driver or global package environment is changed. Owned partial bootstrap downloads support bounded HTTP Range resume; complete hashes must match before promotion/extraction. Rejected bytes remain available for diagnosis and never execute. App-local approval receipts record the approved bootstrap plan.

Same-artifact bootstrap attempts hold one exclusive OS file handle across owned-stage validation, downloads, extraction and final runtime verification. The handle releases automatically when its process exits; a remaining lock file is not a stale PID and is not deleted to take ownership. ZIP entries are verified in temporary files outside the runtime tree, then atomically published. An interrupted temporary entry is retained/quarantined and rebuilt from the verified ZIP on retry. Existing committed runtime tampering, unlisted files or an unowned/malformed initial staging marker cause refusal and diagnosis rather than automatic cleanup.

The verified stdlib orchestrator then reviews the exact installer transaction plan: selected artifact hashes, licenses, download bytes, mode, configuration and audit digest. The user confirms that exact hash, selected license IDs and byte budget, or supplies matching expiring approval files. `-BootstrapApprovalFile` is distinct from the engine `-ApprovalFile`; there is no force/automatic approval switch. A managed CPU/GPU/model installation additionally requires an explicitly reviewed plan and hardware compatibility. Candidate metadata alone is not executable approval; incomplete Managed dependency/model/hardware gates remain blockers.

Disabled installs/operates Study without Comfy. External uses the existing loopback API and never starts, stops, updates or deletes external Comfy. Managed components require an authoritative active pointer plus matching installer ownership marker. Launch/restart derive executable and code paths from that pointer, not stale example paths. `-Action Status -MonitorSeconds 30` provides a bounded foreground status monitor without registering any background service. Rollback requires an explicitly selected transaction and a new exact-plan approval. Uninstall delegates to the owned-component retention planner; it is not a general recursive directory-removal command.

Managed component removal may remove that component's installer-owned embedded runtime after verifying retained learner files/model contents. Shared model storage, external persistent data, other components, external Comfy and independently existing Python environments are outside that removal scope. Interrupted removal resumes from its exact saved plan and retention journal rather than creating a new transaction.

Example interfaces, to review **after** LS5 audit and approval, not commands already run:

```powershell
.\setup.ps1
.\setup.ps1 -Action Menu
.\setup.ps1 -Action Audit > .\ls5-audit.json
.\setup.ps1 -Action Install -Mode Disabled -Audit .\ls5-audit.json -Manifest .\release_manifest.json
.\setup.ps1 -Action Status -MonitorSeconds 30
```

Use the bundle's materialized manifest with its exact built Study source ZIP; `release_catalog.json` is research/candidate metadata, not a substitute for that bound release. Managed availability is separate from Study-only Disabled/External readiness. No genuine runtime installation, model download or LS5 execution has occurred during source preparation.

The code-only distribution is built from one clean committed HEAD by `build_bundle.py`. Its default `release_manifest.json` binds that exact source ZIP and Study's closed wheel lock. Optional `managed-cpu-*.candidate.json` files bind the separately verified 86-wheel CPU metadata graph and models with pinned licence documents. They are alternatives, not defaults or an LS5 model selection. Their `runtime_acceptance` remains `not_tested`; a fresh LS5 fit review, explicit CPU opt-in, selected model/legal/download approval, and actual managed inference are still mandatory. No CUDA runtime is selected from PC1 hardware. `release.json` and the ZIP hash identify the delivered code; no model/runtime payload is included in the distribution.

Managed removal preserves shared data/models and first copies legacy data found inside owned code into a plan-owned retained directory with hashes. Complete component inventories and the ownership marker prevent deleting replacement/unlisted files after an interruption. Recorded files are removed before the marker; a saved plan can resume mid-removal. Corrupt or unknown ownership/lock state fails closed for diagnosis rather than deleting data. Unrecognized empty legacy lifecycle locks require manual inspection; recognized dead-PID locks use serialized OS-level reclamation.

## Independent processes and storage

Review `config.example.json` after the LS5 audit. Relative paths resolve relative to the configuration file. The low-level lifecycle wrappers below require separate existing environments. The approval-bound installer can prepare separate managed embedded-Python runtime folders from pinned payloads; it never invokes unconstrained package resolution or installs a global Python.

- Study uses its configured Python and release, listening on `127.0.0.1:8766`. Text/board operation does not require an installed or running Comfy process.
- Comfy uses its own configured Python and existing checkout, listening on `127.0.0.1:8188`. It is disabled by default and requires a reviewed existing checkpoint.
- Releases live below `app_root/releases`; persistent databases/assets live outside every release in `study.data_dir`.
- Comfy output/user directories are `study.data_dir/comfy/output` and `study.data_dir/comfy/user`. Python environments, Comfy code, and models remain separate.

Comfy launch requests loopback binding, disabled browser auto-launch/API nodes/custom nodes, and explicit external output/user directories. Installed CLI source must contain every requested flag; unsupported versions are refused. This compatibility check does not establish that arbitrary installed code is safe. The installed Comfy version, dependencies, hardware and models require audit. References: [official CLI source](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/cli_args.py), [startup flags](https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/startup-flags.mdx).

## Operator interface — after approval on LS5

These examples describe the interface; they have not been executed:

```powershell
.\start.ps1 -Config C:\Study\config.json -Service study
.\start.ps1 -Config C:\Study\config.json -Service comfy
.\diagnose.ps1 -Config C:\Study\config.json
.\stop.ps1 -Config C:\Study\config.json -Service study
.\stop.ps1 -Config C:\Study\config.json -Service comfy
```

Start launches only the selected service in a hidden window, with timestamped stdout/stderr under `app_root/logs`. Bounded readiness requires the recorded PID to own the expected loopback listener and return HTTP 200. Unrelated listeners are never stopped. Failure retains ownership records/logs for diagnosis; it does not kill an unknown process. Actual Windows venv launcher/child-process behavior remains unverified on LS5; unexpected listener ownership fails readiness rather than claiming success.

Stop checks PID, executable, full command line, creation time, service and configuration. PID reuse or identity mismatch causes refusal. Stop, restore and code removal support PowerShell confirmation and `-WhatIf`.

## Offline data operations and code removal

Study must be stopped for offline data operations. Owned Managed Comfy must also be stopped, including a retained managed component under a globally Disabled plan, because its output/user files share the external data tree. A validated External API-only descriptor does not require its unmanaged port 8188 listener to stop; it is never controlled by these operations. Legacy managed records/configuration still protect their known writers. Close other programs that write directly into the data tree. Changes to source membership, size or modification time cause backup refusal. Startup and offline operations share `app_root/run/lifecycle.lock`; native PowerShell writers stamp and flush their PID before work for the shared recovery protocol. An empty/unrecognized creation-before-stamp orphan requires diagnosis, never blind deletion.

```powershell
.\backup.ps1 -Config C:\Study\config.json -Destination D:\StudyBackups\new-backup
.\restore.ps1 -Config C:\Study\config.json -Backup D:\StudyBackups\new-backup -Destination C:\Study\restored-new
.\uninstall-code.ps1 -Config C:\Study\config.json -Release C:\Study\releases\current -WhatIf
```

Backup requires a new destination outside the source tree. SQLite files use the backup API, explicitly closed handles and integrity checks; asset copies have SHA-256/size manifests. An interrupted backup without a completed valid manifest cannot be restored. Source data is not deleted.

Restore verifies manifest paths, listed membership, hashes and SQLite integrity before writing into a separate new/empty destination. Existing data is never overwritten. Configuration is not switched automatically. This is an offline local backup format, not an encrypted/authenticated archive; use trusted storage.

Code removal accepts only the exact configured resolved release below `app_root/releases`, verifies release markers/protected paths, and holds the lifecycle lock through final validation and removal. It refuses linked/reparse paths and known legacy learner storage inside the release. Preserve or migrate such legacy data separately before retrying; no automatic movement is performed. It does not remove `app_root`, external data, environments, Comfy or models.

## Validation boundary

Tests use temporary databases/files, launch plans and a temporary Windows junction. PowerShell syntax parsing is not service execution. No production service, GPU workload, user-data backup, installation or uninstall has been run on PC1 or LS5. Actual LS5 permissions, process ownership/readiness and restart behavior remain approval-gated acceptance work. Persistent autostart is not configured.
