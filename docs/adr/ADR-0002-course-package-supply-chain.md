# ADR-0002: Course package supply chain

## Status

Accepted (PR 1)

## Context

Curriculum lives in WAIKE. The platform must deliver signed, role-separated packages without re-authoring content.

## Decision

- Pin WAIKE revisions in `curriculum/registry/PIN.json`.
- Compile with a deterministic Python tool (`tools/course_compiler`).
- Sign learner packs with Ed25519; encrypt instructor packs with AES-256-GCM.
- Verify signatures and hashes before the client trusts content.

## Consequences

Reproducible builds via `SOURCE_DATE_EPOCH`. Instructor material never ships inside learner packs.
