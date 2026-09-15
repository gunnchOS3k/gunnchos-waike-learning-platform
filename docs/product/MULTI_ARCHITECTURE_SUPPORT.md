# Multi-architecture support (WAIKE Learning Platform)

## Policy

Architecture coverage is **additive**. Adding a new OS/arch pair must not
remove or shrink an existing validated path. Prefer honest FAIL over false
PASS when an artifact cannot run on a target guest.

**Distro / glibc compatibility is a first-class portability contract**, not an
afterthought of “same arch.” Two aarch64 Linux artifacts may both be native ARM
and still be incompatible with a guest if their measured `GLIBC_*` requirements
differ.

## Current matrix

| Target | OS | Arch | Producer | Artifact / check | Status |
|---|---|---|---|---|---|
| Windows x86_64 | Windows | x86_64 | Windows Pilot 0 | Windows Pilot 0 jobs | Retained |
| Linux x86_64 | Linux | x86_64 | Gate D `native-linux` (`ubuntu-latest`) | `waike-learning-os-gate-d-linux` | Retained |
| Linux aarch64 current / newer-glibc (`aarch64-current`) | Linux | aarch64 | Device Lab `native-linux-aarch64` (`ubuntu-24.04-arm`) | `waike-learning-os-device-lab-linux-aarch64` | Retained |
| Linux aarch64 glibc-2.36 baseline (`aarch64-glibc236`) | Linux | aarch64 | Device Lab `native-linux-aarch64-glibc236` (ARM runner + Debian 12 bookworm userspace) | `waike-learning-os-linux-aarch64-glibc236` | Added |
| Future targets | — | — | Additive qualification | — | Additive |

## Rules

1. **Linux x86_64 retained** — Gate D `native-linux` remains the Learning OS
   linux-amd64 producer. Device Lab aarch64 targets do not replace it.
2. **Linux aarch64 current retained** — Native `ubuntu-24.04-arm` producer stays
   as `aarch64-current` (newer glibc). Not overwritten by glibc236.
3. **Linux aarch64 glibc-2.36 added** — Native ARM64 runner with Debian 12
   bookworm userspace. Measured max `GLIBC_*` must be ≤ 2.36 (fail-closed).
   `qemu-user` is not a canonical ARM artifact.
4. **Windows retained** — Windows Pilot 0 stays required for Windows evidence.
5. **Future arches / distros are additive** — macOS, further Windows SKUs,
   additional glibc baselines, etc. may be added without deleting existing
   producers.
6. **Functionality not reduced per arch** — Each arch ships the same Tauri
   client product surface for that host; arch-specific packaging differences
   are limited to ABI/runtime deps, not feature cuts.
7. **Provenance is intrinsic** — Artifact metadata records WAIKE source SHA,
   ref, OS/arch, distro/glibc contract, toolchain versions, lockfile digests,
   workflow run identity, and build epoch policy. Cross-repo Device OS /
   gunnchAI SHAs are not required pin fields for Device Lab artifacts.
8. **RuntimeTarget metadata** — glibc236 publishes `RUNTIME_TARGET.json` with
   compatibility label `linux-aarch64-glibc236` for zero-surprise Device OS
   preflight consumption (preflight implementation is a follow-up re-earn).

## Device Lab note

Device Lab Interactive Guest is Debian 12 / glibc 2.36 on aarch64. Prefer the
`aarch64-glibc236` artifact for that guest. The Ubuntu ARM (`aarch64-current`)
artifact remains valid for newer-glibc hosts and must not be deleted.

Until the glibc236 PR merges, accepted-main re-freezes, and Device OS re-earns
runtime evidence on the glibc236 ELF, Device Lab WAIKE remains honest FAIL when
only the newer-glibc Ubuntu ARM ELF is available.
