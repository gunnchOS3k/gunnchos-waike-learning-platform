# PR1 Verification — post taxonomy-merge repin

- Status: `AUTOMATED_PIPELINE_PASS`
- Claim: `DIGITALLY_IMPLEMENTED_AND_AUTOMATICALLY_TESTED_FOR_PR1_SCOPE`
- declared_pinned_commit (WAIKE merged main): `e97e74fc9bfb44b1cdc26b272dc4848264f15fe0`
- observed_source_commit: `e97e74fc9bfb44b1cdc26b272dc4848264f15fe0`
- Taxonomy PR #56: **merged** into main at the pin above
- Learner package hash: `732ec8af7600b0d415ae2898fd6113ea056ca9ad7ec013b759b05327c10d4505`
- Python: 38 passed
- Rust: 5 passed
- Frontend: 7 passed

## Checks

- PASS `provenance_match`
- PASS `registry_18`
- PASS `compile`
- PASS `learner_deterministic`
- PASS `instructor_plaintext_deterministic`
- PASS `instructor_ciphertext_unique`
- PASS `report_provenance`
- PASS `python_tests`
- PASS `rust_tests`
- PASS `frontend_tests`
- PASS `docs`

## Artifact distinction

- Desktop recovered DMG = historical exact PR1 artifact evidence
- Final GitHub Actions macOS artifact after this repin = authoritative for final PR1 head
