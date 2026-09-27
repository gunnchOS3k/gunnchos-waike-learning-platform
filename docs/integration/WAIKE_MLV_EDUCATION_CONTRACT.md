# WAIKE ↔ 3k MLV education contract v1

WAIKE exposes an authenticated, user-scoped read model and deep links for optional 3k MLV / gunnchOS launchers.

This lane does **not** modify 3k MLV.

## Deep links

- `waike://home`
- `waike://course/<section_id>`
- `waike://module/<module_or_instance_id>`
- `waike://lesson/<lesson_id>`
- `waike://assignment/<assignment_id>`
- `waike://quiz/<quiz_id>`
- `waike://lab/<lab_id>`
- `waike://grades`
- `waike://calendar`
- `waike://study/<content_id>`
- `waike://portfolio`

IDs follow existing hub/section/assignment identifiers.

## Consumer summary

`GET /api/v1/mlv/consumer-summary` returns only the authenticated user's:

- display name
- Continue Learning item
- Due Soon list
- course cards
- recent feedback count
- upcoming calendar count

It never returns answer keys, other learners, tokens, or unrestricted Hub APIs.
