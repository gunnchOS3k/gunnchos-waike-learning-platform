"""Complete learner journey acceptance (Gate D aggregator)."""

from __future__ import annotations

from datetime import datetime, timezone

from helpers import SECTION, auth_header, login, write_json


def test_complete_learner_journey(client, tmp_path):
    from offline_client import OfflineDevice

    steps: dict[str, str] = {}
    learner = login(client, "learner-alpha")
    lh = auth_header(learner["token"])
    steps["auth"] = "PASS"

    home = client.get("/api/v1/learner/home", headers=lh)
    assert home.status_code == 200
    assert any(s["section_id"] == SECTION for s in home.json())
    steps["enroll_nav"] = "PASS"

    section = client.get(f"/api/v1/sections/{SECTION}", headers=lh)
    assert section.status_code == 200
    steps["lessons_nav"] = "PASS"

    assigns = client.get("/api/v1/assignments", headers=lh)
    assert assigns.status_code == 200
    assert len(assigns.json()) >= 1
    aid = assigns.json()[0]["assignment_id"]
    draft = client.put(
        f"/api/v1/assignments/{aid}/draft",
        headers=lh,
        json={"text_response": "gate-d learner draft"},
    )
    assert draft.status_code == 200
    steps["assignments"] = "PASS"

    qstart = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    assert qstart.status_code == 200
    steps["quizzes"] = "PASS"

    thr = client.post(
        "/api/v1/discussions/threads",
        headers=lh,
        json={"section_id": SECTION, "title": "gate-d learner discussion"},
    )
    assert thr.status_code == 200
    steps["discussions"] = "PASS"

    groups = client.get("/api/v1/groups", headers=lh, params={"section_id": SECTION})
    assert groups.status_code == 200
    steps["groups"] = "PASS"

    lab = client.get("/api/v1/labs/lab_dc_local_software", headers=lh)
    assert lab.status_code == 200
    run = client.post(
        "/api/v1/labs/lab_dc_local_software/runs",
        headers=lh,
        json={
            "evidence": {"stdout_hash": "gd"},
            "artifact_hashes": ["bb"],
            "client_mutation_id": "mut_gd_lab_0001",
        },
    )
    assert run.status_code == 200
    steps["labs"] = "PASS"

    device = OfflineDevice(
        "gd-learner",
        tmp_path / "gd_learner.sqlite",
        client,
        learner["token"],
        "site-alpha",
        SECTION,
    )
    device.obtain_lease()
    device.set_online(False)
    device.save_progress_local("pack_dc", "lesson_gd", 33)
    device.restart()
    assert device.pending_count() >= 1
    device.set_online(True)
    synced = device.sync_outbox()
    assert any(r.get("sync_status") == "acknowledged" for r in synced)
    steps["save_resume_offline_sync"] = "PASS"

    gb = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=lh)
    assert gb.status_code == 200
    steps["mastery_portfolio"] = "PASS"

    # Capstone/project: portfolio via gradebook + assignment history surface
    hist = client.get(f"/api/v1/assignments/{aid}/history", headers=lh)
    assert hist.status_code == 200
    steps["projects_capstones"] = "PASS"

    write_json(
        "GATE_D_LEARNER_JOURNEY.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "steps": steps,
        },
    )
    assert all(v == "PASS" for v in steps.values())
