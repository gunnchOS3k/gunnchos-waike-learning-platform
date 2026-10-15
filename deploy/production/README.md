# Existing WAIKE Hub + reader: Linux release operations

This local release implementation serves the compiled public reader and the **existing** Python Hub from one origin. The gunnchos.com Next.js/OpenNext gateway retains its Cloudflare Worker and points its Campus links to the operator-approved HTTPS reader destination. There is no additional LMS, identity store, gradebook or learner database. The existing SQLite Hub and its blobs persist on one host volume. This is a supported Linux ASGI/container topology, not Python deployed into the gateway Worker.

**Status: locally tested implementation; no production deployment or human educational acceptance.** No Docker daemon, approved Linux host, HTTPS ingress access, production signing key, identity/enrollment authorization or minor-account privacy approval was available in this workstream. Container build/run, actual ingress connectivity and recovery on that host remain release gates. No paid service, domain, DNS, Cloudflare or production configuration was changed.

## Reproducible release input

From a clean platform checkout with its pin matching a clean canonical curriculum checkout, run:

```sh
python3 deploy/production/prepare_release.py --curriculum-root ../curriculum
```

The script refuses dirty/mismatched sources, regenerates the non-authoring course split, builds with same-origin Hub and public anonymous reading enabled, exports the exact Git curriculum tree into `.release/`, and records platform/curriculum SHAs plus tree hashes in `.release/runtime-release.json`. It never deploys. This directory contains **private server-only instructor material**, is ignored in Git, and must never be uploaded as a public download or static directory. Only `.release/reader` is served. The image is therefore a restricted server artifact; authorize its registry audience separately.

On the approved Linux builder, resolve and record `python:3.14-slim` to an immutable digest, scan that base plus requirements.lock, and build `deploy/production/Dockerfile` from the repository root. Pin the resulting immutable image digest in `WAIKE_RELEASE_IMAGE`. The lock records versions exercised locally; Linux wheel resolution, vulnerability scanning and container runtime checks remain pending. Do not substitute a moving tag for the reviewed release digest.

## First start without demonstration accounts

1. Supply an existing approved Linux host and HTTPS ingress for the exact reader origin (for example the existing approved learn destination). No account or provider provisioning is included.
2. Create an empty protected persistent data directory owned by UID/GID 10001. Keep protected backups on a different encrypted volume. The production image is read-only, non-root, cap-drop ALL, no-new-privileges, with bounded CPU/memory/PIDs and a 64-MiB temporary filesystem.
3. Run the image's `python deploy/production/operations.py migrate --data-dir /var/lib/waike` as a one-off container with that persistent volume. This initializes the canonical nine migrations. For an existing database, `--snapshot /backups/pre-upgrade.zip` is mandatory; migration is rehearsed against the exact snapshot before the stopped database is changed. Mount `/backups` separately and protect it. No users are seeded.
4. Supply a random operator-owned secret file (32–512 characters) as `WAIKE_PRACTICE_KEY_PATH`, never commit or pass its contents in a command argument. Preserve the key across a normal restart; rotating it invalidates outstanding practical tokens.
5. Set `WAIKE_PUBLIC_ORIGIN`, `WAIKE_RELEASE_IMAGE`, `WAIKE_DATA_DIRECTORY`, `WAIKE_PRACTICE_KEY_PATH` in protected host configuration and review `docker compose -f deploy/production/compose.yaml config` without publishing expanded secret paths. Start only after release approval and image/runtime gates pass. The service is bound to loopback8080; the existing approved HTTPS ingress must route **the entire reader origin** to it, preserving Host. Do not use a static-only origin with missing API routes.
6. Configure ingress TLS, trusted Host, HSTS, request timeout ≤15s, request body ≤2MiB, rate/concurrency limits and privacy-safe error monitoring. This process does not trust forwarded headers. Its bounded per-peer limiter is a coarse additional defense: 10 login requests or120 API requests/minute per actual TCP peer, with 4,096 bounded buckets and Retry-After. Behind a proxy, these are shared proxy budgets; apply appropriate real-client distributed limits at the ingress and capacity-test them. No distributed rate-limit guarantee is claimed.
7. Verify `/readyz` returns the exact approved source SHAs and `seeded_test_fixtures:false`. Root HTML and one course must load, quiz/case POSTs must reach this same origin, private endpoints must require authorization, and source/instructor/blob paths must return404. Verify real public URLs after the governed release, not just a successful process start.

