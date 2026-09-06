#!/usr/bin/env python3
"""Run a seeded hub over real HTTP so the client can be tested against it.

This is a test harness, not a deployment entrypoint: it binds loopback only and
requires an explicit temp database path. Production auth stays on; fixture header
auth stays off, so the client must use real login sessions.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "services" / "hub"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))


def _waike_root() -> Path:
    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    raise FileNotFoundError("waike-research-ops not found; set WAIKE_ROOT")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", required=True, help="path to a throwaway sqlite file")
    args = ap.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("refusing to bind a non-loopback host", file=sys.stderr)
        return 2

    os.environ.setdefault("WAIKE_ROOT", str(_waike_root()))
    import uvicorn

    from app.main import HubConfig, create_app

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    app = create_app(
        HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
        db_path=db,
        seed=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
