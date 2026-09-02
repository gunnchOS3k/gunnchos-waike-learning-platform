# PR1 Verification

- Status: 
- Generated: 
- Platform branch: 
- Platform draft PR: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/1
- Pinned WAIKE commit: 
- Taxonomy draft PR: https://github.com/gunnchOS3k/waike-research-ops/pull/56
- Learner package sha256: 
- Instructor blob sha256: 
- Deterministic recompile pair:  /  (MISMATCH)
- Python: 29 passed (includes hub/compiler/compatibility)
- Security negatives: 10 passed
- Rust: 5 passed
- Frontend: 7 passed (vitest)
- WAIKE .venv/bin/python3 -m pytest -q tests services/hub/tests
.............................                                            [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  /Users/gunnchos/dev/waike-learning-os-workspace/gunnchos-waike-learning-platform/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
29 passed, 1 warning in 1.23s
cd apps/client/src-tauri && cargo test

running 5 tests
test keyring_store::tests::decodes_valid_hex ... ok
test db::tests::envelope_roundtrip_restart ... ok
test pack::tests::rejects_tampered_content ... ok
test pack::tests::rejects_unsigned_and_wrong_role ... ok
test pack::tests::install_verify_persist_restart ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.43s


running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s


running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

cd apps/client && (command -v pnpm >/dev/null && pnpm test || npm test)

 RUN  v2.1.9 /Users/gunnchos/dev/waike-learning-os-workspace/gunnchos-waike-learning-platform/apps/client

 ✓ src/App.test.tsx (7 tests) 162ms

 Test Files  1 passed (1)
      Tests  7 passed (7)
   Start at  14:44:37
   Duration  1.02s (transform 57ms, setup 125ms, collect 107ms, tests 162ms, environment 369ms, prepare 39ms): 43 passed
- Native build: NATIVE_BUILD_OK (darwin arm64 .app + .dmg)

## Claim language

digitally implemented and automatically tested for PR 1 scope

## Not claimed

Full LMS, all-course migration, student validation, production security review, accessibility certification, device-quartet field proof, field pilot.
