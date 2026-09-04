# PR3 role capability matrix (ALLOW/DENY) — backed by tests/pr3/*

| Capability | learner | instructor | grader | site_admin | cross-site peer | Test |
|---|---|---|---|---|---|---|
| Login with password | ALLOW | ALLOW | ALLOW | ALLOW | N/A | test_auth_security |
| Fixture headers in production | DENY | DENY | DENY | DENY | DENY | test_fixture_headers_rejected_in_production |
| Role spoof via header | DENY | DENY | DENY | DENY | DENY | test_role_spoof_rejected |
| Read own submission | ALLOW | ALLOW* | ALLOW* | ALLOW* | DENY | test_authorization / e2e |
| Read peer submission | DENY | ALLOW (same site/section) | ALLOW (same site/section) | ALLOW (same site) | DENY | test_learner_cannot_access_other_learner_submission |
| Instructor queue | DENY | ALLOW | ALLOW | ALLOW | DENY | test_learner_cannot_instructor_queue |
| Grade submission | DENY | ALLOW | ALLOW | ALLOW | DENY | test_beta_instructor_cannot_grade_alpha_submission |
| Gradebook matrix | own scores | ALLOW | ALLOW | ALLOW | DENY | test_gradebook_matrix_and_learner_view |
| Roster | DENY | ALLOW | DENY† | ALLOW | DENY | test_cross_site_roster / e2e |
| Create user / enroll | DENY | DENY | DENY | ALLOW (same site) | DENY | test_multi_user_e2e / admin APIs |
| Duplicate active enrollment | DENY | DENY | DENY | DENY (409) | N/A | test_duplicate_active_enrollment_rejected |
| Disable user | DENY | DENY | DENY | ALLOW | DENY | test_disabled_user_rejected |

\* Instructor-side may read submissions in assigned sections only.  
† Graders can queue/grade; roster requires instructor or site_admin.
