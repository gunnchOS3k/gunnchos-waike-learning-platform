# Gate D Adversarial Final Review

Generated: 2026-09-07T02:30:11Z

## Hunt checklist
- soft-fail assert tautologies across Gate D + prior-regression suites
- PASS_OPTIONAL / startswith(PASS) / 200|404 required-scope soft paths
- journeys_ok file-existence-only / hardcoded clean-room false
- behavioral sabotage: accommodations denials, mastery absence, PASS_OPTIONAL verifier fail

## Behavioral cases executed
- `accommodations_wrong_role_learner` → `{'case': 'accommodations_wrong_role_learner', 'status_code': 403}`
- `accommodations_wrong_section` → `{'case': 'accommodations_wrong_section', 'status_code': 403}`
- `instructor_pass_optional` → `{'case': 'instructor_pass_optional', 'ok_expected_false': True, 'ok': False, 'details': [{'scope': 'instructor_journey', 'field': 'steps.accommodations', 'observed': 'PASS_OPTIONAL', 'required': 'PASS'}, {'scope': 'instructor_journey', 'field': 'steps.accommodations_rejected_token', 'observed': 'PASS_OPTIONAL', 'required': 'PASS'}, {'scope': 'instructor_journey', 'field': 'steps.accommodations_startswith_pass', 'observed': 'PASS_OPTIONAL', 'required': 'PASS'}]}`
- `missing_mastery_remediation_step` → `{'case': 'missing_mastery_remediation_step', 'ok': False, 'details': [{'scope': 'instructor_journey', 'field': 'steps.mastery_remediation', 'observed': None, 'required': 'PASS'}]}`
- `learner_step_fail` → `{'case': 'learner_step_fail', 'ok': False, 'details': [{'scope': 'learner_journey', 'field': 'steps.labs', 'observed': 'FAIL', 'required': 'PASS'}, {'scope': 'learner_journey', 'field': 'steps.labs_rejected_token', 'observed': 'FAIL', 'required': 'PASS'}]}`
- `role_matrix_missing_guardian` → `{'case': 'role_matrix_missing_guardian', 'ok': False, 'details': [{'scope': 'role_matrix', 'field': 'roles.guardian', 'observed': None, 'required': 'dict'}]}`
- `mastery_absence` → `{'case': 'mastery_absence', 'ok': False, 'details': [{'scope': 'instructor_journey', 'field': 'steps.mastery_remediation', 'observed': None, 'required': 'PASS'}]}`

## Findings: 0
- none — digital falsification pass clean
