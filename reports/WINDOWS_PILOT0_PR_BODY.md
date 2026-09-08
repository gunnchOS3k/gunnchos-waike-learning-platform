## Summary
- Add authentic Windows Pilot 0 evidence workflow on `windows-2025` (authoritative) plus `windows-latest` compatibility smoke.
- Tauri native Windows package build (NSIS/MSI) + install/launch/data/soak evidence collector.
- Does **not** claim signing/production/human/Device Lab readiness.

## Test plan
- [ ] `windows-pilot0-windows-2025` job green on this PR head
- [ ] Evidence artifact `reports/windows_pilot0/WINDOWS_PILOT0_EVIDENCE.json` uploaded and bound to short SHA
- [ ] Claim is PASS only if skipped_required_checks=0 and soak >=1800s
- [ ] Owner merge only after reviewing evidence (Cursor merges nothing)
