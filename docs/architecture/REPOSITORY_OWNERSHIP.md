# Repository ownership

| Concern | Authority |
|---------|-----------|
| Curriculum content, taxonomy, outcomes, rubrics, provenance | `waike-research-ops` |
| Native client, contracts, compiler, hub, pilot runtime | `gunnchos-waike-learning-platform` (this repo) |
| Device packaging, launcher, fleet policy, offline device behavior | `gunnchos-device-os` |

This platform pins a WAIKE commit in `curriculum/registry/PIN.json` and imports modules. It must not become a second authoring source for lessons or track IDs.

## Seed browser note

`gunnchos-device-os/apps/waike_learning` is a Device OS **seed browser / lab launcher**, not the Learning OS LMS. See `docs/product/SEED_BROWSER_BOUNDARY.md`.
