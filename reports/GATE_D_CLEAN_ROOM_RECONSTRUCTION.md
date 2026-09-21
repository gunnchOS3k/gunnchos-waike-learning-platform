# Gate D Clean-Room Reconstruction

Generated: 2026-09-20T18:57:26Z
OK: **True**

## Pins
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `waike`: `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62`
- `gunnchai`: `851e7916d6d5c7da23a8f30dba6bdfd389daa8ac`

## Observed
- `waike`: `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62`
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `gunnchai`: `851e7916d6d5c7da23a8f30dba6bdfd389daa8ac`
- `platform`: `700a6ac0f284d941e1b56fac38744ded526bd9f4`

## Forbidden (measured)
- `uncommitted_deps`: `False`
- `stale_db_reuse`: `False`
- `prior_run_artifact_reuse`: `False`
- `fixture_only_production_proof`: `False`

## Steps
1. Checkout platform Gate D head into empty runner workspace
2. Checkout waike-research-ops @63ba9f25ac6b8d8d1b6dd118923566fd51c57b62
3. Checkout gunnchos-device-os @4f02a48780d300a5d3a7758937b20e3bf9364d0d
4. Checkout gunnchAI3k @851e7916d6d5c7da23a8f30dba6bdfd389daa8ac
5. Align curriculum/registry/PIN.json absolute_path_hint to checkout
6. Install Python/Node/Rust toolchains without reusing prior pack_out/DBs
7. Run Gate D acceptance suites; fail closed on skip/xfail masks
8. Require this-run native + Device OS Tauri E2E (not fixture-only production proof)
