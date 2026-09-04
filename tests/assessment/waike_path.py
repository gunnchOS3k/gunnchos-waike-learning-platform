from __future__ import annotations

import os
from pathlib import Path


def resolve_waike_root(platform_root: Path | None = None) -> Path:
    """Resolve WAIKE SoT for local workspace (sibling) or CI (nested checkout)."""
    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    root = platform_root or Path(__file__).resolve().parents[2]
    nested = root / "waike-research-ops"
    if nested.is_dir():
        return nested
    sibling = root.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    raise FileNotFoundError(
        f"waike-research-ops not found (tried WAIKE_ROOT, {nested}, {sibling})"
    )
