"""Complete instructor journey acceptance (Gate D aggregator)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gd_helpers import SECTION, auth_header, login, user_id, write_json

OTHER_SECTION = "sec_beta_dc_w01"


def _unrelated_same_site_instructor(client) -> dict:
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    created = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "instructor-unrelated-gd",
            "display_name": "Unrelated GD Instructor",
            "password": "WaikeTestPass1!",
            "roles": ["instructor"],
        },
    )
    assert created.status_code in (200, 201), created.text
    uid = created.json()["user_id"]
    pkg = client.app.state.db.execute("SELECT package_id FROM packages LIMIT 1").fetchone()
    assert pkg is not None
    other = client.post(
        "/api/v1/admin/sections",
        headers=ah,
        json={
            "code": "DC-W99-GD",
            "title": "Unrelated Gate D Section",
            "package_id": pkg["package_id"],
        },
    )
    assert other.status_code in (200, 201), other.text
    client.post(
        f"/api/v1/admin/sections/{other.json()['section_id']}/instructors",
        headers=ah,
        json={"user_id": uid},
    )
    return login(client, "instructor-unrelated-gd", "site-alpha")


def test_complete_instructor_journey(client):
    steps: dict[str, str] = {}
    admin = login(client, "admin-alpha")
    inst = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    lid = user_id(learner)
    ah, ih, lh = auth_header(admin["token"]), auth_header(inst["token"]), auth_header(learner["token"])
    steps["auth_roles"] = "PASS"

    dash = client.get(f"/api/v1/instructor/sections/{SECTION}/dashboard", headers=ih)
    assert dash.status_code == 200
    steps["sections_activity"] = "PASS"

    assigns = client.get("/api/v1/assignments", headers=lh)
    aid = assigns.json()[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=lh,
        json={
            "idempotency_key": "gd-inst-submit-1",
            "text_response": "Gate D instructor journey submission body.",
        },
    )
    assert sub.status_code == 200
    sid = sub.json()["submission_id"]

    queue = client.get(f"/api/v1/instructor/assignments/{aid}/queue", headers=ih)
    assert queue.status_code == 200
    steps["assessment_queue"] = "PASS"

    detail = client.get(f"/api/v1/assignments/{aid}", headers=ih)
    assert detail.status_code == 200
    rubric = detail.json()["rubric"]
    # Grade below mastery threshold so remediation is assigned (lowest rubric levels).
    criterion_scores = [
        {
            "criterion_id": c["criterion_id"],
            "points": c["levels"][-1]["score"],
            "level_id": c["levels"][-1]["level_id"],
            "comment": "gate-d gap feedback",
        }
        for c in rubric["criteria"]
    ]
    grade = client.post(
        f"/api/v1/instructor/submissions/{sid}/grade",
        headers=ih,
        json={
            "criterion_scores": criterion_scores,
            "feedback_body": "needs remediation",
            "return_to_learner": True,
        },
    )
    assert grade.status_code == 200, grade.text
    grade_body = grade.json()
    assert grade_body.get("mastery") is not None
    assert grade_body["mastery"].get("mastered") in (0, False)
    assert grade_body.get("remediation") is not None
    assert grade_body["remediation"].get("status") == "assigned"
    steps["grading_rubrics_feedback"] = "PASS"

    gb = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih)
    assert gb.status_code == 200
    steps["gradebook"] = "PASS"

    # F2 — mastery/remediation REQUIRED (never 404 soft-pass).
    mastery = client.get(
        f"/api/v1/assignments/{aid}/mastery",
        headers=ih,
        params={"learner_id": lid},
    )
    assert mastery.status_code == 200, mastery.text
    mastery_body = mastery.json()
    assert mastery_body.get("mastery_id") or mastery_body.get("learner_id")
    assert "mastered" in mastery_body
    rem_learner = client.get("/api/v1/remediation", headers=lh)
    assert rem_learner.status_code == 200, rem_learner.text
    rem_rows = rem_learner.json()
    assert any(r.get("assignment_id") == aid for r in rem_rows), rem_rows
    rem_inst = client.get("/api/v1/remediation", headers=ih)
    assert rem_inst.status_code == 200
    assert any(r.get("assignment_id") == aid and r.get("learner_id") == lid for r in rem_inst.json())
    steps["mastery_remediation"] = "PASS"

    thr = client.post(
        "/api/v1/discussions/threads",
        headers=ih,
        json={"section_id": SECTION, "title": "gate-d instructor thread"},
    )
    assert thr.status_code == 200
    steps["discussion_group"] = "PASS"

    # F1 — accommodations REQUIRED real workflow (create/update, denials, effect, read-back).
    gb_json = gb.json()
    if isinstance(gb_json, list):
        gb_rows = gb_json
    elif isinstance(gb_json, dict):
        gb_rows = gb_json.get("rows") or gb_json.get("learners") or gb_json.get("entries") or []
    else:
        gb_rows = []
    gb_learners = {
        row.get("learner_id") or row.get("user_id")
        for row in gb_rows
        if isinstance(row, dict)
    }

    create = client.post(
        "/api/v1/accommodations",
        headers=ih,
        json={
            "learner_id": lid,
            "section_id": SECTION,
            "attempt_override": 5,
            "time_multiplier": 1.5,
            "due_extension_minutes": 30,
            "notes_private": "Gate D IEP confidential",
        },
    )
    assert create.status_code == 200, create.text
    assert create.json().get("attempt_override") == 5
    assert create.json().get("time_multiplier") == 1.5
    assert create.json().get("due_extension_minutes") == 30

    listed = client.get(f"/api/v1/accommodations/{lid}", headers=ih, params={"section_id": SECTION})
    assert listed.status_code == 200, listed.text
    assert listed.json().get("attempt_override") == 5
    assert listed.json().get("time_multiplier") == 1.5
    assert listed.json().get("due_extension_minutes") == 30

    update = client.post(
        "/api/v1/accommodations",
        headers=ih,
        json={
            "learner_id": lid,
            "section_id": SECTION,
            "attempt_override": 6,
            "time_multiplier": 2.0,
            "due_extension_minutes": 45,
            "notes_private": "Gate D IEP confidential updated",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json().get("attempt_override") == 6
    assert update.json().get("time_multiplier") == 2.0
    assert update.json().get("due_extension_minutes") == 45

    unrelated = _unrelated_same_site_instructor(client)
    deny_unassigned = client.post(
        "/api/v1/accommodations",
        headers=auth_header(unrelated["token"]),
        json={"learner_id": lid, "section_id": SECTION, "attempt_override": 9},
    )
    assert deny_unassigned.status_code == 403, deny_unassigned.text

    cross = login(client, "instructor-beta")
    deny_cross = client.post(
        "/api/v1/accommodations",
        headers=auth_header(cross["token"]),
        json={"learner_id": lid, "section_id": SECTION, "attempt_override": 9},
    )
    assert deny_cross.status_code in (403, 404), deny_cross.text

    deny_learner = client.post(
        "/api/v1/accommodations",
        headers=lh,
        json={"learner_id": lid, "section_id": SECTION, "attempt_override": 9},
    )
    assert deny_learner.status_code == 403, deny_learner.text

    gamma = login(client, "learner-gamma")
    deny_unenrolled = client.post(
        "/api/v1/accommodations",
        headers=ih,
        json={
            "learner_id": user_id(gamma),
            "section_id": SECTION,
            "attempt_override": 9,
        },
    )
    assert deny_unenrolled.status_code in (403, 404), deny_unenrolled.text

    deny_wrong_section = client.post(
        "/api/v1/accommodations",
        headers=ih,
        json={
            "learner_id": lid,
            "section_id": OTHER_SECTION,
            "attempt_override": 9,
        },
    )
    assert deny_wrong_section.status_code in (403, 404), deny_wrong_section.text

    # Persist + read-back after "reload" (fresh GET) — include due + time fields.
    reread = client.get(f"/api/v1/accommodations/{lid}", headers=ih, params={"section_id": SECTION})
    assert reread.status_code == 200
    assert reread.json().get("attempt_override") == 6
    assert reread.json().get("time_multiplier") == 2.0
    assert reread.json().get("due_extension_minutes") == 45

    # Product effect — time/due: control vs accommodated timed attempt.
    # Base quiz time_limit=30; multiplier 2.0 → 60; due_extension +45 → 105.
    control = login(client, "learner-beta")
    ctrl = client.post(
        "/api/v1/quizzes/quiz_dc_w01_gate_a/attempts",
        headers=auth_header(control["token"]),
    )
    assert ctrl.status_code == 200, ctrl.text
    assert float(ctrl.json()["time_limit_minutes"]) == 30.0

    def _parse_ts(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    ctrl_span = _parse_ts(ctrl.json()["deadline_at"]) - _parse_ts(ctrl.json()["started_at"])
    assert abs(ctrl_span - timedelta(minutes=30)) < timedelta(seconds=90)

    timed = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    assert timed.status_code == 200, timed.text
    assert float(timed.json()["time_limit_minutes"]) == 105.0
    acc_span = _parse_ts(timed.json()["deadline_at"]) - _parse_ts(timed.json()["started_at"])
    assert abs(acc_span - timedelta(minutes=105)) < timedelta(seconds=90)
    # Close the timed attempt so attempt_override proof can continue cleanly.
    client.post(
        f"/api/v1/quiz-attempts/{timed.json()['attempt_id']}/submit",
        headers=lh,
        json={"responses": {}, "client_mutation_id": "mut_gd_acc_time_01_xxxx"},
    )

    # Product effect — attempt_override allows more than default (2) quiz attempts.
    for i in range(3):
        start = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
        assert start.status_code == 200, start.text
        client.post(
            f"/api/v1/quiz-attempts/{start.json()['attempt_id']}/submit",
            headers=lh,
            json={"responses": {}, "client_mutation_id": f"mut_gd_acc_quiz_{i:02d}_xxxx"},
        )

    steps["accommodations"] = "PASS"

    users = client.get("/api/v1/admin/users", headers=ah)
    assert users.status_code == 200
    steps["admin_operator"] = "PASS"

    assert all(v == "PASS" for v in steps.values()), steps
    assert steps["accommodations"] == "PASS"
    assert steps["mastery_remediation"] == "PASS"

    write_json(
        "GATE_D_INSTRUCTOR_JOURNEY.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "steps": steps,
            "accommodations_effect": {
                "attempt_override": True,
                "time_multiplier": True,
                "due_extension_minutes": True,
                "control_time_limit_minutes": 30.0,
                "accommodated_time_limit_minutes": 105.0,
                "formula": "base_30 * time_multiplier_2.0 + due_extension_45",
            },
            "mastery_observable": True,
            "remediation_observable": True,
            "gradebook_learner_ids_sampled": sorted(x for x in gb_learners if x)[:8],
        },
    )
