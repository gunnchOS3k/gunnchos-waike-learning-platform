"""Multi-role authorization + atomic create-user validate-before-mutate."""

from __future__ import annotations

from app.auth import Role
from app.modules.identity import FIXTURE_PASSWORD

SITE = "site-alpha"
SECTION = "sec_alpha_dc_w01"


def login(client, username: str, password: str = FIXTURE_PASSWORD, site_id: str = SITE):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "site_id": site_id},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_learner_plus_instructor_can_access_instructor_scope(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    cu = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "multi-li",
            "display_name": "Multi LI",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner", "instructor"],
        },
    )
    assert cu.status_code == 200
    uid = cu.json()["user_id"]
    # Ensure both roles active even if insert order differed
    roles = set(cu.json()["roles"])
    assert "learner" in roles and "instructor" in roles
    # Section staff assignment required for dashboard object-level authz
    staff = client.post(
        f"/api/v1/admin/sections/{SECTION}/instructors",
        headers=ah,
        json={"user_id": uid},
    )
    assert staff.status_code == 200
    # Enroll so learner home works
    client.post(
        f"/api/v1/admin/sections/{SECTION}/enrollments",
        headers=ah,
        json={"user_id": uid},
    )
    sess = login(client, "multi-li")
    h = auth_header(sess["token"])
    # Instructor scope (role membership + staff)
    dash = client.get(f"/api/v1/instructor/sections/{SECTION}/dashboard", headers=h)
    assert dash.status_code == 200
    # Learner scope via has_role(LEARNER) even when primary role is instructor
    home = client.get("/api/v1/learner/home", headers=h)
    assert home.status_code == 200


def test_learner_plus_site_admin_can_admin(client):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    cu = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "multi-la",
            "display_name": "Multi LA",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner", "site_admin"],
        },
    )
    assert cu.status_code == 200
    sess = login(client, "multi-la")
    users = client.get("/api/v1/admin/users", headers=auth_header(sess["token"]))
    assert users.status_code == 200


def test_deactivated_role_revokes_capability(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    cu = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "temp-inst",
            "display_name": "Temp Inst",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner", "instructor"],
        },
    )
    assert cu.status_code == 200
    uid = cu.json()["user_id"]
    # Deactivate instructor membership
    prod_app.state.identity.deactivate_role(
        __import__("app.auth", fromlist=["Actor"]).Actor(
            actor_id=admin["user"]["user_id"],
            role=Role.SITE_ADMIN,
            display_name="Admin",
            site_id=SITE,
            roles=(Role.SITE_ADMIN,),
            username="admin-alpha",
            session_id=admin["session_id"],
        ),
        uid,
        "instructor",
    )
    sess = login(client, "temp-inst")
    h = auth_header(sess["token"])
    dash = client.get(f"/api/v1/instructor/sections/{SECTION}/dashboard", headers=h)
    assert dash.status_code == 403
    home = client.get("/api/v1/learner/home", headers=h)
    assert home.status_code == 200


def test_client_cannot_elevate_unpersisted_role(tmp_path, monkeypatch):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.main import HubConfig, create_app

    root = Path(__file__).resolve().parents[2]
    import os

    env = os.environ.get("WAIKE_ROOT")
    waike = Path(env) if env and Path(env).is_dir() else root.parent / "waike-research-ops"
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    app = create_app(
        HubConfig(production_auth_enabled=False, fixture_auth_enabled=True),
        db_path=tmp_path / "elevate.sqlite3",
        seed=True,
    )
    c = TestClient(app)
    # Claim site_admin for a learner fixture — rejected
    r = c.get(
        "/api/v1/admin/users",
        headers={"X-Waike-Actor-Id": "learner-alpha", "X-Waike-Actor-Role": "site_admin"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "ROLE_MISMATCH"


def test_create_user_invalid_role_rolls_back(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    before = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username='partial-user'"
    ).fetchone()["c"]
    r = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "partial-user",
            "display_name": "Partial",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner", "not-a-real-role"],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "INVALID_ROLE"
    after = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username='partial-user'"
    ).fetchone()["c"]
    assert after == before == 0
    # No success audit for failed create
    aud = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE action='create_user' AND detail_json LIKE '%partial-user%'"
    ).fetchone()["c"]
    assert aud == 0


def test_create_user_duplicate_username_no_partial(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    r = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "learner-alpha",
            "display_name": "Dup",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner"],
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "USERNAME_TAKEN"
    # Still exactly one learner-alpha
    n = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username='learner-alpha' AND site_id=?",
        (SITE,),
    ).fetchone()["c"]
    assert n == 1


def test_create_user_password_validation_fail_no_user(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    r = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "short-pw-user",
            "display_name": "Short",
            "password": "short",
            "roles": ["learner"],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "PASSWORD_TOO_SHORT"
    n = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username='short-pw-user'"
    ).fetchone()["c"]
    assert n == 0


def test_create_user_audit_only_after_success(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    before = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE action='create_user'"
    ).fetchone()["c"]
    # Fail first
    client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "audit-fail",
            "display_name": "X",
            "password": "short",
            "roles": ["learner"],
        },
    )
    mid = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE action='create_user'"
    ).fetchone()["c"]
    assert mid == before
    ok = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "audit-ok",
            "display_name": "OK",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner"],
        },
    )
    assert ok.status_code == 200
    after = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE action='create_user'"
    ).fetchone()["c"]
    assert after == before + 1
