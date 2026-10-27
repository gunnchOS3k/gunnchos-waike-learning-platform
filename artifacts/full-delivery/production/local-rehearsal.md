# Local HTTPS rehearsal continuation — 2026-10-15

Runtime source:c7d1aefd9a641e99c8cf1746c9d6eef841a3096f. Curriculum snapshot:33a101852f4fefb0eb239bcffa60a65d71102e2c. Previous runtime025e100 reports and screenshots are preserved in `history/025e100/`, and its original ignored `.release` remains intact. The current curriculum checkout has workshop-only changes at18efa764e4db066fb17d597284557195499f93ea; the tested runtime deliberately retains the exact source/tree manifest in this directory. Do not repin or rebuild merely to replay this demonstration.

The temporary Python environment is `/private/tmp/waike-recovery-platform-env`; `recovery-environment.txt` records its versions. If the temporary environment expires, recreate it and install `deploy/production/requirements.lock`, `pytest`, `httpx`, `jsonschema`, `pynacl`. No persistent production environment is implied. The generated `.release/candidates/c7d1aef` contains server-only instructor content and must remain private. The local staging database/key/certificate under `deploy/production/private/local-acceptance/` are ignored. They may be discarded after the local demonstration; they are not customer records or production keys.

From the platform worktree, start the retained release **only when port4194 is free**:

```sh
WAIKE_ENV=production \
WAIKE_FACTORY_MODE=true \
WAIKE_ROOT="$PWD/.release/candidates/c7d1aef/curriculum" \
WAIKE_STATIC_ROOT="$PWD/.release/candidates/c7d1aef/reader" \
WAIKE_HUB_DB="$PWD/deploy/production/private/local-acceptance/data/hub.sqlite3" \
WAIKE_RELEASE_MANIFEST="$PWD/.release/candidates/c7d1aef/runtime-release.json" \
WAIKE_PUBLIC_ORIGIN=https://localhost:4194 \
WAIKE_PRACTICE_SIGNING_KEY_FILE="$PWD/deploy/production/private/local-acceptance/practice.key" \
PYTHONPATH=services/hub \
/private/tmp/waike-recovery-platform-env/bin/uvicorn app.production:create_production_app \
  --factory --host 127.0.0.1 --port 4194 --workers 1 --no-access-log --no-proxy-headers \
  --ssl-keyfile deploy/production/private/local-acceptance/tls.key \
  --ssl-certfile deploy/production/private/local-acceptance/tls.crt
```

The root conversation retains the running execution session and is coordinating teardown after buyer-journey checks; do not launch another process onto the same database. No global TLS verification setting was changed.

Browser check:

```sh
WAIKE_STAGING_URL=https://localhost:4194 \
WAIKE_BROWSER_DEPENDENCY_ROOT=../site \
node deploy/production/browser_acceptance.cjs
```

The dedicated Playwright context allows only the local self-signed certificate for this rehearsal. A real deployment needs trusted TLS and the README release gates. The script checks one selected lazy course, actual fictional file practice and feedback, unsubmitted evidence, quiz, no automatic completion, keyboard activation, automated accessibility, blank institutional login, interrupted course loading/retry, private boundaries and mobile layout. `browser/acceptance.json` is the exact15-check result; four screenshots were visually inspected. It is not a user study, authentic independent outcome or institutional capacity test. A broad-course acceptance suite and simulated assessment actors remain historical engineering tests, not customer proof.

Current evidence checkpoint reports the actual tested runtime source separately from later documentation/browser-harness commits. No push, merge or deployment occurred. Stop the specifically owned rehearsal process after the root buyer checks and owner local preview are finished; leave previous unrelated previews alone.

Current specifically owned server: execution session8303, PID17174. It replaced only the stopped session74477/PID13501. The new immutable build uses a detached clean private source view of curriculum33a1018, leaving canonical18efa and the old snapshot unchanged. The root conversation coordinates the buyer-workshop replay before teardown. The client regression first failed on a delayed file read, then passed with106 total client tests; `workshop-regression/` preserves both outcomes. These are engineering tests, not learner validation.
