# WAIKE V1 Public Learner Journey

Date checked: 2026-10-06
Implementation base: `90fb9c5ceab51d99dfff7b5e6d1775fd1dca85d6`
Curriculum source pin: `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62`
Package format: `waike.course_package.v1` / package version `1.0.0`

## Claim boundary

The automated implementation is ready for review. It does not claim a deployed public build,
a configured production school Hub, human usability approval, physical-device approval, external
interop certification, or production signing/notarization.

`V1_WAIKE_HUMAN_PASS=false`

## 18-track public/offline coverage

Counts and declarations are validated against `curriculum/registry/eighteen_tracks.json` and
`reports/WAIKE_18_TRACK_PACKAGE_MATRIX.json`. “Offline declared” means the signed source package
contains an offline pack; it does not mean the public browser has downloaded or installed it.

| Track | Lessons | Assignments | Quizzes | Labs | Groups | Portfolio | Offline declared | AI policy |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Digital Confidence to Computer Operator | 10 | 10 | 10 | 10 | 25 | 3 | Yes | Present |
| IT Support and Hardware Foundations | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Absent |
| Software Builder Zero-to-Hero | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Networking and Internet Infrastructure | 10 | 10 | 10 | 14 | 1 | 3 | Yes | Present |
| Cybersecurity Foundations and SOC Readiness | 10 | 10 | 10 | 13 | 1 | 3 | Yes | Present |
| Data, Databases, and Dashboards | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| AI/ML and Edge AI Foundations | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Embedded Systems and Device Prototyping | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Wireless, DSP, and 6G Foundations | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Project Management, Agile, and Lean Six Sigma | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Game Development and Interactive Media | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| 7GC AI-RAN Research Apprenticeship | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Cloud and DevOps | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Communication, Professional Development, and Ethics | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Robotics and Control | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| gunnchOS Device OS and Product Lab | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Hardware Engineering | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |
| Data Visualization and Business Intelligence | 10 | 10 | 10 | 10 | 1 | 3 | Yes | Present |

Digital Confidence's packaging gap is resolved from already-authored pinned canonical content.
`curriculum/digital_rc/DIGITAL_CONFIDENCE/course.json` and its shared `GENERAL_IT` content
provide 10 lessons, 10 assignments, 10 quizzes, 10 labs, 8 rubrics, 4 outcomes, 3 portfolio
mappings, AI policy, and an offline pack. The import now explicitly allows these paths.
No pedagogical content was invented; no upstream blocker remains for these packaging issues.

## Learner-surface matrix

`V1_REAL_CONTENT_MATRIX.md` records per-track reader counts and routes. All 18 pass
compile/verify and content reachability. Each selected document matches the signed
learner manifest hash. The package-level portfolio mapping count above differs from
the number of readable portfolio instruction documents (Digital Confidence: 2;
other tracks: 1). Exact package IDs and hashes are in `V1_PUBLIC_LEARNER_JOURNEY.json`.

| Surface | No-Hub public behavior | Hub/device behavior | Result |
|---|---|---|---|
| Today | States that no school schedule is available; links to all 18 tracks | Server schedule/feedback remains existing behavior | PASS |
| Courses | Searchable 18-track package catalog with readable titles and counts | Enrolled course cards remain existing behavior | PASS |
| Course/modules | Actual authored lesson titles, linked to Study | Hub module sequence remains existing behavior | PASS |
| Lesson/Study | Actual authored package markdown opens through Modules > Study | Verified installed pack opens authored content | PASS |
| Assignments | Actual authored instructions open through Assignments > Open; no draft/submit/receipt fabricated | Authenticated assessment lifecycle remains existing behavior | PASS |
| Calendar | States that due dates/events require a Hub | Hub-derived agenda remains existing behavior | PASS |
| Grades/mastery | States unavailable; creates no score, mastery, or completion | Hub grades/mastery remain existing behavior | PASS |
| Activities | Every packaged quiz/lab opens authored questions/instructions; attempts, groups, grading require Hub | Activity engine remains existing behavior | PASS |
| Messages | States that a Hub is required; no local thread is fabricated | Course discussion behavior remains Hub-owned | PASS |
| Portfolio | Actual authored portfolio instructions; submitted evidence requires Hub | Hub-owned evidence remains existing behavior | PASS |
| gunnchAI | Unavailable panel without Hub | Existing policy-scoped Hub adapter remains unchanged | PASS with external dependency |
| Mobile/keyboard | Mobile More menu now includes Grades; semantic buttons and focus path retained | Same role/auth boundaries | PASS automated, human review open |
| Device OS / 3k MLV return | Existing validated return link and launch-context auth boundary retained | No MLV or Device OS work redone | PASS regression scope only |

## Offline/sync matrix

