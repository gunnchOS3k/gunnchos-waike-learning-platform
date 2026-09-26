# WAIKE adoption parity audit

Accepted main: `a4daa1d07a3ef8f6c00cf2b4a1692053bf99f518`

Classification distinguishes **backend capability** from a **complete learner/instructor workflow**. A schema or API alone is not parity.

Workflow references (Classroom / Canvas / Brightspace / Pearson+) were used only as job-to-be-done lists. No competitor branding, assets, APIs, or trade dress were copied.

## Learner

| Capability | Status | Backend vs workflow |
|---|---|---|
| Today/home | HAVE | New Today surface over existing home/assignment APIs |
| Continue learning | HAVE | Persisted active course + last lesson |
| Course list | HAVE | All authorized sections; no `list[0]` |
| Course overview | HAVE | Course home tabs |
| Modules/units | PARTIAL | Honest statuses from recorded state only |
| Lesson rendering | HAVE | Safe Markdown, not raw `<pre>` |
| Files/resources | PARTIAL | Pack lessons/files; no invented library |
| Assignments | HAVE | Assignment Center + explicit open |
| Submission/resubmission | HAVE | Existing assessment lifecycle |
| Quizzes | PARTIAL | Activity engine exists; mock hub has no quizzes |
| Labs | PARTIAL | Existing lab flow, launched from Study when present |
| Discussions | PARTIAL | Activity threads exist; Messages is a thin entry |
| Groups | PARTIAL | Backend only |
| Grades | HAVE | Rows + pending; no fake overall % |
| Feedback | HAVE | Returned comments + deep link |
| Mastery | PARTIAL | Shown only when recorded |
| Remediation | HAVE | Existing plans |
| Calendar | HAVE | Due-date aggregation only |
| To-do | HAVE | Same canonical calendar |
| Announcements | PARTIAL | Publish notes / configured events |
| Notifications | HAVE | Event-backed, deep-linked |
| Search | HAVE | Authorized catalog; answer keys denied |
| Study tools | HAVE | Honest mode availability |
| AI tutor | HAVE | Existing gunnchAI policy |
| Portfolio | PARTIAL | Existing evidence list |
| Offline | HAVE | Existing queue + learner-facing truth |
| Mobile | HAVE | 4–5 actions + More |
| Accessibility | PARTIAL | Automated checks only |

## Instructor

| Capability | Status | Backend vs workflow |
|---|---|---|
| Create/copy course | HAVE | Copies section metadata; same package_id |
| Template/blueprint | PARTIAL | Template = existing canonical section |
| Due-date shift | HAVE | Preview then commit |
| Assignments | HAVE | Existing |
| Rubrics | HAVE | Existing |
| Question banks | PARTIAL | Backend/QTI foundation |
| Grade queue | HAVE | Next ungraded + save/next |
| Comment bank | HAVE | Instructor-owned snippets |
| Bulk grading | PARTIAL | Save/next, not bulk blast |
| Accommodations | PARTIAL | Existing activity accommodations |
| Regrade | PARTIAL | Existing regrade queue |
| Roster | HAVE | Existing |
| Analytics | PARTIAL | Dashboard metrics only |
| Announcements | PARTIAL | Publish notes |
| Intervention | HAVE | Missing/low mastery/revision; waiting-to-grade excluded |
| Publish/unpublish | PARTIAL | Existing published flag |

## Admin / institution

| Capability | Status | Notes |
|---|---|---|
| Sites / terms / users / roles / enrollment | HAVE | Existing identity |
| Audit | HAVE | Existing audit log |
| Backup/restore | HAVE | Existing |
| OneRoster / QTI / LTI | PARTIAL | Honest not-certified claims preserved |
| SSO seam | PARTIAL | Session auth only |
| Import/export | PARTIAL | Package + OneRoster import status |
| Accessibility audit | PARTIAL | Automated only |
| Policy/config | HAVE | Privacy + AI policy |
| Observability | HAVE | Diagnostics |
| School Apps | HAVE | Institution-configured URLs/LTI only |

## Better than reference

- Signed learner packs and offline receipt honesty
- gunnchAI grading-safety / no answer-key leakage
- Canonical 18-track import without duplicating curriculum SoT

## Not in scope

- 3k MLV as a second gradebook
- Competitor LMS impersonation or scraping
- Invented academic content to force 18/18 READY
- WCAG or human certification from automation
