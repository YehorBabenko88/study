# Unified Study installer design and release research

This change prepares an installer release contract; it does not certify or install LS5. SSH authentication remains blocked, so LS5 GPU, VRAM, RAM, free disk, driver and runtime state are unknown. The catalogue contains 19 pinned artifact candidates. A complete Study-only Python wheel lock is available; An explicit CPU candidate now has a closed metadata-only dependency lock (see the candidate section below); Managed ComfyUI remains blocked by runtime acceptance and LS5 hardware/model fit. CUDA dependency closure remains unresolved. No model, Torch wheel, Python ZIP, or portable runtime payload was downloaded during this research.

## Three explicit modes

- **Managed** owns a separate ComfyUI source tree and embedded Python environment, alongside Study's independent owned environment. It requires a complete audited release manifest, fresh LS5 inventory, explicit device/model review, model licence acceptance and approved download byte budget.
- **External** installs Study's owned runtime only. Connection to an existing ComfyUI is explicit; the installer does not upgrade, uninstall, stop, or modify that external runtime.
- **Disabled** installs Study's owned runtime only and leaves generation unavailable. It never silently selects a GPU, model, or CPU fallback.

The catalogue is metadata, not blanket installation approval. `manifest_validation.validate_manifest(manifest, plan, hardware)` validates only artifacts reachable from selected components and returns a detached JSON manifest or raises `ManifestError`. External/Disabled plans select `components:["study"]`. An initial Managed installation selects Study and ComfyUI; independent updates can select either component. Whenever ComfyUI is selected, `release_ready:false` cannot be bypassed by supplying a GPU name. A Study-only update does not require a new Comfy lock/model choice or enable a new Comfy runtime; the engine must preserve the existing policy and ownership/proof boundary. A Comfy-only update requires the engine's already-active verified Study prerequisite for smoke testing.

## Bootstrap without a preinstalled Python

Native PowerShell can display the download/licence/size plan before invoking Python. After the user's exact plan approval, the bootstrap verifies and extracts the official pinned Python ZIP into an application-owned folder, then uses that interpreter for the standard-library installer engine. The same verified archive can populate **separate** Study and ComfyUI interpreter folders; they do not share writable site-packages. System Python, PATH, registry, SSH/security settings and existing services remain untouched.

| Artifact | Version and exact bytes | SHA-256 |
| --- | --- | --- |
| Windows x64 embedded Python | 3.13.12; 10,941,233 | `76f238f606250c87c6beac75dccd35ee99070a13490555936abb6cb64ecce3d0` |
| pip universal wheel | 25.3; 1,778,622 | `9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd` |

