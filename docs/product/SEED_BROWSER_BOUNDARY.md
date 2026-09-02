# Seed browser boundary

## What exists today

In `gunnchos-device-os`, `apps/waike_learning` is a first-party **seed browser / lab launcher**. It surfaces accepted WAIKE course IDs with executable seeds (lesson, assignment, lab, packets). Its own README states it is **not a finished 8-week LMS**.

## Why it is not Learning OS

- It does not implement signed package verification, encrypted instructor separation, or encrypted local lesson persistence as the platform system of record.
- Device OS remains authority for packaging, launcher, and device policy — not curriculum runtime LMS features.
- Embedding that HTML surface inside Tauri would not satisfy PR 1 integrity requirements.

## Later integration

Device OS launcher/install/update integration is a **separate later PR** after the platform shell is established. The seed browser may remain as a discovery/lab tool until superseded by Learning OS delivery.
