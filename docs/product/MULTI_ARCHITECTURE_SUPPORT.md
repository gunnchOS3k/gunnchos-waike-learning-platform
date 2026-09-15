# Multi-architecture support (WAIKE Learning Platform)

## Policy

Architecture coverage is **additive**. Adding a new OS/arch pair must not
remove or shrink an existing validated path. Prefer honest FAIL over false
PASS when an artifact cannot run on a target guest.

## Current matrix

| OS | Arch | Producer | Artifact / check | Status |
|---|---|---|---|---|
| Linux | x86_64 | Gate D `native-linux` (`ubuntu-latest`) | `waike-learning-os-gate-d-linux` | Retained |
| Linux | aarch64 | Device Lab `native-linux-aarch64` (`ubuntu-24.04-arm`) | `waike-learning-os-device-lab-linux-aarch64` | Added (PR #9) |
| Windows | x86_64 | Windows Pilot 0 | Windows Pilot 0 jobs | Retained |

## Rules

1. **Linux x86_64 retained** — Gate D `native-linux` remains the Learning OS
   linux-amd64 producer. Device Lab aarch64 does not replace it.
2. **Linux aarch64 added** — Native ARM64 runner only. `qemu-user` is not a
   canonical ARM artifact when a native runner is available.
3. **Windows retained** — Windows Pilot 0 stays required for Windows evidence.
4. **Future arches are additive** — macOS, further Windows SKUs, etc. may be
   added without deleting existing producers.
5. **Functionality not reduced per arch** — Each arch ships the same Tauri
   client product surface for that host; arch-specific packaging differences
   are limited to ABI/runtime deps, not feature cuts.
6. **Provenance is intrinsic** — Artifact metadata records WAIKE source SHA,
   ref, OS/arch, toolchain versions, lockfile digests, workflow run identity,
   and build epoch policy. Cross-repo Device OS / gunnchAI SHAs are not
   required pin fields for the aarch64 Device Lab artifact.

## Device Lab note

Device Lab Interactive Guest is aarch64. Until PR #9 merges, accepted-main
re-freezes, and Device OS re-earns runtime evidence, Device Lab WAIKE remains
honest FAIL when only the x86_64 CI ELF is available.
