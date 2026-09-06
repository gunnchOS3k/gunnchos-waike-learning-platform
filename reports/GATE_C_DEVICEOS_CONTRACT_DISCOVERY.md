# Gate C Device OS Contract Discovery

Generated: 2026-09-06T19:41:40Z

## Device OS main
`28562a8456207540c205a1c8a6434a491b0a4771` (accepted main; platform tests against this)

## Found contracts
| Surface | Path |
|---|---|
| App registry | `gunnchos_device_os/app_registry.py` (`waike_offline`) |
| App runtime | `gunnchos_device_os/app_runtime.py` (`waike`) |
| Launcher | `gunnchos_device_os/launcher.py` |
| Permissions | `gunnchos_device_os/permissions_manager.py` |
| Continuity | `gunnchos_device_os/shell/continuity_coordinator.py` |
| Update | `gunnchos_device_os/updater.py` + `shared_contracts/update_contract.schema.json` |
| Dock capabilities | `config/dock/capability_descriptors.json` |

## Adapter policy
Platform **consumes** Device OS contracts via a bridge. Device OS remains authority for install/launcher/capability/update semantics. Platform never bypasses auth on deep links and never puts secrets/keys in continuity handoff.

## Device Quartet (digital only)
Student 14.5", Handheld Hybrid, DS-XL Coder, Edge IO Wearables — synthetic capability profiles. Physical validation remains external.

## Device OS PR
Not required for Gate C if accepted-main contracts remain sufficient.
