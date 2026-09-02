# Seed browser relationship

## What the device-os seed browser is

`gunnchos-device-os/apps/waike_learning` is a **first-party HTML/JS seed browser** used to exercise course IDs and launch lab scripts on the device OS surface. It is not the Learning OS product.

## What this repository is

`gunnchos-waike-learning-platform` is the **native Learning OS client + package supply chain**: signed learner packs, encrypted instructor packs, encrypted local progress, and a modular-monolith school hub.

## Relationship rules (PR 1)

1. Visual cues (palette, IBM Plex / Source Sans feel, course list + lesson pane) may inform the Learning OS shell.
2. The seed browser HTML/JS must **not** be embedded or copied as the product UI.
3. Curriculum truth remains pinned from `waike-research-ops`; the seed browser does not own contracts.
4. HUMAN_E6 / STUDENT_VALIDATED claims from the seed browser remain out of scope for PR 1.

Observed device-os SHA at PR 1 blueprint time: `28562a8456207540c205a1c8a6434a491b0a4771`.
