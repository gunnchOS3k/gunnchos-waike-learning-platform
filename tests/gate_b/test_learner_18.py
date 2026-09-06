"""Gate B: learner open-track + progress + per-track packaged activity flows."""

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
    registered = installed["registered_activities"] or {}
    lh = auth_header(installed["learner_token"])
    activity_status = dict(registered.get("status") or {})

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

    if counts["lessons"] == 0:
        assert activity_status.get("lessons") == "NOT_APPLICABLE"
    else:
        assert activity_status.get("lessons") == "REGISTERED"
        assert (registered.get("lesson") or {}).get("module_id") == track_id

    if counts["assignments"] == 0:
        assert activity_status.get("assignments") == "NOT_APPLICABLE"
        assert registered.get("assignment") is None
    else:
        assign_meta = registered["assignment"]
        assert assign_meta["module_id"] == track_id
        aid = assign_meta["assignment_id"]
        detail_a = client.get(f"/api/v1/assignments/{aid}", headers=lh)
        assert detail_a.status_code == 200, detail_a.text
        assert detail_a.json()["module_id"] == track_id
        draft = client.put(
            f"/api/v1/assignments/{aid}/draft",
            headers=lh,
            json={"text_response": f"gate-b draft {track_id}", "section_id": section_id},
        )
        assert draft.status_code == 200, draft.text

    if counts["quizzes"] == 0:
        assert activity_status.get("quizzes") == "NOT_APPLICABLE"
        assert registered.get("quiz") is None
        # Must not fall back to Gate A DIGITAL_CONFIDENCE seed quiz.
        quiz_ids = [q["quiz_id"] for q in acts.json().get("quizzes") or []]
        assert not any(qid.startswith("quiz_dc_w01") for qid in quiz_ids)
    else:
        quiz_meta = registered["quiz"]
        assert quiz_meta["module_id"] == track_id
        quiz_id = quiz_meta["quiz_id"]
        start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=lh)
        assert start.status_code == 200, start.text
        attempt_id = start.json()["attempt_id"]
        responses = quiz_meta.get("correct_responses") or {}
        submit = client.post(
            f"/api/v1/quiz-attempts/{attempt_id}/submit",
            headers=lh,
            json={
                "responses": responses,
                "client_mutation_id": f"mut_gb_quiz_{track_id.lower()[:20]}",
            },
        )
        assert submit.status_code == 200, submit.text

    if counts["labs"] == 0:
        assert activity_status.get("labs") == "NOT_APPLICABLE"
        assert registered.get("lab") is None
        lab_ids = [lab["lab_id"] for lab in acts.json().get("labs") or []]
        assert not any(lid.startswith("lab_dc_local_software") for lid in lab_ids)
    else:
        lab_meta = registered["lab"]
        assert lab_meta["module_id"] == track_id
        lab_id = lab_meta["lab_id"]
        run = client.post(
            f"/api/v1/labs/{lab_id}/runs",
            headers=lh,
            json={
                "evidence": {"stdout_hash": f"gb_{track_id}", "notes": "pack lab evidence"},
                "artifact_hashes": ["aa"],
                "client_mutation_id": f"mut_gb_lab_{track_id.lower()[:20]}",
            },
        )
        assert run.status_code == 200, run.text
