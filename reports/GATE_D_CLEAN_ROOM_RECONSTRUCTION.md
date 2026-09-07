# Gate D Clean-Room Reconstruction

Generated: 2026-09-07T03:01:07Z
OK: **False**

## Pins
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `waike`: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- `gunnchai`: `4b4f411710e8cdb8102a7e11502f8497f68156b1`

## Observed
- `waike`: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `gunnchai`: `4b4f411710e8cdb8102a7e11502f8497f68156b1`
- `platform`: `271944f3effdc7dc3ef82c11b1294f9c5a8159fa`

## Forbidden (measured)
- `uncommitted_deps`: `False`
- `stale_db_reuse`: `True`
- `prior_run_artifact_reuse`: `False`
- `fixture_only_production_proof`: `False`

## Steps
1. Checkout platform Gate D head into empty runner workspace
2. Checkout waike-research-ops @fbf7685bc5686201ccaa0128ee83346d59b3d584
3. Checkout gunnchos-device-os @4f02a48780d300a5d3a7758937b20e3bf9364d0d
4. Checkout gunnchAI3k @4b4f411710e8cdb8102a7e11502f8497f68156b1
5. Align curriculum/registry/PIN.json absolute_path_hint to checkout
6. Install Python/Node/Rust toolchains without reusing prior pack_out/DBs
7. Run Gate D acceptance suites; fail closed on skip/xfail masks
8. Require this-run native + Device OS Tauri E2E (not fixture-only production proof)
