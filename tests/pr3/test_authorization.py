"""Site boundary and object-level authorization negatives."""

from __future__ import annotations

from app.modules.identity import FIXTURE_PASSWORD

SECTION_ALPHA = "sec_alpha_dc_w01"
SECTION_BETA = "sec_beta_dc_w01"


def login(client, username: str, password: str = FIXTURE_PASSWORD, site_id: str | None = None):
    sid = site_id or {
        "admin-alpha": "site-alpha",
        "instructor-alpha": "site-alpha",
        "grader-alpha": "site-alpha",
        "learner-alpha": "site-alpha",
        "learner-beta": "site-alpha",
        "admin-beta": "site-beta",
        "instructor-beta": "site-beta",
        "learner-gamma": "site-beta",
    }.get(username, "site-alpha")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "site_id": sid},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_learner_cannot_access_other_learner_submission(client):
    a = login(client, "learner-alpha")
    b = login(client, "learner-beta")
    assigns = client.get("/api/v1/assignments", headers=auth_header(a["token"])).json()
    aid = assigns[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=auth_header(a["token"]),
        json={"idempotency_key": "iso-a-1", "text_response": "alpha submission body"},
    )
    assert sub.status_code == 200
    sid = sub.json()["submission_id"]
    r = client.get(f"/api/v1/submissions/{sid}", headers=auth_header(b["token"]))
    assert r.status_code == 403
    assert r.json()["detail"] == "FORBIDDEN_OTHER_LEARNER"


def test_learner_cannot_instructor_queue(client):
    a = login(client, "learner-alpha")
    assigns = client.get("/api/v1/assignments", headers=auth_header(a["token"])).json()
    r = client.get(
        f"/api/v1/instructor/assignments/{assigns[0]['assignment_id']}/queue",
        headers=auth_header(a["token"]),
    )
    assert r.status_code == 403


def test_cross_site_section_forbidden(client):
    alpha_inst = login(client, "instructor-alpha")
    r = client.get(
        f"/api/v1/sections/{SECTION_BETA}",
        headers=auth_header(alpha_inst["token"]),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "CROSS_SITE_FORBIDDEN"


def test_cross_site_admin_cannot_list_other_site_users(client):
    admin_a = login(client, "admin-alpha")
    users = client.get("/api/v1/admin/users", headers=auth_header(admin_a["token"])).json()
    assert all(u["site_id"] == "site-alpha" for u in users)
    assert not any(u["username"] == "learner-gamma" for u in users)


def test_beta_instructor_cannot_grade_alpha_submission(client):
    learner = login(client, "learner-alpha")
    assigns = client.get("/api/v1/assignments", headers=auth_header(learner["token"])).json()
    aid = assigns[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=auth_header(learner["token"]),
        json={"idempotency_key": "cross-grade-1", "text_response": "body for cross site"},
    ).json()
    detail = client.get(f"/api/v1/assignments/{aid}", headers=auth_header(learner["token"])).json()
    beta_inst = login(client, "instructor-beta")
    scores = [
        {
            "criterion_id": c["criterion_id"],
            "points": 3,
            "level_id": next(l["level_id"] for l in c["levels"] if l["score"] == 3),
            "comment": "x",
        }
        for c in detail["rubric"]["criteria"]
    ]
    r = client.post(
        f"/api/v1/instructor/submissions/{sub['submission_id']}/grade",
        headers=auth_header(beta_inst["token"]),
        json={"criterion_scores": scores, "feedback_body": "nope", "return_to_learner": True},
    )
    assert r.status_code == 403


def test_unenrolled_learner_cannot_submit_other_section(client):
    gamma = login(client, "learner-gamma")
    assigns = client.get("/api/v1/assignments", headers=auth_header(gamma["token"])).json()
    aid = assigns[0]["assignment_id"]
    r = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=auth_header(gamma["token"]),
        json={
            "idempotency_key": "gamma-wrong-sec",
            "text_response": "trying alpha section",
            "section_id": SECTION_ALPHA,
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] in {"NOT_ENROLLED", "CROSS_SITE_FORBIDDEN"}


def test_duplicate_active_enrollment_rejected(client):
    admin = login(client, "admin-alpha")
    r = client.post(
        f"/api/v1/admin/sections/{SECTION_ALPHA}/enrollments",
        headers=auth_header(admin["token"]),
        json={"user_id": "learner-alpha"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "DUPLICATE_ACTIVE_ENROLLMENT"
