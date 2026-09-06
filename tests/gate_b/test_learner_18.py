"""Gate B: learner open-track + progress + representative activity flows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from course_compiler.tracks import CANONICAL_TRACK_IDS
from helpers import auth_header, install_track_into_hub, resolve_pack_dir

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "gate_a"))
from offline_client import OfflineDevice  # noqa: E402


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_learner_track_flow(client, packs_18, tmp_path, track_id):
    pack_dir = resolve_pack_dir(track_id, packs_18)
    installed = install_track_into_hub(client, track_id, pack_dir)
    section_id = installed["section_id"]
    counts = installed["activity_counts"]
    lh = auth_header(installed["learner_token"])

    # Open track: section detail + activity listing
    detail = client.get(f"/api/v1/sections/{section_id}", headers=lh)
    assert detail.status_code == 200, detail.text
    assert (detail.json().get("package") or {}).get("module_id") == track_id

    acts = client.get(f"/api/v1/sections/{section_id}/activities", headers=lh)
    assert acts.status_code == 200, acts.text

    # Progress persistence (all installed packs)
    device = OfflineDevice(
        device_id=f"gb-learn-{track_id[:8]}",
        db_path=tmp_path / f"{track_id}.sqlite",
        client=client,
        token=installed["learner_token"],
        site_id="site-alpha",
        section_id=section_id,
    )
    device.obtain_lease()
    lesson_id = f"lesson_{track_id.lower()}_open"
    device.save_progress_local(installed["package_id"], lesson_id, 40.0)
    device.set_online(True)
    results = device.sync_outbox()
    assert any(r.get("sync_status") == "acknowledged" for r in results)
    pull = device.pull()
    assert any(p["lesson_id"] == lesson_id for p in pull["lesson_progress"])

    # Representative flows only when inventory count > 0 (honest for thin tracks)
    if counts["lessons"] > 0:
        # Lesson path already covered by progress sync above
        assert True

    if counts["assignments"] > 0:
        assigns = client.get("/api/v1/assignments", headers=lh)
        assert assigns.status_code == 200
        # Use seeded Digital Confidence assignment as hub lifecycle stand-in when present;
        # do not invent track-specific assignment bodies.
        seed = next((a for a in assigns.json() if a.get("module_id") == "DIGITAL_CONFIDENCE"), None)
        if seed:
            aid = seed["assignment_id"]
            draft = client.put(
                f"/api/v1/assignments/{aid}/draft",
                headers=lh,
                json={"text_response": f"gate-b draft {track_id}", "section_id": section_id},
            )
            assert draft.status_code == 200, draft.text

    if counts["quizzes"] > 0:
        app = client.app
        seeded = app.state.activities.seed_section_activities(
            section_id=section_id,
            site_id="site-alpha",
            instructor_id=installed["instructor_user_id"],
        )
        quiz_id = seeded["quiz_id"]
        start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=lh)
        assert start.status_code == 200, start.text
        attempt_id = start.json()["attempt_id"]
        submit = client.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit",
            headers=lh,
            json={
                "responses": {
                    f"qi_sc_{section_id}": "b",
                    f"qi_ms_{section_id}": ["a", "c"],
                    f"qi_tf_{section_id}": True,
                    f"qi_num_{section_id}": 42,
                    f"qi_short_{section_id}": "digital confidence",
                    f"qi_file_{section_id}": {"f": 1},
                },
                "client_mutation_id": f"mut_gb_quiz_{track_id.lower()[:20]}",
            },
        )
        assert submit.status_code == 200, submit.text

    if counts["labs"] > 0:
        app = client.app
        seeded = app.state.activities.seed_section_activities(
            section_id=section_id,
            site_id="site-alpha",
            instructor_id=installed["instructor_user_id"],
        )
        lab_id = seeded["lab_id"]
        run = client.post(
            f"/api/v1/labs/{lab_id}/runs",
            headers=lh,
            json={
                "evidence": {"stdout_hash": f"gb_{track_id}"},
                "artifact_hashes": ["aa"],
                "client_mutation_id": f"mut_gb_lab_{track_id.lower()[:20]}",
            },
        )
        assert run.status_code == 200, run.text
