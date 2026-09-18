#!/usr/bin/env python3
"""Seed password-auth Pixel pilot users into a dedicated Hub DB.

Writes secrets only to gitignored .pixel-pilot/credentials.json.
Writes redacted ROLE_TEST_MANIFEST.json under artifacts/pixel6a_waike/.

Credential keys match tools/pixel_pilot/run_pixel_pilot.py (pixel-*).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "hub"))

from app.auth import Role, hash_password  # noqa: E402
from app.db import connect, migrate  # noqa: E402
from app.modules.assessment_lifecycle import _id, _now  # noqa: E402
from app.modules.guardian import GuardianService  # noqa: E402
from app.modules.identity import IdentityService  # noqa: E402
from app.pilot.full_curriculum_seed import (  # noqa: E402
    EXPECTED_TRACK_IDS,
    seed_full_curriculum,
)


def strong_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*-_=+" for c in pwd)
        ):
            return pwd


# Keys MUST match run_pixel_pilot.run_role_api_journeys lookups.
PILOT_USERS = [
    ("pixel-learner-alpha", "site-alpha", "Pixel Learner Alpha", [Role.LEARNER]),
    ("pixel-instructor-alpha", "site-alpha", "Pixel Instructor Alpha", [Role.INSTRUCTOR]),
    ("pixel-grader-alpha", "site-alpha", "Pixel Grader Alpha", [Role.GRADER]),
    ("pixel-guardian-alpha", "site-alpha", "Pixel Guardian Alpha", [Role.GUARDIAN]),
    ("pixel-admin-alpha", "site-alpha", "Pixel Site Admin Alpha", [Role.SITE_ADMIN]),
    ("pixel-learner-beta", "site-beta", "Pixel Learner Beta", [Role.LEARNER]),
    ("pixel-instructor-beta", "site-beta", "Pixel Instructor Beta", [Role.INSTRUCTOR]),
    ("pixel-admin-beta", "site-beta", "Pixel Site Admin Beta", [Role.SITE_ADMIN]),
    ("pixel-guardian-unlinked", "site-alpha", "Pixel Guardian Unlinked", [Role.GUARDIAN]),
]


def seed_pilot_users(db_path: Path | str) -> dict[str, Any]:
    """Create pilot DB users + 18-track sections.

    Returns:
      credentials: flat map username -> {username,password,site_id,user_id,roles}
      manifest: redacted role manifest
      inventory: 18-track runtime inventory
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = connect(db_path)
    migrate(conn)
    identity = IdentityService(conn)
    now = _now()

    for site_id, name in (("site-alpha", "Alpha Academy"), ("site-beta", "Beta Institute")):
        conn.execute(
            "INSERT OR IGNORE INTO sites(site_id, name, created_at) VALUES (?,?,?)",
            (site_id, name, now),
        )

    flat_creds: dict[str, dict[str, Any]] = {}
    manifest_users: list[dict[str, Any]] = []
    generated_at = datetime.now(timezone.utc).isoformat()

    for username, site_id, display, roles in PILOT_USERS:
        user_id = username
        password = strong_password()
        identity._upsert_user(user_id, site_id, username, display, roles, password)
        conn.execute(
            "UPDATE users SET password_hash=?, disabled=0 WHERE user_id=?",
            (hash_password(password), user_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
            (user_id, roles[0].value, display),
        )
        flat_creds[username] = {
            "username": username,
            "user_id": user_id,
            "site_id": site_id,
            "roles": [r.value for r in roles],
            "password": password,
        }
        manifest_users.append(
            {
                "username": username,
                "user_id": user_id,
                "role": roles[0].value,
                "site": site_id,
                "password_present": True,
                "section_assignments": [],
                "course_assignments": [],
            }
        )

    inventory = seed_full_curriculum(
        conn,
        identity=identity,
        instructor_by_site={
            "site-alpha": "pixel-instructor-alpha",
            "site-beta": "pixel-instructor-beta",
        },
        grader_by_site={"site-alpha": "pixel-grader-alpha"},
    )

    learner_id = flat_creds["pixel-learner-alpha"]["user_id"]
    instructor_id = flat_creds["pixel-instructor-alpha"]["user_id"]
    grader_id = flat_creds["pixel-grader-alpha"]["user_id"]
    for track_id in EXPECTED_TRACK_IDS:
        section_id = f"sec_alpha_{track_id.lower()}_pilot"
        if not conn.execute("SELECT section_id FROM sections WHERE section_id=?", (section_id,)).fetchone():
            continue
        conn.execute(
            "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, instructor_id, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO section_graders(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, grader_id, now),
        )
        active = conn.execute(
            "SELECT enrollment_id FROM enrollments WHERE section_id=? AND user_id=? AND status='active'",
            (section_id, learner_id),
        ).fetchone()
        if not active:
            conn.execute(
                """
                INSERT INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
                VALUES (?,?,?,'active',?)
                """,
                (_id("enr"), section_id, learner_id, now),
            )

    beta_learner = flat_creds["pixel-learner-beta"]["user_id"]
    beta_inst = flat_creds["pixel-instructor-beta"]["user_id"]
    for track_id in EXPECTED_TRACK_IDS[:3]:
        section_id = f"sec_beta_{track_id.lower()}_pilot"
        if not conn.execute("SELECT section_id FROM sections WHERE section_id=?", (section_id,)).fetchone():
            continue
        conn.execute(
            "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, beta_inst, now),
        )
        active = conn.execute(
            "SELECT enrollment_id FROM enrollments WHERE section_id=? AND user_id=? AND status='active'",
            (section_id, beta_learner),
        ).fetchone()
        if not active:
            conn.execute(
                """
                INSERT INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
                VALUES (?,?,?,'active',?)
                """,
                (_id("enr"), section_id, beta_learner, now),
            )

    _ = GuardianService(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO guardian_links(
          link_id, site_id, guardian_user_id, learner_user_id, active, created_at
        ) VALUES (?,?,?,?,1,?)
        """,
        (
            "glink_px_alpha",
            "site-alpha",
            flat_creds["pixel-guardian-alpha"]["user_id"],
            learner_id,
            now,
        ),
    )
    conn.commit()

    by_user = {u["username"]: u for u in manifest_users}
    for username, meta in flat_creds.items():
        uid = meta["user_id"]
        sections = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.section_id, s.code, s.title, p.module_id
                FROM sections s
                JOIN packages p ON p.package_id = s.package_id
                LEFT JOIN enrollments e ON e.section_id = s.section_id AND e.user_id=? AND e.status='active'
                LEFT JOIN section_instructors si ON si.section_id = s.section_id AND si.user_id=?
                LEFT JOIN section_graders sg ON sg.section_id = s.section_id AND sg.user_id=?
                WHERE e.user_id IS NOT NULL OR si.user_id IS NOT NULL OR sg.user_id IS NOT NULL
                ORDER BY p.module_id
                """,
                (uid, uid, uid),
            ).fetchall()
        ]
        by_user[username]["section_assignments"] = [s["section_id"] for s in sections]
        by_user[username]["course_assignments"] = [s["module_id"] for s in sections]

    manifest = {
        "generated_at": generated_at,
        "PIXEL_PILOT_ALL_ROLES_SEEDED": True,
        "PIXEL_PILOT_ALL_18_TRACKS_LOADED": bool(inventory.get("all_18_loaded")),
        "sites": ["site-alpha", "site-beta"],
        "auth_mode": "password",
        "fixture_headers_primary": False,
        "users": list(by_user.values()),
        "notes": [
            "Passwords live only in .pixel-pilot/credentials.json (gitignored).",
            "Guardian pixel-guardian-alpha linked to pixel-learner-alpha; pixel-guardian-unlinked has no links.",
        ],
    }
    return {
        "credentials": flat_creds,
        "manifest": manifest,
        "inventory": inventory,
        "db_path": str(db_path),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / ".pixel-pilot" / "hub.sqlite3"))
    ap.add_argument("--credentials", default=str(ROOT / ".pixel-pilot" / "credentials.json"))
    ap.add_argument(
        "--manifest",
        default=str(ROOT / "artifacts" / "pixel6a_waike" / "ROLE_TEST_MANIFEST.json"),
    )
    ap.add_argument(
        "--inventory",
        default=str(ROOT / "artifacts" / "pixel6a_waike" / "FULL_18_TRACK_RUNTIME_INVENTORY.json"),
    )
    args = ap.parse_args()

    result = seed_pilot_users(args.db)
    credentials = result["credentials"]
    inventory = result["inventory"]
    manifest = result["manifest"]

    cred_path = Path(args.credentials)
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    # Store flat map for the orchestrator; never commit this file.
    cred_path.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(cred_path, 0o600)
    except OSError:
        pass

    inv_path = Path(args.inventory)
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    man_path = Path(args.manifest)
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "db": str(args.db),
                "credentials": str(cred_path),
                "manifest": str(man_path),
                "tracks_loaded": inventory.get("loaded_track_ids"),
                "all_18": inventory.get("all_18_loaded"),
                "users": len(manifest["users"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
