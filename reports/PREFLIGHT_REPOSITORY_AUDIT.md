# Preflight repository audit

## SHAs
- waike-research-ops main: `8eb2827dc58ffa391842da1bfb1ee665c25a31a7` (matches blueprint)
- gunnchos-device-os main: `28562a8456207540c205a1c8a6434a491b0a4771` (matches blueprint)
- gunnchos-waike-learning-platform main: `187c662a83c0ca2dff97b2c7aaecbde5ba6e4da8`
- taxonomy branch tip pinned: see PIN.json

## Drift (fact)
- 18 canonical tracks; 16 digital_rc package dirs
- GENERAL_IT is a multi-track package id, not a unique alias
- COMPUTER_NETWORKING → NETWORKING_INFRA; CYBERSECURITY → CYBER_SOC (explicit historical package ids)

## Seed browser
`gunnchos-device-os/apps/waike_learning` is an HTML/JS catalog seed — not the Learning OS LMS.
