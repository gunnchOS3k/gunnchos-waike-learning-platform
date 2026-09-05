"""Object-level authorization closure.

The recurring failure mode these tests target: treating "same site" or "has the
instructor role" as authorization. Every check must be scoped to the specific
section the object belongs to.
"""

from __future__ import annotations

import pytest
from helpers import SECTION, auth_header, login, user_id

OTHER_SECTION = "sec_beta_dc_w01"
QUIZ = "quiz_dc_w01_gate_a"
LAB = "lab_dc_local_software"


def _unrelated_instructor(client, prod_app) -> tuple[dict, str]:
    """An instructor in the SAME site who is not assigned to SECTION.

    This is the dangerous case: site-level checks let them through, so the section
    assignment check is the only thing standing between them and another cohort.
    """
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    created = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "instructor-unrelated",
            "display_name": "Unrelated Instructor",
            "password": "WaikeTestPass1!",
            "roles": ["instructor"],
        },
    )
    assert created.status_code in (200, 201), created.text
    uid = created.json()["user_id"]
    # Give them a real section of their own, so the only thing separating them from
    # SECTION is the assignment check rather than "has no sections at all".
    pkg = prod_app.state.db.execute(
        "SELECT package_id FROM packages LIMIT 1"
    ).fetchone()
    assert pkg is not None, "seed must provide at least one package"
    other = client.post(
        "/api/v1/admin/sections",
        headers=ah,
        json={
            "code": "DC-W99",
            "title": "Unrelated Alpha Section",
            "package_id": pkg["package_id"],
        },
    )
    assert other.status_code in (200, 201), other.text
    client.post(
        f"/api/v1/admin/sections/{other.json()['section_id']}/instructors",
        headers=ah,
        json={"user_id": uid},
    )
    session = login(client, "instructor-unrelated", "site-alpha")
    # Same site as the target section, and genuinely an instructor.
    assert session["user"]["site_id"] == "site-alpha"
    assert "instructor" in session["user"]["roles"]
    return session, uid


def test_unrelated_same_site_instructor_cannot_read_section_activities(client, prod_app):
    intruder, _ = _unrelated_instructor(client, prod_app)
    r = client.get(
        f"/api/v1/sections/{SECTION}/activities",
        headers=auth_header(intruder["token"]),
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] in {"SECTION_NOT_ASSIGNED", "SECTION_ACCESS_DENIED"}


def test_unrelated_same_site_instructor_cannot_read_answer_key(client, prod_app):
    intruder, _ = _unrelated_instructor(client, prod_app)
    r = client.get(
        f"/api/v1/quizzes/{QUIZ}/answer-key", headers=auth_header(intruder["token"])
    )
    assert r.status_code == 403, r.text
    # The key itself must not leak in the error body either.
    assert "correct" not in r.text


def test_unrelated_same_site_instructor_cannot_grade_or_moderate(client, prod_app):
    learner = login(client, "learner-alpha")
    lh = auth_header(learner["token"])
    attempt = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=lh).json()
    client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/submit",
        headers=lh,
        json={"responses": {"qi_file": {"note": "done"}}},
    )
    thread = client.post(
        "/api/v1/discussions/threads",
        headers=lh,
        json={"section_id": SECTION, "title": "Closure thread"},
    ).json()
    post = client.post(
        f"/api/v1/discussions/threads/{thread['thread_id']}/posts",
        headers=lh,
        json={"body": "learner post"},
    ).json()

    intruder, _ = _unrelated_instructor(client, prod_app)
    ih = auth_header(intruder["token"])

    graded = client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/manual-grade",
        headers=ih,
        json={"item_id": "qi_file", "points": 2, "comment": "not mine to grade"},
    )
    assert graded.status_code == 403, graded.text

    queued = client.get(
        f"/api/v1/instructor/sections/{SECTION}/manual-queue", headers=ih
    )
    assert queued.status_code == 403

    moderated = client.post(
        f"/api/v1/discussions/posts/{post['post_id']}/moderate",
        headers=ih,
        json={"note": "sabotage", "delete": True},
    )
    assert moderated.status_code == 403

    accommodated = client.post(
        "/api/v1/accommodations",
        headers=ih,
        json={
            "learner_id": user_id(learner),
            "section_id": SECTION,
            "time_multiplier": 10.0,
        },
    )
    assert accommodated.status_code == 403

    # And nothing was written despite four attempts.
    detail = client.get(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}",
        headers=auth_header(login(client, "instructor-alpha")["token"]),
    ).json()
    file_item = next(i for i in detail["items"] if i["item_id"] == "qi_file")
    assert not file_item["manual_graded"]
    assert file_item["points_earned"] in (None, 0, 0.0)


def test_mutation_without_lease_still_requires_section_authorization(client):
    """A missing lease must not become a bypass for the section check."""
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/sync/mutations",
        headers=auth_header(learner["token"]),
        json={
            "client_mutation_id": "mut_authz_no_lease_01",
            "site_id": "site-alpha",
            "section_id": OTHER_SECTION,
            "device_id": "dev_authz",
            "entity_type": "lesson_progress",
            "entity_id": "L1",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "pack_dc", "lesson_id": "L1", "percent_complete": 10},
            # deliberately no lease_id
        },
    )
    assert r.status_code in (403, 404), r.text


def test_learner_cannot_pull_another_section(client):
    learner = login(client, "learner-alpha")
    r = client.get(
        f"/api/v1/sync/pull?section_id={OTHER_SECTION}&since_revision=0",
        headers=auth_header(learner["token"]),
    )
    assert r.status_code in (403, 404), r.text


