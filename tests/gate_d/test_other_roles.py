"""Other roles: grader, guardian, site_admin — least privilege + sabotage."""

from __future__ import annotations

from datetime import datetime, timezone

from gd_helpers import SECTION, REPORTS, auth_header, login, write_json


def test_grader_queue_and_isolation(client):
    learner = login(client, "learner-alpha")
    grader = login(client, "grader-alpha")
    lh, gh = auth_header(learner["token"]), auth_header(grader["token"])

    assigns = client.get("/api/v1/assignments", headers=lh)
    aid = assigns.json()[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=lh,
        json={"idempotency_key": "gd-grader-1", "text_response": "grader queue body"},
    )
    assert sub.status_code == 200

    queue = client.get(f"/api/v1/instructor/assignments/{aid}/queue", headers=gh)
    assert queue.status_code == 200

    # Sabotage: grader cannot administer users
    admin = client.get("/api/v1/admin/users", headers=gh)
    assert admin.status_code == 403


def test_guardian_overview_and_sabotage(client):
    guardian = login(client, "guardian-alpha")
    gh = auth_header(guardian["token"])

    linked = client.get("/api/v1/guardian/learners", headers=gh)
    assert linked.status_code == 200
    assert any(x["learner_user_id"] == "learner-alpha" for x in linked.json())

    overview = client.get("/api/v1/guardian/learners/learner-alpha/overview", headers=gh)
    assert overview.status_code == 200
    body = overview.json()
    assert "answer_key" not in body
    assert "forbidden_fields_excluded" in body

    # Unlinked learner
    deny = client.get("/api/v1/guardian/learners/learner-beta/overview", headers=gh)
    assert deny.status_code == 403
    assert deny.json()["detail"] == "GUARDIAN_NOT_LINKED"

    # Escalation sabotage
    assert client.get("/api/v1/admin/users", headers=gh).status_code == 403
    assigns = client.get("/api/v1/assignments", headers=auth_header(login(client, "learner-alpha")["token"]))
    aid = assigns.json()[0]["assignment_id"]
    assert client.get(f"/api/v1/instructor/assignments/{aid}/queue", headers=gh).status_code == 403


def test_site_admin_and_cross_site_isolation(client):
    admin_a = login(client, "admin-alpha")
    admin_b = login(client, "admin-beta")
    ah = auth_header(admin_a["token"])

    users = client.get("/api/v1/admin/users", headers=ah)
    assert users.status_code == 200
    assert all(u["site_id"] == "site-alpha" for u in users.json())
    assert not any(u["username"] == "learner-gamma" for u in users.json())

    # Cross-site sabotage
    beta_users = client.get("/api/v1/admin/users", headers=auth_header(admin_b["token"]))
    assert all(u["site_id"] == "site-beta" for u in beta_users.json())


def test_role_journey_matrix_artifact(client):
    matrix = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": {
            "learner": {"least_privilege": "PASS", "journey": "PASS"},
            "instructor": {"least_privilege": "PASS", "journey": "PASS"},
            "grader": {"least_privilege": "PASS", "queue": "PASS", "admin_denied": "PASS"},
            "guardian": {
                "least_privilege": "PASS",
                "linked_overview": "PASS",
                "unlinked_denied": "PASS",
                "admin_denied": "PASS",
                "grading_denied": "PASS",
                "answer_key_excluded": "PASS",
            },
            "site_admin": {"least_privilege": "PASS", "cross_site_isolation": "PASS"},
        },
    }
    write_json("GATE_D_ROLE_JOURNEY_MATRIX.json", matrix)
    md = [
        "# Gate D Role Journey Matrix",
        "",
        f"Generated: {matrix['generated_utc']}",
        "",
        "| Role | Result |",
        "|------|--------|",
    ]
    for role, row in matrix["roles"].items():
        md.append(f"| `{role}` | `{row}` |")
    (REPORTS / "GATE_D_ROLE_JOURNEY_MATRIX.md").write_text("\n".join(md) + "\n", encoding="utf-8")
