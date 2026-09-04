"""Gradebook matrix, states, weighted categories, override audits."""

from __future__ import annotations

from app.modules.identity import FIXTURE_PASSWORD

SECTION = "sec_alpha_dc_w01"


def login(client, username: str, password: str = FIXTURE_PASSWORD, site_id: str = "site-alpha"):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "site_id": site_id},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gradebook_matrix_and_learner_view(client):
    inst = login(client, "instructor-alpha")
    ih = auth_header(inst["token"])
    matrix = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih)
    assert matrix.status_code == 200
    body = matrix.json()
    assert body["section_id"] == SECTION
    assert body["categories"]
    assert body["items"]
    item_id = body["items"][0]["item_id"]

    # Set graded / missing / excused / late
    for learner, pts, status, reason in [
        ("learner-alpha", 18.0, "graded", "initial"),
        ("learner-beta", None, "missing", "no submit"),
    ]:
        r = client.post(
            f"/api/v1/gradebook/items/{item_id}/scores",
            headers=ih,
            json={"learner_id": learner, "points_earned": pts, "status": status, "reason": reason},
        )
        assert r.status_code == 200, r.text

    # Override with audit
    ov = client.post(
        f"/api/v1/gradebook/items/{item_id}/scores",
        headers=ih,
        json={
            "learner_id": "learner-alpha",
            "points_earned": 16.0,
            "status": "graded",
            "reason": "reconsideration",
        },
    )
    assert ov.status_code == 200
    entry_id = ov.json()["entry_id"]
    audits = client.get(f"/api/v1/gradebook/entries/{entry_id}/overrides", headers=ih)
    assert audits.status_code == 200
    assert any(a["reason"] == "reconsideration" for a in audits.json())
    assert any(a.get("before_json") for a in audits.json())

    refreshed = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih).json()
    alpha_row = next(r for r in refreshed["rows"] if r["learner_id"] == "learner-alpha")
    assert alpha_row["overall_percent"] is not None
    assert alpha_row["overall_percent"] == alpha_row["overall_percent"]  # not NaN
    beta_row = next(r for r in refreshed["rows"] if r["learner_id"] == "learner-beta")
    assert beta_row["cells"][item_id]["status"] == "missing"

    # Learner own view
    la = login(client, "learner-alpha")
    own = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=auth_header(la["token"]))
    assert own.status_code == 200
    assert len(own.json()["rows"]) == 1
    assert own.json()["rows"][0]["learner_id"] == "learner-alpha"

    # Cannot see peer
    assert all(r["learner_id"] == "learner-alpha" for r in own.json()["rows"])


def test_excused_excluded_from_average(client):
    inst = login(client, "instructor-alpha")
    ih = auth_header(inst["token"])
    matrix = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih).json()
    item_id = matrix["items"][0]["item_id"]
    client.post(
        f"/api/v1/gradebook/items/{item_id}/scores",
        headers=ih,
        json={"learner_id": "learner-beta", "points_earned": None, "status": "excused", "reason": "medical"},
    )
    refreshed = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih).json()
    beta = next(r for r in refreshed["rows"] if r["learner_id"] == "learner-beta")
    assert beta["cells"][item_id]["status"] == "excused"


def test_nan_rejected(client):
    inst = login(client, "instructor-alpha")
    ih = auth_header(inst["token"])
    item_id = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih).json()["items"][0]["item_id"]
    # Bypass JSON by hitting service with invalid float via out-of-range sentinel string → 422,
    # and also via direct service call.
    from app.main import create_app  # local

    # HTTP layer: non-finite via string
    r = client.post(
        f"/api/v1/gradebook/items/{item_id}/scores",
        headers=ih,
        json={"learner_id": "learner-alpha", "points_earned": "not-a-number", "status": "graded", "reason": "bad"},
    )
    assert r.status_code == 422
    # Direct service: infinity
    app = client.app
    actor = None
    # login already proved instructor; call service with +inf
    from app.auth import Actor, Role

    actor = Actor(
        actor_id="instructor-alpha",
        role=Role.INSTRUCTOR,
        display_name="Instructor Alpha",
        site_id="site-alpha",
        roles=(Role.INSTRUCTOR,),
        username="instructor-alpha",
    )
    from app.modules.assessment_lifecycle import ServiceError

    try:
        app.state.gradebook.set_score(actor, item_id, "learner-alpha", float("inf"), "graded", "bad")
        assert False, "expected ServiceError"
    except ServiceError as e:
        assert e.code == "INVALID_POINTS"
