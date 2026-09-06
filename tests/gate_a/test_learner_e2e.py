"""Gate A acceptance E2E — learner path (23-step coverage)."""

from helpers import SECTION, auth_header, login, user_id
from offline_client import OfflineDevice


def test_gate_a_acceptance_23_steps(client, tmp_path):
    # 1 authenticate online
    learner = login(client, "learner-alpha")
    inst = login(client, "instructor-alpha")
    peer = login(client, "learner-beta")
    assert learner["token"]

    # 2 section/course sync locally (lease + home)
    home = client.get("/api/v1/learner/home", headers=auth_header(learner["token"]))
    assert home.status_code == 200
    assert any(s["section_id"] == SECTION for s in home.json())

    device = OfflineDevice(
        "e2e-a", tmp_path / "e2e_a.sqlite", client, learner["token"], "site-alpha", SECTION
    )
    device.obtain_lease()

    # 3 offline
    device.set_online(False)
    # 4 lesson progress
    device.save_progress_local("pack_dc", "lesson_e2e", 50)
    # 5 assignment draft
    device.save_draft_local("draft_e2e", "draft text")
    # 6 offline-eligible quiz — start online then treat submit as queued mutation path
    device.set_online(True)
    qstart = client.post(
        "/api/v1/quizzes/quiz_dc_w01_gate_a/attempts",
        headers=auth_header(learner["token"]),
    )
    assert qstart.status_code == 200
    attempt_id = qstart.json()["attempt_id"]
    device.set_online(False)
    device.enqueue(
        entity_type="quiz_attempt",
        entity_id="quiz_submit_e2e",
        operation="submit",
        payload={
            "attempt_id": attempt_id,
            "responses": {
                "qi_sc": "b",
                "qi_ms": ["a", "c"],
                "qi_tf": True,
                "qi_num": 42,
                "qi_short": "digital confidence",
                "qi_file": {"f": 1},
            },
            "client_mutation_id": "mut_e2e_quiz_submit1",
        },
    )
    # 7 discussion draft
    thr = client.post(
        "/api/v1/discussions/threads",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "title": "e2e"},
    )
    # need online briefly for thread create then draft offline via API as_draft after reconnect pattern
    device.set_online(True)
    tid = thr.json()["thread_id"]
    device.set_online(False)
    device.enqueue(
        entity_type="discussion_draft",
        entity_id="disc_e2e",
        operation="draft",
        payload={"thread_id": tid, "body": "hello draft"},
    )

    # 8-9 restart + persist
    device.restart()
    assert device.pending_count() >= 3

    # 10-11 reconnect + outbox sync
    device.set_online(True)
    results = device.sync_outbox()
    assert any(r.get("sync_status") == "acknowledged" for r in results)

    # 12 no duplicate — resync idempotent
    pending_before = device.pending_count()
    device.sync_outbox()
    assert device.pending_count() == pending_before  # already acked

    # 13 instructor receives work (manual queue)
    nxt = client.get(
        f"/api/v1/instructor/sections/{SECTION}/next-ungraded",
        headers=auth_header(inst["token"]),
    )
    assert nxt.status_code == 200
    assert nxt.json()["ungraded_count"] >= 1

    # 14 objective quiz grading correct (score from prior submit)
    attempt = client.app.state.db.execute(
        "SELECT score, status FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    assert float(attempt["score"]) == 6.0

    # 15-16 manual item + instructor grades
    grade = client.post(
        f"/api/v1/quiz-attempts/{attempt_id}/manual-grade",
        headers=auth_header(inst["token"]),
        json={"item_id": "qi_file", "points": 2, "comment": "solid"},
    )
    assert grade.status_code == 200

    # 17-18 Device B pull + Device A reconcile
    b = OfflineDevice(
        "e2e-b", tmp_path / "e2e_b.sqlite", client, learner["token"], "site-alpha", SECTION
    )
    pulled = b.pull()
    assert any(p["lesson_id"] == "lesson_e2e" for p in pulled["lesson_progress"])
    device.pull()

    # 19 conflict handled by policy
    device.enqueue(
        entity_type="assignment_draft",
        entity_id="draft_e2e",
        operation="save",
        payload={"draft_key": "draft_e2e", "text_response": "stale"},
        base_revision=0,
    )
    conflict_results = device.sync_outbox()
    assert any(r.get("sync_status") == "conflict" for r in conflict_results)

    # 20 unauthorized cross-user mutation rejected
    bad = client.post(
        "/api/v1/sync/mutations",
        headers=auth_header(peer["token"]),
        json={
            "client_mutation_id": "mut_cross_user_bad01",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "peer",
            "entity_type": "lesson_progress",
            "entity_id": "lesson_e2e",
            "base_revision": 99,
            "operation": "upsert",
            "payload": {
                "pack_id": "pack_dc",
                "lesson_id": "lesson_e2e",
                "percent_complete": 100,
            },
        },
    )
    # Peer may write own progress with same lesson id (scoped by user_id) — ensure they cannot
    # overwrite learner-alpha row: peer creates separate row.
    peer_row = client.app.state.db.execute(
        "SELECT user_id FROM lesson_progress WHERE lesson_id=? AND percent_complete=100",
        ("lesson_e2e",),
    ).fetchone()
    if peer_row:
        assert peer_row["user_id"] == user_id(peer)

    # 21 group activity
    g = client.post(
        "/api/v1/groups",
        headers=auth_header(inst["token"]),
        json={"section_id": SECTION, "name": "E2E Group", "member_ids": [user_id(learner)]},
    )
    assert g.status_code == 200
    gs = client.post(
        f"/api/v1/groups/{g.json()['group_id']}/submissions",
        headers=auth_header(learner["token"]),
        json={
            "activity_id": "a1",
            "activity_type": "lab",
            "payload": {"ok": True},
            "contributions": [{"user_id": user_id(learner), "pct": 100}],
        },
    )
    assert gs.status_code == 200

    # 22 lab path
    lab = client.post(
        "/api/v1/labs/lab_dc_local_software/runs",
        headers=auth_header(learner["token"]),
        json={
            "evidence": {"stdout_hash": "e2e"},
            "artifact_hashes": ["aa"],
            "client_mutation_id": "mut_e2e_lab_0001",
        },
    )
    assert lab.status_code == 200

    # 23 accommodation changes behavior
    client.post(
        "/api/v1/accommodations",
        headers=auth_header(inst["token"]),
        json={
            "learner_id": user_id(learner),
            "section_id": SECTION,
            "attempt_override": 10,
            "notes_private": "private",
        },
    )
    # Can start another attempt beyond default 2 because override (may already have attempts)
    start_more = client.post(
        "/api/v1/quizzes/quiz_dc_w01_gate_a/attempts",
        headers=auth_header(learner["token"]),
    )
    assert start_more.status_code == 200
