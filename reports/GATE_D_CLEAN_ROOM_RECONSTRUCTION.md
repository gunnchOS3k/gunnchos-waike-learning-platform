# Gate D Clean-Room Reconstruction

Generated: 2026-09-07T00:05:45Z
OK: **True**

## Pins
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `waike`: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- `gunnchai`: `4b4f411710e8cdb8102a7e11502f8497f68156b1`

## Observed
- `waike`: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- `device_os`: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- `gunnchai`: `4b4f411710e8cdb8102a7e11502f8497f68156b1`
- `platform`: `58daf1a0cc22b60c4246eb4195b74bcb0a714a38`

## Steps
1. Checkout platform Gate D head into empty runner workspace
2. Checkout waike-research-ops @fbf7685bc5686201ccaa0128ee83346d59b3d584
3. Checkout gunnchos-device-os @4f02a48780d300a5d3a7758937b20e3bf9364d0d
4. Checkout gunnchAI3k @4b4f411710e8cdb8102a7e11502f8497f68156b1
5. Align curriculum/registry/PIN.json absolute_path_hint to checkout
6. Install Python/Node/Rust toolchains without reusing prior pack_out/DBs
7. Run Gate D acceptance suites; fail closed on skip/xfail masks
