# Device Lab aarch64 glibc-2.36 (Debian 12) artifact

## Why

Device Lab Interactive Development Guest is **Debian 12 / glibc 2.36** on
**aarch64**. The retained Ubuntu 24.04 ARM producer
(`waike-learning-os-device-lab-linux-aarch64`, target `aarch64-current`) links
against newer glibc symbols (observed `GLIBC_2.39`) and cannot exec on that
guest.

## What

Adds `.github/workflows/device-lab-aarch64-glibc236.yml` producing artifact
`waike-learning-os-linux-aarch64-glibc236` (target `aarch64-glibc236`).

Build model:

- Host runner: native `ubuntu-24.04-arm` (not qemu-user)
- Userspace: pinned Debian 12 bookworm container (`node:20-bookworm@sha256:…`)
- Product: full Tauri `waike-learning-client` with WebKitGTK/GTK build deps
- Gate: measured max `GLIBC_*` symbol version must be **≤ 2.36** (fail-closed)

Triggers:

- pull_request (client / workflow / measure script / multi-arch docs paths)
- push to `main` (accepted-main artifact; `artifact_source_sha=${{ github.sha }}`)
- push to `cursor/device-lab-aarch64-glibc236` (feature-branch validation)
- workflow_dispatch

Uploads:

- ELF `waike-learning-client` (must be ARM aarch64; wrong-arch / missing = FAIL)
- `LINUX_AARCH64_GLIBC236_SHA256SUMS.txt`
- `LINUX_AARCH64_GLIBC236_ARTIFACT_META.txt` (intrinsic provenance only)
- `LINUX_AARCH64_GLIBC236_FILE.txt`
- `LINUX_AARCH64_GLIBC236_RUNTIME_DEPS.txt` (`file`, `readelf -h`, interpreter, `ldd`)
- `LINUX_AARCH64_GLIBC236_GLIBC_SYMBOLS.txt` (raw `objdump`/`readelf` evidence)
- `LINUX_AARCH64_GLIBC236_GLIBC_MAX.txt`
- `RUNTIME_TARGET.json` (machine-readable portability contract)

Compatibility label: `linux-aarch64-glibc236`.

## Provenance

Intrinsic fields only: WAIKE source SHA / ref, OS, arch, Debian version, base
image identity, measured max GLIBC, ELF interpreter, Rust host/target,
filename, SHA-256, Node/pnpm/rustc/cargo versions, lockfile SHA-256s, WebKitGTK
/ GTK pkg-config versions, workflow run ID/attempt, `SOURCE_DATE_EPOCH` policy.

Device OS / gunnchAI SHAs are **not** hard-coded into artifact metadata.

## Zero-surprise contract (artifact → Device OS preflight)

These fields are published on the artifact so Device OS can later refuse launch
before exec when the guest cannot satisfy the ABI. **Device OS preflight
implementation is a follow-up re-earn**, not this PR.

| Field | Source |
|---|---|
| Target architecture | `RUNTIME_TARGET.json` → `architecture` |
| ELF interpreter | `RUNTIME_TARGET.json` → `elf_interpreter` |
| Required GLIBC (measured max) | `RUNTIME_TARGET.json` → `measured_max_glibc` (+ baseline `glibc_baseline`) |
| Required shared libraries | `RUNTIME_TARGET.json` → `dynamic_dependency_summary` (+ WebKit/GTK blocks) |
| Artifact / source provenance | `source_sha`, `artifact_sha256`, workflow run identity |

## Non-goals

- Does not replace or shrink Linux x86_64 Gate D, Ubuntu ARM (`aarch64-current`),
  or Windows Pilot 0.
- Does not fake compatibility (ELF string edits, bundling newer glibc,
  qemu-user-as-native, feature stripping).
- Does not claim Device Lab PASS until owner merge + pin re-freeze + runtime
  re-earn on the glibc236 artifact.
- Does not merge itself; Edmund is sole merge authority.
- Does not modify Device OS or portal in this change.

See also: [MULTI_ARCHITECTURE_SUPPORT.md](./MULTI_ARCHITECTURE_SUPPORT.md),
[DEVICE_LAB_AARCH64_LINUX.md](./DEVICE_LAB_AARCH64_LINUX.md).
