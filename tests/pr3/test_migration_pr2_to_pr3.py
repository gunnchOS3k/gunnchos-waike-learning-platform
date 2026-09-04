"""PR2→PR3 forward migration: receipt hash / grade / history survive and re-scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
sys.path.insert(0, str(HUB))

from app.db import connect, migrate  # noqa: E402
from app.main import HubConfig, create_app  # noqa: E402
from app.modules.assessment_lifecycle import AssessmentService  # noqa: E402
from app.modules.identity import FIXTURE_PASSWORD, IdentityService  # noqa: E402
from app.modules.sections import SectionService  # noqa: E402
from app.auth import Actor, Role  # noqa: E402


def _waike() -> Path:
    import os

    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    raise FileNotFoundError(f"waike-research-ops missing (tried WAIKE_ROOT, {nested}, {sibling})")


def test_pr2_shaped_db_migrates_preserving_receipts(tmp_path, monkeypatch):
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "migrate.sqlite3"

    # Phase 1: apply only m001+m002 by temporarily truncating MIGRATIONS — simulate PR2 DB
    # by creating app with fixture auth, then verifying m003 can be applied on a copy.
    # Build PR2-era data using assessment with sections=None after m001/m002 only.
    from app import db as dbmod

    original = list(dbmod.MIGRATIONS)
    try:
        dbmod.MIGRATIONS = original[:2]  # PR2 only
        conn = connect(db)
        applied = migrate(conn)
        assert "001_assessment_lifecycle" in applied
        assert "002_receipt_immutability" in applied
        assert "003_identity_sections_gradebook" not in applied

        svc = AssessmentService(conn, waike_root=waike, source_commit="test")
        svc.seed_synthetic_actors()
        assign = svc.seed_digital_confidence_assignment()
        learner = Actor(
            actor_id="learner-a",
            role=Role.LEARNER,
            display_name="Learner A",
            site_id="site-alpha",
            roles=(Role.LEARNER,),
            username="learner-a",
        )
        instructor = Actor(
            actor_id="instructor-1",
            role=Role.INSTRUCTOR,
            display_name="Instructor One",
            site_id="site-alpha",
            roles=(Role.INSTRUCTOR,),
            username="instructor-1",
        )
        sub = svc.submit(
            learner,
            assign["assignment_id"],
            idempotency_key="mig-1",
            text_response="PR2 era submission for migration test body.",
        )
        receipt_hash = sub["receipt"]["content_hash"]
        submission_id = sub["submission_id"]
        detail = svc.get_assignment(assign["assignment_id"])
        scores = [
            {
                "criterion_id": c["criterion_id"],
                "points": 3.0,
                "level_id": next(l["level_id"] for l in c["levels"] if l["score"] == 3),
                "comment": "ok",
            }
            for c in detail["rubric"]["criteria"]
        ]
        graded = svc.grade_submission(
            instructor, submission_id, scores, "Good start", return_to_learner=True
        )
        grade_id = graded["grade"]["grade_id"]
        points = graded["grade"]["points_earned"]
        conn.close()

        # Phase 2: apply remaining migrations (m003)
        dbmod.MIGRATIONS = original
        conn2 = connect(db)
        newly = migrate(conn2)
        assert "003_identity_sections_gradebook" in newly

        # Seed identity mapping + sections on migrated DB
        IdentityService(conn2).seed_sites_and_users()
        SectionService(conn2).seed_digital_confidence_section(source_commit="test")
        # Backfill section_id onto prior submissions
        conn2.execute(
            "UPDATE submissions SET section_id=? WHERE section_id IS NULL",
            ("sec_alpha_dc_w01",),
        )
        conn2.commit()

        row = conn2.execute(
            "SELECT content_hash FROM submission_receipts WHERE submission_id=?",
            (submission_id,),
        ).fetchone()
        assert row["content_hash"] == receipt_hash
        g = conn2.execute("SELECT * FROM grades WHERE grade_id=?", (grade_id,)).fetchone()
        assert float(g["points_earned"]) == float(points)
        # Mapped user exists
        u = conn2.execute("SELECT * FROM users WHERE user_id='learner-a'").fetchone()
        assert u is not None
        assert u["site_id"] == "site-alpha"
        enr = conn2.execute(
            "SELECT * FROM enrollments WHERE user_id='learner-a' AND status='active'"
        ).fetchone()
        assert enr is not None
        conn2.close()

        # Phase 3: boot full PR3 app on migrated DB without reseed wipe
        app = create_app(
            HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
            db_path=db,
            seed=True,
        )
        client = TestClient(app)
        # Login as migrated learner-a
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "learner-a", "password": FIXTURE_PASSWORD, "site_id": "site-alpha"},
        )
        assert r.status_code == 200
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        hist = client.get(f"/api/v1/assignments/{assign['assignment_id']}/history", headers=h)
        assert hist.status_code == 200
        assert any(x["submission_id"] == submission_id for x in hist.json())
        got = client.get(f"/api/v1/submissions/{submission_id}", headers=h)
        assert got.status_code == 200
        assert got.json()["receipt"]["content_hash"] == receipt_hash
        assert got.json()["grade"]["grade_id"] == grade_id
    finally:
        dbmod.MIGRATIONS = original
