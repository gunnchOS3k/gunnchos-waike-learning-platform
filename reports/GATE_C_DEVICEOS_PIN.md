# Gate C — Device OS pin (C-OWNER-02)

## Pin

| Field | Value |
|-------|-------|
| Previous (main baseline) | `28562a8456207540c205a1c8a6434a491b0a4771` |
| **Current DEVICE_OS_PIN_REF** | `5afc126ef1ce0fe917f78d1a3434c1de801535fb` |
| Branch | `cursor/waike-learning-deviceos-integration` |
| PR (draft) | https://github.com/gunnchOS3k/gunnchos-device-os/pull/132 |

Gate C workflow (`.github/workflows/gate-c.yml`) and `scripts/verify_gate_c.py` checkout this **PR head SHA**, not `main`, for all deviceos jobs until the Device OS integration PR merges.

## Relationship

`launcher_wrapper_relationship: thin_launcher_companion`

- Platform Tauri `com.gunnchos.waike.learning` = Learning OS system of record
- Device OS `waike_learning_os` (alias `waike_offline`) = registry + policy + IPC handoff
- `apps/waike_learning` HTML seed = discovery/lab companion only

## Contract

`contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json`
