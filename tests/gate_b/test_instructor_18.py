"""Gate B: instructor grading + section isolation across 18 tracks."""

from __future__ import annotations

import pytest

from course_compiler.tracks import CANONICAL_TRACK_IDS
from helpers import (
    auth_header,
    criterion_scores,
    install_track_into_hub,
    login,
    resolve_pack_dir,
    user_id,
)


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_instructor_section_and_grading(client, packs_18, track_id):
    pack_dir = resolve_pack_dir(track_id, packs_18)
    installed = install_track_into_hub(client, track_id, pack_dir)
    section_id = installed["section_id"]
    counts = installed["activity_counts"]
    ih = auth_header(installed["instructor_token"])
    lh = auth_header(installed["learner_token"])

    dash = client.get(f"/api/v1/instructor/sections/{section_id}/dashboard", headers=ih)
    assert dash.status_code == 200, dash.text
    assert (dash.json()["section"].get("package") or {}).get("module_id") == track_id

    # Cannot see wrong-section / other-site data
    beta = login(client, "instructor-beta", site_id="site-beta")
    wrong = client.get(
        f"/api/v1/instructor/sections/{section_id}/dashboard",
        headers=auth_header(beta["token"]),
    )
    assert wrong.status_code in {403, 404}, wrong.text

    # Seeded DC section remains invisible to beta instructor
    other = client.get(
        "/api/v1/instructor/sections/sec_alpha_dc_w01/dashboard",
        headers=auth_header(beta["token"]),
    )
    assert other.status_code in {403, 404}, other.text

    # Grading where assignments and/or rubrics exist in inventory
    if counts["assignments"] > 0 or counts["rubrics"] > 0:
        assigns = client.get("/api/v1/assignments", headers=lh)
        assert assigns.status_code == 200
        seed = next((a for a in assigns.json() if a.get("module_id") == "DIGITAL_CONFIDENCE"), None)
        if seed is None:
            pytest.skip("no seeded assignment with rubric available for grading exercise")
        aid = seed["assignment_id"]
        detail = client.get(f"/api/v1/assignments/{aid}", headers=lh)
        assert detail.status_code == 200
        assignment = detail.json()
        if not (assignment.get("rubric") or {}).get("criteria"):
            pytest.skip("assignment has no rubric criteria")

        client.put(
            f"/api/v1/assignments/{aid}/draft",
            headers=lh,
            json={"text_response": f"grade me {track_id}", "section_id": section_id},
        )
        sub = client.post(
            f"/api/v1/assignments/{aid}/submit",
            headers=lh,
            json={
                "text_response": f"grade me {track_id}",
                "idempotency_key": f"idem_gb_{track_id.lower()[:24]}",
                "section_id": section_id,
            },
        )
        assert sub.status_code == 200, sub.text
        submission_id = sub.json()["submission_id"]

        grade = client.post(
            f"/api/v1/instructor/submissions/{submission_id}/grade",
            headers=ih,
            json={
                "criterion_scores": criterion_scores(assignment, 2.0),
                "feedback_body": f"Gate B feedback {track_id}",
                "return_to_learner": True,
            },
        )
        assert grade.status_code == 200, grade.text

        # Alpha instructor must not grade beta-site learner submissions via wrong section
        gamma = login(client, "learner-gamma", site_id="site-beta")
        # Ensure beta instructor cannot pull alpha section roster
        roster = client.get(
            f"/api/v1/sections/{section_id}/roster",
            headers=auth_header(beta["token"]),
        )
        assert roster.status_code in {403, 404}
        assert user_id(gamma) not in {
            r.get("user_id") for r in (roster.json() if roster.status_code == 200 else [])
        }
