"""Device A / Device B cross-device continuation."""

from helpers import SECTION, auth_header, login
from offline_client import OfflineDevice


def test_cross_device_progress_draft_grade_pull(client, tmp_path):
    learner = login(client, "learner-alpha")
    instructor = login(client, "instructor-alpha")
    a = OfflineDevice(
        "device-a", tmp_path / "a.sqlite", client, learner["token"], "site-alpha", SECTION
    )
    b = OfflineDevice(
        "device-b", tmp_path / "b.sqlite", client, learner["token"], "site-alpha", SECTION
    )
    a.obtain_lease()
    b.obtain_lease()

    # Device A offline work
    a.set_online(False)
    a.save_progress_local("pack_dc", "lesson_ab", 70.0)
    a.save_draft_local("draft_ab", "work from A")
    a.restart()
    assert a.pending_count() >= 2
    a.set_online(True)
    a.sync_outbox()
    assert a.acknowledged_count() >= 2

    # Device B pulls
    pulled = b.pull()
    assert any(p["lesson_id"] == "lesson_ab" for p in pulled["lesson_progress"])
    assert any(d["draft_key"] == "draft_ab" for d in pulled["draft_versions"])

    # Assignment submission via assessment API (immutable)
    assign = client.get("/api/v1/assignments", headers=auth_header(learner["token"]))
    assert assign.status_code == 200
    assignment_id = assign.json()[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{assignment_id}/submit",
        headers=auth_header(learner["token"]),
        json={
            "text_response": "cross device submission",
            "idempotency_key": "cross-device-sub-1",
            "section_id": SECTION,
        },
    )
    assert sub.status_code == 200, sub.text
    submission_id = sub.json()["submission_id"]

    # Instructor grades
    detail = client.get(
        f"/api/v1/assignments/{assignment_id}", headers=auth_header(instructor["token"])
    ).json()
    criteria = detail["rubric"]["criteria"]
    scores = []
    for c in criteria:
        levels = c.get("levels") or []
        # Pick a level whose score matches points to satisfy LEVEL_POINTS integrity.
        level = levels[-1] if levels else None
        points = float(level["score"]) if level else float(c["max_points"])
        scores.append(
            {
                "criterion_id": c["criterion_id"],
                "points": points,
                "level_id": level["level_id"] if level else None,
                "comment": "good",
            }
        )
    grade = client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=auth_header(instructor["token"]),
        json={"criterion_scores": scores, "feedback_body": "nice work", "return_to_learner": True},
    )
    assert grade.status_code == 200, grade.text

    pulled_b = b.pull()
    assert pulled_b["grades"] or pulled_b["feedback"]
    pulled_a = a.pull()
    assert pulled_a["feedback"] or pulled_a["grades"]
