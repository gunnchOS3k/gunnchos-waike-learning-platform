# PR 1 acceptance matrix

| Gate | Evidence |
|------|----------|
| Repository truth audit | `reports/PREFLIGHT_REPOSITORY_AUDIT.md` |
| 18 canonical tracks | `curriculum/registry/eighteen_tracks.json` + tests |
| Alias collisions zero / no guessing | compiler registry tests |
| Pinned WAIKE revision | `curriculum/registry/PIN.json` |
| Versioned schemas validate | contract tests |
| DIGITAL_CONFIDENCE import | `reports/DIGITAL_CONFIDENCE_IMPORT_REPORT.md` |
| Deterministic signed learner pack | compiler + hash compare |
| Instructor encrypted separately | compiler + security tests |
| No instructor material in learner pack | security sabotage tests |
| Corruption / wrong-role / incompatible / downgrade rejected | security + compatibility tests |
| Tauri native target | `apps/client/src-tauri` build |
| Lesson open + encrypted SQLite persistence + restart | Rust + e2e tests |
| Hub scaffold | hub tests |
| CI / `make verify-pr1` | workflows + reports |
| No production secrets / PII committed | review + fixtures policy |
| Draft PR open, not auto-merged | GitHub |

Final aggregator statuses: `AUTOMATED_PIPELINE_PASS` or an explicit `AUTOMATED_PIPELINE_BLOCKED_*` reason.
