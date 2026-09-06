"""AI policy: server-authoritative, learner cannot alter, capability gating."""

from helpers import SECTION, auth_header, login


def test_default_policy_is_ai_allowed(client):
    learner = login(client, "learner-alpha")
    r = client.get(
        f"/api/v1/ai/policy?section_id={SECTION}",
        headers=auth_header(learner["token"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["policy"] == "AI_ALLOWED"
    assert "hint" in body["allowed_learner_capabilities"]


def test_learner_cannot_set_policy(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/policy",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "policy": "AI_DISABLED", "scope": "section"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] in {"AI_POLICY_LEARNER_CANNOT_SET", "INSTRUCTOR_ROLE_REQUIRED"}


def test_instructor_sets_hints_only_blocks_explain(client):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/policy",
        headers=auth_header(instructor["token"]),
        json={"section_id": SECTION, "policy": "AI_HINTS_ONLY", "scope": "section"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["policy"] == "AI_HINTS_ONLY"

    ok = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "capability": "hint", "query": "Give me a small next step"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True

    blocked = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "capability": "explain", "query": "Explain binary search"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "AI_CAPABILITY_FORBIDDEN"


def test_ai_disabled_blocks_all_learner_assist(client):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    client.post(
        "/api/v1/ai/policy",
        headers=auth_header(instructor["token"]),
        json={"section_id": SECTION, "policy": "AI_DISABLED", "scope": "section"},
    )
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "capability": "hint", "query": "help"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "AI_DISABLED"


def test_activity_scope_overrides_section(client):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    client.post(
        "/api/v1/ai/policy",
        headers=auth_header(instructor["token"]),
        json={"section_id": SECTION, "policy": "AI_ALLOWED", "scope": "section"},
    )
    client.post(
        "/api/v1/ai/policy",
        headers=auth_header(instructor["token"]),
        json={
            "section_id": SECTION,
            "policy": "AI_DISABLED",
            "scope": "activity",
            "activity_id": "quiz_dc_w01_gate_a",
        },
    )
    pol = client.get(
        f"/api/v1/ai/policy?section_id={SECTION}&activity_id=quiz_dc_w01_gate_a",
        headers=auth_header(learner["token"]),
    ).json()
    assert pol["policy"] == "AI_DISABLED"
    assert pol["scope"] == "activity"


def test_instructor_defined_caps(client):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/policy",
        headers=auth_header(instructor["token"]),
        json={
            "section_id": SECTION,
            "policy": "AI_INSTRUCTOR_DEFINED",
            "scope": "section",
            "instructor_defined": {"allowed_capabilities": ["hint", "reflect"]},
        },
    )
    assert r.status_code == 200, r.text
    assert "hint" in r.json()["allowed_learner_capabilities"]
    assert "explain" not in r.json()["allowed_learner_capabilities"]

    blocked = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "capability": "navigate", "query": "where next"},
    )
    assert blocked.status_code == 403
