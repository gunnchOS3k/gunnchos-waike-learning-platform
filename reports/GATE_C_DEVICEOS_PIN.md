# Gate C — Device OS pin (C-OWNER-02)

## Pin

| Field | Value |
|-------|-------|
| Previous (pre-merge main) | `28562a8456207540c205a1c8a6434a491b0a4771` |
| Merged PR tip (ancestral) | `5afc126ef1ce0fe917f78d1a3434c1de801535fb` |
| **Current DEVICE_OS_PIN_REF** | `4f02a48780d300a5d3a7758937b20e3bf9364d0d` |
| Branch | `main` |
| PR (owner-merged) | https://github.com/gunnchOS3k/gunnchos-device-os/pull/132 |

Gate C workflow (`.github/workflows/gate-c.yml`) and `scripts/verify_gate_c.py` checkout this **accepted Device OS `origin/main` SHA** (merge commit for PR #132).

## Relationship

`launcher_wrapper_relationship: thin_launcher_companion`

- Platform Tauri `com.gunnchos.waike.learning` = Learning OS system of record
- Device OS `waike_learning_os` (alias `waike_offline`) = registry + policy + IPC handoff
- `apps/waike_learning` HTML seed = discovery/lab companion only

## Contract

`contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json`