| Contract | Evidence/result |
|---|---|
| Public shell reload | Service-worker cache version advanced; API/auth responses remain network-only |
| Installed pack availability | Catalog distinguishes package declarations from actual downloads/installs |
| Durable queue | Claimed only when a native sync coordinator exists |
| Lease expiry/revocation | Native focused tests PASS |
| Restart recovery | Native queue-and-lease restart test PASS |
| Conflict/rejection/retry | Existing coordinator state model retained; no public-Hub settlement claim |
| Receipt before acknowledgement | Native `ack_requires_a_durable_receipt` test PASS |
| Quarantine/tamper/wrong role | All three real pack fixtures PASS after isolated-output concurrency fix; assertions retained |

## Standards/integration matrix

| Integration | V1 state | External boundary |
|---|---|---|
| OneRoster | Existing Gate C implementation/matrix retained | External SIS certification remains false/open |
| QTI | Existing supported subset and security matrix retained | Full QTI 3 certification remains false/open |
| LTI | Existing supported subset and launch protections retained | External LMS certification remains false/open |
| gunnchAI | Existing pinned adapter/policy boundary retained | Real service availability is external |
| Device OS | Existing authenticated launch-context and endpoint-policy boundary retained | Physical device acceptance remains false/open |
| 3k MLV | Existing portal return contract retained | Hosted cross-product acceptance remains false/open |

## Validation result

- `scripts/validate_public_curriculum.py`: PASS, 18/18 catalog rows match registry order,
  package counts, offline declarations, AI declarations, and learner-visible verification.
- `make bootstrap`: PASS in the authorized isolated task worktree.
- `make compile-18`: 18/18 real packages compile and verify.
- `make gate-b-test`: 70 PASS; `make verify-gate-b`: AUTOMATED_PIPELINE_PASS.
- Full `make test`: PASS — 126 core, 99 Gate A, 201 Gate B, 74 Gate C, 16 Gate D,
  38 Rust, 78 frontend at the full run.
- Final frontend tests: 96/96 PASS (13 files), including exhaustive 18-track routing regression;
  frontend lint (`tsc --noEmit`): PASS.
- `make build`: PASS for Digital Confidence, Vite production bundle, native Rust binary.
- Verifier AI-boundary regression: 2 PASS. Gate C/D verifiers now honor explicit fake-AI
  disabling and default to disabled; production AI acceptance remains false.
- Final Gate C verifier: AUTOMATED_PIPELINE_PASS (223 prior regression + 74 Gate C).
  Final Gate D verifier: AUTOMATED_PIPELINE_PASS (487 prior regression + 16 Gate D).
  Both record `fake_ai_enabled=false`; zero required tests skipped.
- `V1_PUBLIC_LEARNER_JOURNEY.json`: complete per-track package IDs/content roots/ZIP hashes,
  real content counts, routes, signed source hash comparisons, final verifiers, and false gates.
- `git diff --check`: PASS.
- Native pack fixture compilation now uses isolated temporary output and serialization for shared
  report writes. All install/restart/tamper/unsigned/wrong-role assertions remain intact.
- Non-failing warnings: React `act`, Starlette/httpx deprecation, Rust unused helpers,
  and Vite's 832 kB chunk warning. Full tests/build were not repeated solely for continuity.
- Live public runtime/deployment: not established; no hosted acceptance claim is made.
- Final verifiers run against this candidate working diff on the recorded base. Local
  verifier PASS does not bind Linux/macOS release artifacts or a real Device OS Tauri
  launch to the future PR commit. Those CI binding checks remain pending and are
  required in the repository's CI acceptance path before release preparation is complete.

## Exact dependency and preservation evidence

Curriculum clean detached worktree:
`/Users/gunnchos/Downloads/gunnchos-codex-worktrees/waike-research-ops-63ba9f25`.
Device OS clean accepted copy: `4f02a48780d300a5d3a7758937b20e3bf9364d0d` at
`/Users/gunnchos/Downloads/gunnchos-codex-worktrees/gunnchos-device-os-4f02a487`.
gunnchAI clean accepted copy: `e2d1adcb5847cf00282fb7fa64970254b14e344e` at
`/Users/gunnchos/Downloads/gunnchos-codex-worktrees/gunnchai-e2d1adcb`.
Existing dirty dependency repositories remain untouched.

Fresh external binary patch: central spine `artifacts/waike-checkpoints/waike-v1-resume-current-20261006.patch`.
SHA-256: `9bb990114f9fee7e6184eebf320e7707f1473bc57bbc1f3b242a560a014178e1`.
Disk checks: approximately 14 GiB free before/after bootstrap, 12 GiB at resumption.

## Gates kept false/open

- `V1_WAIKE_HUMAN_PASS=false`
- Production public deployment/hosted acceptance: false
- Production school Hub functionality: false until configured and observed
- Human learner/staff usability approval: false
- Physical Pixel and Device Quartet acceptance for this candidate: false
- External OneRoster/QTI/LTI certification: false
- Production signing/notarization: false
- Independent security, accessibility, FERPA/privacy certification: false
- Production AI service acceptance: false
- CI release artifact and real Device OS launch binding to the PR head: pending
