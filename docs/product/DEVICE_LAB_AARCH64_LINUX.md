# Device Lab aarch64 Linux artifact

## Why

Device OS Interactive Development Guest is **aarch64**. Existing Gate D
`native-linux` on `ubuntu-latest` publishes an **x86_64** `waike-learning-client`.

On the aarch64 guest, `qemu-user-static` alone cannot run that dynamically
linked Tauri ELF (`Could not open '/lib64/ld-linux-x86-64.so.2'`), and a full
amd64 GTK/WebKit sysroot would be an unreasonable Device Lab dependency.

## What

Adds `.github/workflows/device-lab-aarch64-linux.yml` producing artifact
`waike-learning-os-device-lab-linux-aarch64` on `ubuntu-24.04-arm`.

## Non-goals

- Does not replace or shrink the Learning OS product surface.
- Does not claim Device Lab PASS until Device OS consumes the artifact on
  accepted-main (after owner merge + pin re-freeze).
- Does not merge itself; Edmund is sole merge authority.

## Device Lab note

Until this merges and pins re-freeze, Device OS WAIKE real-runtime evidence
must remain **FAIL** (honest) when only the x86_64 CI ELF is available.