def test_revoked_learner_cannot_pull_after_revocation(client, prod_app):
    admin = login(client, "admin-alpha")
    learner = login(client, "learner-alpha")
    lh = auth_header(learner["token"])
    assert client.get(f"/api/v1/sync/pull?section_id={SECTION}", headers=lh).status_code == 200

    enr = prod_app.state.db.execute(
        "SELECT enrollment_id FROM enrollments WHERE user_id=? AND section_id=? AND status='active'",
        (user_id(learner), SECTION),
    ).fetchone()
    client.post(
        f"/api/v1/admin/enrollments/{enr['enrollment_id']}/deactivate",
        headers=auth_header(admin["token"]),
    )
    after = client.get(f"/api/v1/sync/pull?section_id={SECTION}", headers=lh)
    assert after.status_code == 403, after.text


def test_lease_read_and_revoke_are_scoped_to_owner_and_assigned_staff(client, prod_app):
    learner = login(client, "learner-alpha")
    lease = client.post(
        "/api/v1/sync/leases",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "device_id": "dev_lease_scope"},
    ).json()
    lid = lease["lease_id"]

    # Owner reads their own lease.
    assert client.get(f"/api/v1/sync/leases/{lid}", headers=auth_header(learner["token"])).status_code == 200
    # Assigned instructor may read it.
    instructor = login(client, "instructor-alpha")
    assert client.get(f"/api/v1/sync/leases/{lid}", headers=auth_header(instructor["token"])).status_code == 200

    # A different learner in the same section may not.
    other_learner = login(client, "learner-beta")
    assert client.get(f"/api/v1/sync/leases/{lid}", headers=auth_header(other_learner["token"])).status_code == 403

    # An unrelated same-site instructor may neither read nor revoke.
    intruder, _ = _unrelated_instructor(client, prod_app)
    ih = auth_header(intruder["token"])
    assert client.get(f"/api/v1/sync/leases/{lid}", headers=ih).status_code == 403
    assert client.post(f"/api/v1/sync/leases/{lid}/revoke", headers=ih, json={"reason": "x"}).status_code == 403

    # The lease is still live after the failed sabotage.
    still = client.get(f"/api/v1/sync/leases/{lid}", headers=auth_header(learner["token"])).json()
    assert not still.get("revoked")


def test_receipt_read_requires_ownership_or_assigned_staff(client, prod_app):
    learner = login(client, "learner-alpha")
    lh = auth_header(learner["token"])
    mid = "mut_receipt_scope_01"
    applied = client.post(
        "/api/v1/sync/mutations",
        headers=lh,
        json={
            "client_mutation_id": mid,
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "dev_receipt",
            "entity_type": "lesson_progress",
            "entity_id": "L1",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "pack_dc", "lesson_id": "L1", "percent_complete": 15},
        },
    )
    assert applied.status_code == 200, applied.text

    assert client.get(f"/api/v1/sync/receipts/{mid}", headers=lh).status_code == 200
    assert (
        client.get(
            f"/api/v1/sync/receipts/{mid}",
            headers=auth_header(login(client, "instructor-alpha")["token"]),
        ).status_code
        == 200
    )
    # Another learner must never see someone else's receipt.
    other = client.get(
        f"/api/v1/sync/receipts/{mid}", headers=auth_header(login(client, "learner-beta")["token"])
    )
    assert other.status_code in (403, 404)
    assert mid not in other.text or other.status_code == 403

    intruder, _ = _unrelated_instructor(client, prod_app)
    assert client.get(f"/api/v1/sync/receipts/{mid}", headers=auth_header(intruder["token"])).status_code in (403, 404)


def test_cross_site_actor_is_refused_everywhere(client):
    gamma = login(client, "learner-gamma", "site-beta")
    gh = auth_header(gamma["token"])
    for path in (
        f"/api/v1/sections/{SECTION}/activities",
        f"/api/v1/quizzes/{QUIZ}",
        f"/api/v1/labs/{LAB}",
        f"/api/v1/sync/pull?section_id={SECTION}",
        f"/api/v1/discussions/threads?section_id={SECTION}",
        f"/api/v1/groups?section_id={SECTION}",
    ):
        r = client.get(path, headers=gh)
        assert r.status_code in (403, 404), f"{path} leaked: {r.status_code} {r.text}"


@pytest.mark.parametrize("username", ["learner-beta"])
def test_learner_cannot_read_another_learners_attempt(client, username):
    owner = login(client, "learner-alpha")
    oh = auth_header(owner["token"])
    attempt = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=oh).json()
    client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/submit",
        headers=oh,
        json={"responses": {"qi_tf": True}},
    )
    intruder = login(client, username)
    r = client.get(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}",
        headers=auth_header(intruder["token"]),
    )
    assert r.status_code == 403, r.text
    assert "qi_tf" not in r.text


def test_learner_attempt_view_never_contains_answer_key(client):
    learner = login(client, "learner-alpha")
    lh = auth_header(learner["token"])
    attempt = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=lh).json()
    client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/submit",
        headers=lh,
        json={"responses": {"qi_sc": "a", "qi_tf": False}},
    )
    body = client.get(f"/api/v1/quiz-attempts/{attempt['attempt_id']}", headers=lh)
    assert body.status_code == 200, body.text
    payload = body.json()
    assert "answer_key" not in body.text
    assert "correct" not in body.text
    # The learner view must not expose grading internals either.
    for resp in payload["responses"]:
        assert "auto_graded" not in resp