The Python digest agrees between the [official release page](https://www.python.org/downloads/release/python-31312/) and the message digest in its [Sigstore metadata](https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip.sigstore); size came from an HTTPS HEAD response. The Sigstore signature itself was **not cryptographically verified** during this metadata review. The installer must verify the actual downloaded bytes before extraction. The pip hash/size comes from [PyPI's exact-version metadata](https://pypi.org/pypi/pip/25.3/json).

Python's embedded distribution omits pip; its documentation does not present it as a conventional pip-managed developer installation. This application-local runtime design therefore explicitly vendors the pinned pip wheel and dependency set. It modifies only its owned `python*._pth` to include `Lib/site-packages` and `import site`; it does not run the full Python EXE installer, register Python, or use an existing interpreter's packages. This is an application packaging choice, not a claim that stock embedded Python supplies venv/pip. See [Python's embedding guidance](https://docs.python.org/3.13/using/windows.html#the-embeddable-package). ComfyUI's [official portable documentation](https://docs.comfy.org/installation/comfyui_portable_windows) independently demonstrates a packaged runtime with its own `python_embeded` directory.

The engine verifies all wheel bytes into a local wheelhouse, bootstraps the pinned pip wheel, then installs the closed requirements using `--no-index --only-binary=:all: --require-hashes --no-deps`. A successful `pip check` and component smoke checks are required before activation. No resolver selects fresh packages during installation. Archive path, symlink/reparse, executable location and rollback checks belong to the engine; a hash alone does not make an archive path safe.

## Complete Study-only Python package lock

The selected target is standard CPython 3.13 on Windows x86-64, not free-threaded Python or ARM64. The source bundler must still produce and pin the **exact Study source ZIP** before this becomes an executable Study release.

| Distribution | Pin | Wheel target | Required base dependencies |
| --- | --- | --- | --- |
| Pillow | 12.1.0 | cp313-cp313-win_amd64 | None; optional extras excluded |
| PyMuPDF | 1.26.7 | cp310-abi3-win_amd64 | None |
| pytesseract | 0.3.13 | py3-none-any | packaging >=21.3; Pillow >=8.0.0 |
| packaging | 25.0 | py3-none-any | None |

Exact byte counts, SHA-256 values, URLs, `Requires-Python`, licence identifiers and full `Requires-Dist` metadata are recorded in `deploy/ls5/release_catalog.json`. Primary evidence: [Pillow 12.1.0 JSON](https://pypi.org/pypi/Pillow/12.1.0/json), [PyMuPDF 1.26.7 JSON](https://pypi.org/pypi/PyMuPDF/1.26.7/json), [pytesseract 0.3.13 JSON](https://pypi.org/pypi/pytesseract/0.3.13/json), [packaging 25.0 JSON](https://pypi.org/pypi/packaging/25.0/json). Selected versions satisfy the two base pytesseract constraints; extras are not selected. This is the entire selected **Python** dependency closure, not a bundle of native OCR/speech/model engines. PyMuPDF carries AGPL/commercial licensing considerations recorded by its package metadata; release distribution must retain applicable licence notices/terms.

`pytesseract` does not bundle the Tesseract executable or language data. This manifest does not install or claim those external tools; OCR retains the existing truthful unavailable state when they are absent. Likewise the lock does not silently install optional speech/translation models.

The Study component's foreground entrypoint is `deploy/ls5/study_service.py`, invoked by the lifecycle engine with its generated active configuration. The underlying application remains `prototype/web_app.py`; it is not launched directly without the external-data/guard setup. The owned Python path policy includes source root, the safe launcher directory and `code/prototype` so isolated mode can import existing sibling Study modules.

`materialize_manifest(catalog, mode="disabled"|"external", study_source_artifact=...)` accepts a source ZIP artifact supplied by the release bundler: `{id,kind:"zip",local_path:"payload/study.zip",sha256,size,...}` or an immutable approved HTTPS URL. It binds that source to the audited Study lock without unlocking ComfyUI. The engine must verify bundled bytes and reject paths escaping the bundle; no fabricated remote Study release URL is used. Managed materialization is refused until its additional gates are complete.

## Pinned ComfyUI source and runtime candidates

ComfyUI v0.43.0 resolves to commit `426f5eea52a7ece1dd599fff4cb6cd1f352ddd24` in the [official tag API](https://api.github.com/repos/Comfy-Org/ComfyUI/git/ref/tags/v0.43.0). The root explicitly authorized one bounded source-only fetch. The [commit-addressed source ZIP](https://codeload.github.com/Comfy-Org/ComfyUI/zip/426f5eea52a7ece1dd599fff4cb6cd1f352ddd24) was streamed, hashed, and discarded without extraction/execution: **13,595,371 bytes**, SHA-256 `01f381c8330f5c5bec9bd3d4c651e8b53b45ffb70020b9e1e947fc63f93a1548`. Expected archive root is `ComfyUI-426f5eea52a7ece1dd599fff4cb6cd1f352ddd24`.

The official v0.43.0 NVIDIA portable archive also has release metadata pins: **2,039,673,203 bytes**, SHA-256 `4928f88e6a8407c4574d4f7d92cfeba020d782edba4a076b7d107ecc98955e50`. It is a **7z research candidate only**: the ZIP-only engine must reject selecting it. Its embedded package contents, extraction tool and compatibility have not been audited here. Evidence: [official versioned release metadata](https://api.github.com/repos/Comfy-Org/ComfyUI/releases/tags/v0.43.0).

The [commit-pinned requirements](https://raw.githubusercontent.com/Comfy-Org/ComfyUI/426f5eea52a7ece1dd599fff4cb6cd1f352ddd24/requirements.txt) contain both exact frontend/template pins and many unbounded or minimum-version dependencies. Pinning three Torch wheels does **not** close that graph. Its full target-specific transitive wheel set, dependency markers/constraints and smoke tests remain a release gate. No sdist/build-script fallback, live package resolver, custom-node installation or arbitrary workflow execution is permitted by this design.

## PyTorch candidate matrix and hardware gate

The catalogue records exact Windows cp313 x86-64 wheel URLs, SHA-256 values and HEAD byte sizes for these published combinations:

| Candidate | torch | torchvision | torchaudio |
| --- | --- | --- | --- |
| Explicit CPU | 2.10.0+cpu | 0.25.0+cpu | 2.10.0+cpu |
| CUDA 12.8 | 2.10.0+cu128 | 0.25.0+cu128 | 2.10.0+cu128 |
| CUDA 13.0 | 2.10.0+cu130 | 0.25.0+cu130 | 2.10.0+cu130 |

These combinations are listed on [PyTorch's official previous-version instructions](https://pytorch.org/get-started/previous-versions/); exact cp313 Windows availability and hashes were read from its official [CPU](https://download.pytorch.org/whl/cpu/torch/), [cu128](https://download.pytorch.org/whl/cu128/torch/) and [cu130](https://download.pytorch.org/whl/cu130/torch/) indexes. Wheel existence is ABI evidence, not LS5 certification. The official [ComfyUI portable guide](https://docs.comfy.org/installation/comfyui_portable_windows) distinguishes a Python 3.13/CUDA 13 NVIDIA package from an older-GPU CUDA 12.6/Python 3.12 package. Our cu128 candidates therefore never become an automatic LS5 choice.

[NVIDIA's compatibility guide](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html) describes family-level minimum driver ranges and feature/PTX caveats. A family table alone does not certify a GPU architecture, Windows driver, specific wheel or workload; this task does not install/update a driver or CUDA toolkit.

A Managed plan must bind a fresh (<=30-minute) `COLLECTED_READ_ONLY` audit for hostname LS5 using `hardware_review.audit_sha256`. `audit_sha256(audit)` is canonical strict JSON SHA-256 (sorted keys, compact separators, UTF-8). A human-reviewed `component_compatibility:"approved"` assertion covers GPU architecture, driver, runtime and selected workflow. CUDA additionally requires `gpu_verified:true` and positive `vram_bytes` matching a precise NVIDIA `nvidia-smi` reading. WMI AdapterRAM and unknown/AMD evidence cannot silently select CUDA. ARM64 is incompatible with these win_amd64 artifacts. Models require reviewed RAM/VRAM requirements; the catalogue intentionally invents no fit thresholds. CPU requires `device:"cpu"` and explicit `cpu_opt_in:true`, plus a reviewed hardware audit; unknown/no GPU never implies automatic CPU generation. Disabled/External remain explicit alternatives.

The plan also states `approved_download_bytes` covering all selected unique artifact sizes. Managed checks a conservative three-times-artifact-size free-disk margin for download, extraction and rollback; this is an installer headroom rule, not a model's official runtime footprint. The engine should additionally bind paths and exact manifest/plan digests before any write.

## Checkpoint candidates and licence acceptance

Only single-checkpoint **SD1/SDXL text-to-image** candidates compatible with the existing allowlisted workflow are recorded. No FLUX workflow or image/reference-conditioning capability is implied.

- Maintainer SD1.5 EMA-only checkpoint: repository `stable-diffusion-v1-5/stable-diffusion-v1-5`, commit `451f4fe16113bff5a5d2269ed5ad43b0592e9a14`, `v1-5-pruned-emaonly.safetensors`, **4,265,146,304 bytes**, SHA-256 `6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa`. Its [pinned maintainer card](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/blob/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/README.md) identifies CreativeML Open RAIL-M, but this repository contains no standalone licence file. Exact acceptance-document pin remains unresolved and blocks selecting this candidate; no 404 URL is treated as a licence.
- Stability AI SDXL base 1.0: commit `462165984030d82259a11f4367a4eed129e94a7b`, `sd_xl_base_1.0.safetensors`, **6,938,078,334 bytes**, SHA-256 `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`. The [pinned licence document](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/462165984030d82259a11f4367a4eed129e94a7b/LICENSE.md) identifies Open RAIL++ terms; its small document bytes/hash are recorded in the catalogue.

File hashes/sizes came from maintainer repository LFS metadata; no checkpoint payload was downloaded. Selection requires reviewed model requirements and explicit `accepted_licenses:[license_id]` bound to a pinned licence document. Metadata approval is not model licence acceptance, and an accepted licence is not proof that the checkpoint fits LS5. Redirect/CDN access and payload byte verification still need to pass the engine's approved-host policy when a real release is eventually prepared.

## Validation evidence and current boundary

`../venv/Scripts/python.exe deploy/ls5/test_release_catalog.py` covers complete fixture manifests, real catalogue Study-only materialization, missing/placeholder hashes, unapproved or mutable URLs, unsafe bundled/archive paths, unclosed locks, mismatched wheel versions/ABIs, requirement-text injection, licence/download approvals, stale/unknown/ARM audits, unsupported model memory, and explicit CPU opt-in. These are metadata/fixture checks; they do not install packages or query a GPU. Engine tests and actual isolated runtime smoke/rollback evidence are separate acceptance gates.

The remaining Managed gates are recorded in the catalogue and must remain visible in the installer. In particular, changing a label to “ready” is insufficient: the validator separately requires closed audited component locks, complete selected pins, licence approval, precise hardware evidence and reviewed model fit. No LS5 installation, service activation, GPU smoke test or performance claim has occurred.

## Guarded metadata-only Comfy lock attempt

Two bounded attempts used the existing development pip 24.0 resolver with `--dry-run --ignore-installed --python-version3.13 --platformwin_amd64 --abicp313 --only-binary=:all:` semantics and the commit-pinned Comfy requirements plus exact Torch/vision/audio 2.10.0/0.25.0 CPU or cu130 variants. A pre-request `PipSession.send` guard allowed only approved HTTPS indexes and `.whl.metadata` URLs; package/archive payloads were rejected before transmission. VCS/build subprocesses were disabled. No pip upgrade or installation was performed.

CPU stopped after 29.401 seconds and cu130 after 25.709 seconds. Each made 185 allowed index/metadata requests, then pip selected a PyTorch-mirror Colorama 0.4.6 wheel without usable metadata-only preparation and attempted its wheel body. The guard refused it before network send. There is **no completed dependency lock or successful pip report** from these attempts. Target-marker/extra closure and compatibility remain unverified; the host resolver was development Python3.12 targeting3.13. Failure evidence is retained in `docs/COMFY_METADATA_RESOLUTION_REPORT.json`. The existing Managed lock gate remains closed; no fallback package payload download was attempted.

Separately, HEAD-only inspection of both pinned checkpoint resolve URLs observed `huggingface.co` redirecting to exactly `us.aws.cdn.hf.co` and returning200. Only hostname chains/status were retained; signed redirect URLs/tokens were neither displayed nor saved, and no checkpoint bytes were read. Those exact redirect hosts are per-artifact catalogue entries and members of the top allowlist. The validator rejects wildcard, scheme/port, IP, duplicate, or unlisted redirect host entries. The downloader must still validate every HTTPS hop and actual payload size/hash; a successful HEAD is not an installed model or inference proof.

The root authorized one final source-filtered retry per profile. Torch/vision/audio candidates were restricted to official PyTorch hosts; all generic packages were restricted to PyPI/files.pythonhosted.org. This fixed the Colorama metadata selection. Both profiles then reached pip24's `prepare_linked_requirements_more` stage and attempted the actual `comfyui_frontend_package-1.57.4` wheel body. The unchanged HTTP guard refused both before transmission. This demonstrates a dry-run completion step attempting payload download, not a proven missing dependency or completed target lock. All four attempts and source filters are preserved in the report. No further retries were performed; the catalogue is frozen with Managed dependency readiness still false.

## Separately authorized post-resolver CPU candidate capture

After the four preserved failed dry-run attempts, the root authorized one concretely different <=60-second CPU-only capture. It intercepted `RequirementPreparer.prepare_linked_requirements_more` after resolvelib chose `result.mapping`, serialized the already-prepared PEP658 metadata, then stopped deliberately **before** any payload completion request. The unchanged HTTP payload guard remained installed. Exact wheel URLs/hash/size were checked against official exact-version PyPI JSON or the existing official Torch index pins. No model, runtime or wheel body was fetched.

The capture completed in **39.145 seconds** and contains **86 wheels totaling 904,951,215 bytes**. Every active Requires-Dist constraint, selected extra and root requirement was checked against an explicit Windows x86-64/CPython3.13.12 marker environment; every filename tag and Requires-Python value was checked for that target. This is a metadata-verified closed **CPU candidate**, not evidence that the packages import or execute successfully. The custom deliberate-stop exception becomes pip24 exit2, so there is still no normal successful pip report; the separate capture proof and offline graph tests are the evidence. The earlier failure report is unchanged.

`deploy/ls5/comfy_cpu_lock_candidate.json` is off by default, with `runtime_acceptance:"not_tested"`, no selected model, and no LS5 hardware certification. Compatible stable-ABI wheels such as cp37/cp38/cp39/cp310/cp312-abi3 are valid on standard cp313; the validator continues to reject future ABI floors, free-threaded Python and incompatible architectures. No cu130 graph capture was attempted or promoted.

An explicit caller can use:

```python
manifest = materialize_managed_cpu_candidate(
    catalog, graph_candidate, built_study_zip_pin, model_id,
    profile="cpu-metadata-verified",
)
```

There is no profile/model default. The model must have an exact pinned licence document: SDXL's document is present; the unresolved SD1.5 licence-document candidate is refused. `components.comfy.model_artifact_id` and its artifact list bind the exact checkpoint. The materialized manifest's `release_ready:true` is explicitly scoped to **metadata/artifact/closed-lock eligibility**, with `runtime_acceptance:"not_tested"` and `requires_real_generation_smoke:true`; it is not permission to enable an untested runtime. The default catalogue's `release_ready:false` remains unchanged.

A real trial still requires a fresh LS5 audit, `device:"cpu"`, `cpu_opt_in:true`, audit-bound compatibility review, selected licence acceptance and exact byte-budget approval. For this candidate the operator's hardware review must explicitly provide `model_fit:{model_id,requirements_reviewed:true,min_ram_bytes:...}`; no RAM threshold or fitness claim is invented by the materializer. The required RAM must fit the same audited machine. The engine must then install only into owned inactive environments, run pip checks and independent Study verification, and obtain actual owned Comfy HTTP generation/PNG proof before generation is enabled. Failed runtime or generation acceptance leaves the candidate unaccepted and preserves the prior active version.

`test_comfy_cpu_lock_candidate.py` performs five offline checks: all86 pins/tags, exact target dependency and root closure, default-off/runtime-unaccepted flags, explicit materialization/licence refusal, and continued audit/CPU/model-fit/licence/budget gates. Its synthetic audit and RAM values are **fixtures only**, not recommended SDXL requirements or an LS5 inventory. The17 catalogue/validator tests remain passing. No installation or hardware query is part of these tests.
