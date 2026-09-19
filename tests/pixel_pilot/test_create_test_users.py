"""Seeding script produces redacted manifest + gitignored credentials."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_create_test_users_seeds_roles_and_18_tracks(tmp_path):
    db = tmp_path / "hub.sqlite3"
    cred = tmp_path / "credentials.json"
    man = tmp_path / "ROLE_TEST_MANIFEST.json"
    inv = tmp_path / "FULL_18_TRACK_RUNTIME_INVENTORY.json"
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT / "services" / "hub")}
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "pixel_pilot" / "create_test_users.py"),
            "--db",
            str(db),
            "--credentials",
            str(cred),
            "--manifest",
            str(man),
            "--inventory",
            str(inv),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = json.loads(man.read_text())
    inventory = json.loads(inv.read_text())
    creds = json.loads(cred.read_text())
    assert manifest["PIXEL_PILOT_ALL_ROLES_SEEDED"] is True
    assert inventory["all_18_loaded"] is True
    assert "password_present" in json.dumps(manifest)
    assert '"password":' not in json.dumps(manifest)
    assert all(u.get("password_present") for u in manifest["users"])
    assert all("password" not in u for u in manifest["users"])
    assert "pixel-learner-alpha" in creds
    assert "password" in creds["pixel-learner-alpha"]
    roles = {u["role"] for u in manifest["users"]}
    assert roles >= {"learner", "instructor", "grader", "guardian", "site_admin"}
