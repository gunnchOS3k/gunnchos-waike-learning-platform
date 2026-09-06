# Gate A Sync Matrix

- Offline leases: user/site/section scoped with expiry + revocation
- Mutation model: client_mutation_id, actor, site, section, entity, base revision, operation, payload hash, statuses
- Durable sync receipts; client persists ack before clearing pending
- Conflict: drafts preserve versions; submissions immutable; grades/roles/enrollment server-authoritative
- Cross-device Device A/B E2E covered
- Blob sync: hashes, MIME, size, path traversal defense, quarantine
- UX: never show synced before durable ack
