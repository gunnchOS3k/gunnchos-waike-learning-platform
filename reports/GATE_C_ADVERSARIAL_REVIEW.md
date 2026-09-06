# Gate C Adversarial Review

Generated: 2026-09-06T19:57:24Z
Updated: 2026-09-06T21:25:00Z (full surgical closure C-OWNER-01…14)

## Scope
Fresh adversarial pass over OneRoster/QTI/LTI sabotage, deep-link auth bypass attempts,
backup tamper, role escalation, continuity secret smuggling, and AI security regression.
Plus full owner-blocker closures for DMG, Device OS integration, LTI JWKS, backup/restore,
UI, rate limits, packages, privacy, diagnostics, keyboard/a11y, performance/concurrency.

## Findings
| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| C-ADV-001 | High | OneRoster admin role import | Rejected (`ONEROSTER_ROLE_ESCALATION`) |
| C-ADV-002 | High | QTI XXE / entity | Rejected (`QTI_XXE_REJECTED`) |
| C-ADV-003 | High | LTI forged issuer/audience/nonce/deployment | Rejected with typed errors |
| C-ADV-004 | High | Deep-link without auth / cross-site | 401/403 |
| C-ADV-005 | Medium | Continuity payload secrets | Rejected (`CONTINUITY_SECRET_REJECTED`) |
| C-ADV-006 | Medium | Backup content/DB hash mismatch | Rejected (`BACKUP_TAMPER`) |

## C-OWNER findings and resolutions
| ID | Finding | Resolution |
|----|---------|------------|
| C-OWNER-01 | Fake macos-native (cargo-only metadata) | Real `pnpm exec tauri build` + `verify_macos_dmg.py` (hdiutil/codesign); PR-head artifact naming; Linux `if-no-files-found: error` |
| C-OWNER-02 | Contract-shape simulation; seed app SoR | Device OS PR #132 thin launcher companion; Platform imports live Device OS modules; integration contract JSON |
| C-OWNER-03 | Silent test-key JWKS fallback | Production HTTPS JWKS fetch; SSRF controls; kid+RS256; no test-key fallback; TTL+atomic state; identity reuse |
| C-OWNER-04 | Unhashed hub.sqlite3; FS copy | SQLite `Connection.backup()`; per-member size+sha256; site filter |
| C-OWNER-05 | Permissive restore assert; no restore API | Exact display_name restore proof; `POST /admin/restore`; admin UI wiring |
| C-OWNER-06 | Dead AdminHardeningPanel / static InteropStatusPanel | HubClient Gate C methods; panels mutate/fetch hub; mounted in App |
| C-OWNER-07 | Rate window never resets | Injectable clock; window reset; remaining/retry_after; cleanup; Retry-After |
| C-OWNER-08 | Event log not state machine | Semver state machine; revoke→open denied; unsafe downgrade rejected |
| C-OWNER-09 | Inactive enrollment left LMS active | Real section/enrollment mapping; inactive revokes access+leases; atomic validate-all |
| C-OWNER-10 | QTI 2.1; weak auth; ID collision; silent 0 | QTI 3 xmlns; section staff scope; external_identifier; malformed numeric reject |
| C-OWNER-11 | Privacy flags without behavior | Export block; deactivate+leases; retention hooks; `ferpa_claim=false` |
| C-OWNER-12 | Static diagnostics `health: ok` | Per-subsystem probes; never global OK if failing; redacted bundle |
| C-OWNER-13 | Keyboard tests on stubs | Real App/admin/interop keyboard journeys |
| C-OWNER-14 | GET-only perf/concurrency | Pilot fixture + p50/p95; concurrent mutations |

## Unresolved blockers
Physical Device Quartet, external LMS certification, FERPA, and production signing/notarization remain **external**.
Coordinated Device OS PR #132 must merge before Platform Gate C claims are earned (`REVIEW_CROSS_REPO_PR_DEPENDENCY_ORDER`).

## Verdict
Digital owner findings C-OWNER-01…14 addressed in code + tests. Not an independent security certification. Do not start Gate D. Do not merge either PR until owner completes Device OS → Platform order.
