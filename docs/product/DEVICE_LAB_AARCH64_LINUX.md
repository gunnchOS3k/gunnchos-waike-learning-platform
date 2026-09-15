# Device Lab aarch64 Linux artifact

## Why

Device OS Interactive Development Guest is **aarch64**. Existing Gate D
`native-linux` on `ubuntu-latest` publishes an **x86_64** `waike-learning-client`.

On the aarch64 guest, `qemu-user-static` alone cannot run that dynamically
linked Tauri ELF (`Could not open '/lib64/ld-linux-x86-64.so.2'`), and a full
amd64 GTK/WebKit sysroot would be an unreasonable Device Lab dependency.

## What

Adds `.github/workflows/device-lab-aarch64-linux.yml` producing artifact
`waike-learning-os-device-lab-linux-aarch64` on native `ubuntu-24.04-arm`.

Triggers:

- pull_request (client / workflow / multi-arch docs paths)
- push to `main` (generates accepted-main ARM artifact; `artifact_source_sha=${{ github.sha }}`)
- push to `cursor/device-lab-aarch64-linux-ci` (feature-branch validation)
- workflow_dispatch

Uploads:

- ELF `waike-learning-client` (must be ARM aarch64; wrong-arch / missing = FAIL)
- `LINUX_AARCH64_SHA256SUMS.txt`
- `LINUX_AARCH64_ARTIFACT_META.txt` (intrinsic provenance only)
- `LINUX_AARCH64_FILE.txt`
- `LINUX_AARCH64_RUNTIME_DEPS.txt` (`file`, `readelf -h`, interpreter, `ldd`)

## Provenance

Intrinsic fields only: WAIKE source SHA / ref, OS, arch, Rust host/target,
filename, SHA-256, file/ELF summary, Node/pnpm/rustc/cargo versions, lockfile
SHA-256s, workflow run ID/attempt, `SOURCE_DATE_EPOCH` policy.

This workflow does **not** consume `waike-research-ops` curriculum content, so
no curriculum pin is recorded as consumed. Device OS / gunnchAI SHAs are
**not** hard-coded into artifact metadata (optional Device Lab guest hint only).

See also: [MULTI_ARCHITECTURE_SUPPORT.md](./MULTI_ARCHITECTURE_SUPPORT.md).

## Non-goals

- Does not replace or shrink Linux x86_64 Gate D or Windows Pilot 0.
- Does not claim Device Lab PASS until Device OS consumes the artifact on
  accepted-main (after owner merge + pin re-freeze + runtime re-earn).
- Does not merge itself; Edmund is sole merge authority.
- Does not treat qemu-user as a canonical aarch64 artifact.

## Device Lab note

Until this merges and pins re-freeze, Device OS WAIKE real-runtime evidence
must remain **FAIL** (honest) when only the x86_64 CI ELF is available.
