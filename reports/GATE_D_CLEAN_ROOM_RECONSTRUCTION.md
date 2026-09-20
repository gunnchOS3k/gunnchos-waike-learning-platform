# Gate D Clean-Room Reconstruction

Generated: 2026-09-20T08:21:44Z
OK: **False**

## Pins
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `waike`: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- `gunnchai`: `c429750ff83b2a5344a6e1f40f5c7d27a863bf4d`

## Observed
- `waike`: `0c627ab700cf72a89a9aad06369e5dedb8fb9b82`
- `device_os`: `a64f544e98bed00213d06ab2130f2729c7a784fa`
- `gunnchai`: `c429750ff83b2a5344a6e1f40f5c7d27a863bf4d`
- `platform`: `e1fa0ee3205f57b7e1976b4aa437342f448aaece`

## Forbidden (measured)
- `uncommitted_deps`: `True`
- `stale_db_reuse`: `False`
- `prior_run_artifact_reuse`: `False`
- `fixture_only_production_proof`: `False`

## Steps
1. Checkout platform Gate D head into empty runner workspace
2. Checkout waike-research-ops @fbf7685bc5686201ccaa0128ee83346d59b3d584
3. Checkout gunnchos-device-os @4f02a48780d300a5d3a7758937b20e3bf9364d0d
4. Checkout gunnchAI3k @c429750ff83b2a5344a6e1f40f5c7d27a863bf4d
5. Align curriculum/registry/PIN.json absolute_path_hint to checkout
6. Install Python/Node/Rust toolchains without reusing prior pack_out/DBs
7. Run Gate D acceptance suites; fail closed on skip/xfail masks
8. Require this-run native + Device OS Tauri E2E (not fixture-only production proof)
