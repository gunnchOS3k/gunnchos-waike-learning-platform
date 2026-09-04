"""waike-hub CLI — safe first-admin bootstrap (no default passwords, no synthetic users)."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val is None:
        return None
    val = val.strip()
    return val or None


def _resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    override = os.environ.get("WAIKE_HUB_DB")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "hub.sqlite3"


def cmd_bootstrap_admin(args: argparse.Namespace) -> int:
    """Create only the requested site + site_admin. Never resets existing passwords."""
    site_id = args.site_id or _env("WAIKE_BOOTSTRAP_SITE_ID")
    site_name = args.site_name or _env("WAIKE_BOOTSTRAP_SITE_NAME")
    username = args.username or _env("WAIKE_BOOTSTRAP_ADMIN_USERNAME")
    display_name = args.display_name or _env("WAIKE_BOOTSTRAP_ADMIN_DISPLAY_NAME")
    # Password never accepted via argv (shell history). Env or interactive getpass only.
    password = _env("WAIKE_BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass("Admin password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("error: passwords do not match", file=sys.stderr)
                return 2
        else:
            print(
                "error: set WAIKE_BOOTSTRAP_ADMIN_PASSWORD or run interactively",
                file=sys.stderr,
            )
            return 2

    missing = [
        name
        for name, val in (
            ("site_id / WAIKE_BOOTSTRAP_SITE_ID", site_id),
            ("site_name / WAIKE_BOOTSTRAP_SITE_NAME", site_name),
            ("username / WAIKE_BOOTSTRAP_ADMIN_USERNAME", username),
            ("display_name / WAIKE_BOOTSTRAP_ADMIN_DISPLAY_NAME", display_name),
        )
        if not val
    ]
    if missing:
        print("error: missing " + ", ".join(missing), file=sys.stderr)
        return 2

    from app.db import connect, migrate
    from app.modules.assessment_lifecycle import ServiceError
    from app.modules.identity import IdentityService

    db_path = _resolve_db_path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    migrate(conn)
    identity = IdentityService(conn)
    try:
        result = identity.bootstrap_admin(
            site_id=site_id,  # type: ignore[arg-type]
            site_name=site_name,  # type: ignore[arg-type]
            username=username,  # type: ignore[arg-type]
            display_name=display_name,  # type: ignore[arg-type]
            password=password,
        )
    except ServiceError as e:
        # Never echo the password or bootstrap secret.
        print(f"error: {e.code}", file=sys.stderr)
        return 1
    finally:
        # Clear local reference; env var left to operator to unset.
        password = ""  # noqa: F841

    # Safe summary only — no secrets.
    print(
        f"bootstrap {result['status']} site_id={result['site_id']} "
        f"user_id={result['user_id']} username={result['username']} "
        f"password_reset={result['password_reset']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waike-hub", description="WAIKE Learning Hub operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser(
        "bootstrap-admin",
        help="One-time first site admin (no synthetic users; password via env/getpass only)",
    )
    boot.add_argument("--site-id", default=None)
    boot.add_argument("--site-name", default=None)
    boot.add_argument("--username", default=None)
    boot.add_argument("--display-name", default=None)
    boot.add_argument("--db", default=None, help="SQLite path (or WAIKE_HUB_DB)")
    boot.set_defaults(func=cmd_bootstrap_admin)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
