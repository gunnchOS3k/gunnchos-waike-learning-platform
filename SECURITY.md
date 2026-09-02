# Security Policy

## Supported versions

PR 1 is a foundation slice. Do not treat unsigned or unverified packages as trusted.

## Reporting

Report suspected vulnerabilities privately to the repository maintainers. Do not open public issues that include exploit details for live systems.

## PR 1 boundaries

- No production signing keys in this repository.
- Test-only keys are clearly marked `TEST_ONLY` under `contracts/fixtures/keys/`.
- No live learner authentication, grades, submissions, or pilot PII in PR 1.
- Learner packages must never contain instructor solutions or decryption secrets.
- Package verification must succeed before content is trusted by the client.

See `docs/security/THREAT_MODEL.md` and `docs/security/KEY_MANAGEMENT_DEVELOPMENT.md`.