Production explicitly rejects fixture authentication, fixture seeding, Pixel pilot startup and fake-AI flags, including combinations previously capable of seeding production. A direct Hub `seed=True` is forbidden in production. Production requires the explicit migrated database and exact source/reader tree hashes. The factory opens one Hub, holds an exclusive maintenance lock and uses one Uvicorn worker; do not horizontally replicate this SQLite deployment or override workers. Its single SQLite connection and rate limiting need a separate reviewed design before multi-process scaling.

## Identity and privacy

Anonymous study/practice does not create accounts. The public reader includes a deliberate sign-in entry point for an existing institution/site identity; official submissions and grades continue through the existing bearer-session services and enrollment checks. A production first administrator can be created using the existing `waike-hub bootstrap-admin` CLI with an interactive password or protected environment, never argv or default credentials. Do not bootstrap a sample school or real minor accounts without institutional, legal and guardian decisions. Ongoing user enrollment is a human institutional operation, not something a static course import authorizes.

Cross-origin API requests with an Origin header are rejected. Production strips the desktop/opaque-origin CORS middleware for this browser deployment; native clients need their separately reviewed deployment. Bearer authorization still protects API mutations without an Origin header. This boundary does not weaken server enrollment/role checks. API responses are no-store; CSP forbids remote scripts and framing, object embedding and cross-origin API connections. Existing external fonts may be unavailable offline; system fallbacks remain. Access logs are disabled to avoid URLs carrying identifiers; approved monitoring must avoid passwords, tokens, request bodies and learner artifacts.

No arbitrary learner programs run on this server. Existing lab execution accepts data for a repo-controlled fixture; that is process confinement, not proof of an OS sandbox. Programming practice uses the canonical downloadable local Python workflow. Container resource caps are defense in depth and do not authorize unrestricted remote code execution.

## Stop, backup, recovery and rollback

Stop the exact service before maintenance; keep the old immutable image and its `.release` manifest. The running factory owns `.hub.lock`; backup/migration refuse the same directory while that lock is held. Never copy a live SQLite file or use the site-scoped in-app archive as a full-host disaster snapshot.

```sh
python deploy/production/operations.py backup --data-dir /var/lib/waike --snapshot /backups/pre-release.zip
python deploy/production/operations.py verify --data-dir /var/lib/waike
python deploy/production/operations.py restore --data-dir /restore/new-data --snapshot /backups/pre-release.zip
```

The host snapshot uses SQLite's backup API, checks DB integrity/foreign keys, records migration versions, and hashes the full database plus every stored blob. Private snapshots are mode0600; transfer through authorized encrypted backup storage. Restore verifies all members before writing and only accepts a new empty destination. It rejects path traversal, extra/missing members and tampering. It does **not** overwrite an active volume or an existing directory. These archives are privileged operator inputs, not learner uploads; protect authenticity/access in the backup system as well as checking hashes.

For a failed release, stop it. Reconfigure the approved deployment to the retained prior image digest. If a schema/content change is incompatible, restore the matching pre-upgrade snapshot into a **new** persistent directory, review integrity and versions, then deliberately point the stopped service at that directory. Restart and verify readiness/login/submission history and blob retrieval against the prior source manifest. Do not downgrade a migrated database in place. A rollback loses changes made after its snapshot unless reconciled through an authorized recovery process; record that decision. Practice token content hashes can invalidate old cases; installed independent rubrics must use the existing explicit assessment-version process rather than overwriting prior rubrics.

The snapshot includes the complete existing database (all sites) and blobs. Back up protected secret material and ingress/identity configuration using the organization's separate secret-recovery process; the application archive deliberately contains no production secret. Test a restore on the actual host before public use and define owner-approved retention/RPO/RTO. Local synthetic recovery tests do not establish an operational recovery objective.

## Local checks and infrastructure limits

`services/hub/tests/test_production_delivery.py` exercises clean startup, prohibited flags, source/tree mismatch, static/private boundaries, Origin/Host denial, body caps, rate limits, mandatory migration, maintenance locking, full DB/blob backup, tamper rejection, new-directory restore and migration rehearsal. Existing real-auth assessment tests remain authoritative. No fixture accounts are added to a real preview.

The client now imports one course chunk on demand. The canonical aggregate export stays a source-bound compiler artifact and is no longer imported into the initial client. Course requests have loading/retry UI; unavailable evaluation awards nothing. This is not native/offline acceptance or a service-worker promise of complete offline delivery. Measure course requests, transferred bytes, mobile layout and interrupted loading in the actual staging origin before release.

Primary runtime references checked for this implementation: [FastAPI Linux containers](https://fastapi.tiangolo.com/deployment/docker/), [Uvicorn settings](https://uvicorn.dev/settings/), [SQLite backup API](https://www.sqlite.org/backup.html). These support the runtime/backup mechanics, not a claim that an actual production host has been provisioned or accepted.
