"""Exact-origin CORS allowlists. Never include wildcard origins."""

from __future__ import annotations

import os

TAURI_ORIGINS: tuple[str, ...] = (
    "http://ipc.localhost",
    "https://ipc.localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
    "null",
)

PIXEL_LOOPBACK_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def extra_pilot_origins() -> tuple[str, ...]:
    """Optional exact origins from WAIKE_PIXEL_PILOT_ORIGINS (comma-separated).

    Rejects wildcards, empty tokens, and credentialed URLs.
    """
    raw = os.environ.get("WAIKE_PIXEL_PILOT_ORIGINS", "")
    out: list[str] = []
    for token in raw.split(","):
        origin = token.strip()
        if not origin:
            continue
        if origin == "*" or "*" in origin:
            raise ValueError("CORS_WILDCARD_FORBIDDEN")
        if origin.lower() in {"null", "file://"}:
            continue
        out.append(origin.rstrip("/"))
    return tuple(out)


def hub_allow_origins() -> list[str]:
    origins = list(TAURI_ORIGINS)
    if _env_truthy("WAIKE_PIXEL_PILOT") or _env_truthy("WAIKE_PIXEL_WEB_CLIENT"):
        origins.extend(PIXEL_LOOPBACK_ORIGINS)
        origins.extend(extra_pilot_origins())
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for o in origins:
        if o in seen:
            continue
        if o == "*":
            raise ValueError("CORS_WILDCARD_FORBIDDEN")
        seen.add(o)
        unique.append(o)
    return unique
