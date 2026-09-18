#!/usr/bin/env python3
"""Seed password-auth Pixel pilot users into a dedicated Hub DB.

Writes secrets only to gitignored .pixel-pilot/credentials.json.
Writes redacted ROLE_TEST_MANIFEST.json under artifacts/pixel6a_waike/.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "hub"))

from app.auth import Role, hash_password  # noqa: E402
from app.db import connect, migrate  # noqa: E402
from app.modules.assessment_lifecycle import _id, _now  # noqa: E402
from app.modules.guardian import GuardianService  # noqa: E402
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


PILOT_USERS = [
    ("px-learner-alpha", "site-alpha", "Learner Alpha Pixel", [Role.LEARNER]),
    ("px-instructor-alpha", "site-alpha", "Instructor Alpha Pixel", [Role.INSTRUCTOR]),
    ("px-grader-alpha", "site-alpha", "Grader Alpha Pixel", [Role.GRADER]),
    ("px-guardian-alpha", "site-alpha", "Guardian Alpha Pixel", [Role.GUARDIAN]),
    ("px-admin-alpha", "site-alpha", "Site Admin Alpha Pixel", [Role.SITE_ADMIN]),
    ("px-learner-beta", "site-beta", "Learner Beta Pixel", [Role.LEARNER]),
    ("px-instructor-beta", "site-beta", "Instructor Beta Pixel", [Role.INSTRUCTOR]),
    ("px-admin-beta", "site-beta", "Site Admin Beta Pixel", [Role.SITE_ADMIN]),
    ("px-guardian-unlinked", "site-alpha", "Guardian Unlinked Pixel", [Role.GUARDIAN]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db",
        default=str(ROOT / ".pixel-pilot" / "hub.sqlite3"),
        help="Pilot DB path (gitignored)",
    )
    ap.add_argument(
        "--credentials",
        default=str(ROOT / ".pixel-pilot" / "credentials.json"),
    )
    ap.add_argument(
        "--manifest",
        default=str(ROOT / "artifacts" / "pixel6a_waike" / "ROLE_TEST_MANIFEST.json"),
    )
    ap.add_argument(
        "--inventory",
        default=str(ROOT / "artifacts" / "pixel6a_waike" / "FULL_18_TRACK_RUNTIME_INVENTORY.json"),
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = connect(db_path)
    migrate(conn)
    now = _now()

    for site_id, name in (("site-alpha", "Alpha Academy"), ("site-beta", "Beta Institute")):
        conn.execute(
            "INSERT OR IGNORE INTO sites(site_id, name, created_at) VALUES (?,?,?)",
            (site_id, name, now),
        )

    credentials: dict[str, dict] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "users": {},
    }
    manifest_users = []

    for username, site_id, display, roles in PILOT_USERS:
        user_id = f"px_{username.replace('-', '_')}"
        password = strong_password()
        identity._upsert_user(user_id, site_id, username, display, roles, password)
        # Force unique password even if upsert skipped hash update on existing rows.
        conn.execute(
            "UPDATE users SET password_hash=?, disabled=0 WHERE user_id=?",
            (hash_password(password), user_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
            (user_id, roles[0].value, display),
        )
        credentials["users"][username] = {
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

    # Wire instructor/grader aliases expected by curriculum seed.
    inventory = seed_full_curriculum(
        conn,
        identity=identity,
        instructor_by_site={
            "site-alpha": "px_px_instructor_alpha",
            "site-beta": "px_px_instructor_beta",
        },
        grader_by_site={"site-alpha": "px_px_grader_alpha"},
    )

    # Enroll learner-alpha in all alpha pilot sections; assign instructor/grader.
    learner_id = credentials["users"]["px-learner-alpha"]["user_id"]
    instructor_id = credentials["users"]["px-instructor-alpha"]["user_id"]
    grader_id = credentials["users"]["px-grader-alpha"]["user_id"]
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

    # Beta learner enrollments for cross-site isolation tests.
    beta_learner = credentials["users"]["px-learner-beta"]["user_id"]
    beta_inst = credentials["users"]["px-instructor-beta"]["user_id"]
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

    guardian = GuardianService(conn)
    # Direct link without site_admin actor bootstrap: insert link row.
    conn.execute(
        """
        INSERT OR IGNORE INTO guardian_links(
          link_id, site_id, guardian_user_id, learner_user_id, active, created_at
        ) VALUES (?,?,?,?,1,?)
        """,
        (
            "glink_px_alpha",
            "site-alpha",
            credentials["users"]["px-guardian-alpha"]["user_id"],
            learner_id,
            now,
        ),
    )
    conn.commit()

    # Fill manifest assignments from DB.
    by_user = {u["username"]: u for u in manifest_users}
    for username, meta in credentials["users"].items():
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

    cred_path = Path(args.credentials)
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    cred_path.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(cred_path, 0o600)
    except OSError:
        pass

    inv_path = Path(args.inventory)
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "generated_at": credentials["generated_at"],
        "PIXEL_PILOT_ALL_ROLES_SEEDED": True,
        "PIXEL_PILOT_ALL_18_TRACKS_LOADED": bool(inventory.get("all_18_loaded")),
        "sites": ["site-alpha", "site-beta"],
        "auth_mode": "password",
        "fixture_headers_primary": False,
        "users": list(by_user.values()),
        "notes": [
            "Passwords live only in .pixel-pilot/credentials.json (gitignored).",
            "Guardian px-guardian-alpha linked to px-learner-alpha; px-guardian-unlinked has no links.",
        ],
    }
    man_path = Path(args.manifest)
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "db": str(db_path),
        "credentials": str(cred_path),
        "manifest": str(man_path),
        "tracks_loaded": inventory.get("loaded_track_ids"),
        "all_18": inventory.get("all_18_loaded"),
        "users": len(manifest_users),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
