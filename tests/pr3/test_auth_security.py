"""PR3 auth security tests — production sessions, password hashing, fixture rejection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.auth import hash_password, session_token_hash
from app.modules.identity import FIXTURE_PASSWORD

SITE_FOR_USER = {
    "admin-alpha": "site-alpha",
    "instructor-alpha": "site-alpha",
    "grader-alpha": "site-alpha",
    "learner-alpha": "site-alpha",
    "learner-beta": "site-alpha",
    "admin-beta": "site-beta",
    "instructor-beta": "site-beta",
    "learner-gamma": "site-beta",
}


def login(client, username="learner-alpha", password=FIXTURE_PASSWORD, site_id=None):
    sid = site_id or SITE_FOR_USER.get(username, "site-alpha")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "site_id": sid},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login_json(username: str, password: str = FIXTURE_PASSWORD, site_id: str | None = None) -> dict:
    return {
        "username": username,
        "password": password,
        "site_id": site_id or SITE_FOR_USER.get(username, "site-alpha"),
    }


def test_valid_login(client):
    body = login(client)
    assert body["user"]["user_id"] == "learner-alpha"
    me = client.get("/api/v1/auth/me", headers=auth_header(body["token"]))
    assert me.status_code == 200
    assert me.json()["user_id"] == "learner-alpha"


def test_wrong_password(client):
    r = client.post(
        "/api/v1/auth/login",
        json=_login_json("learner-alpha", "definitely-wrong-password"),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "INVALID_PASSWORD"


def test_unknown_user(client):
    r = client.post(
        "/api/v1/auth/login",
        json=_login_json("no-such-user"),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "UNKNOWN_USER"


def test_missing_site_id_rejected(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "learner-alpha", "password": FIXTURE_PASSWORD},
    )
    assert r.status_code == 422


def test_empty_site_id_rejected(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "learner-alpha", "password": FIXTURE_PASSWORD, "site_id": ""},
    )
    assert r.status_code == 422


def test_wrong_site_does_not_leak_username(client):
    r = client.post(
        "/api/v1/auth/login",
        json=_login_json("learner-alpha", site_id="site-beta"),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "UNKNOWN_USER"


def test_same_username_site_scoped(client, prod_app):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    cu = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "shared-name",
            "display_name": "Shared Alpha",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner"],
        },
    )
    assert cu.status_code == 200
    admin_b = login(client, "admin-beta", site_id="site-beta")
    bh = auth_header(admin_b["token"])
    cu2 = client.post(
        "/api/v1/admin/users",
        headers=bh,
        json={
            "username": "shared-name",
            "display_name": "Shared Beta",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner"],
        },
    )
    assert cu2.status_code == 200
    a = client.post("/api/v1/auth/login", json=_login_json("shared-name", site_id="site-alpha"))
    b = client.post("/api/v1/auth/login", json=_login_json("shared-name", site_id="site-beta"))
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["user"]["site_id"] == "site-alpha"
    assert b.json()["user"]["site_id"] == "site-beta"
    assert a.json()["user"]["user_id"] != b.json()["user"]["user_id"]
    # Alpha-only password must not authenticate the beta account.
    prod_app.state.db.execute(
        "UPDATE users SET password_hash=? WHERE username=? AND site_id=?",
        (hash_password("AlphaOnlyPass9!"), "shared-name", "site-alpha"),
    )
    prod_app.state.db.commit()
    cross = client.post(
        "/api/v1/auth/login",
        json={
            "username": "shared-name",
            "password": "AlphaOnlyPass9!",
            "site_id": "site-beta",
        },
    )
    assert cross.status_code == 401
    assert cross.json()["detail"] == "INVALID_PASSWORD"


def test_disabled_user_rejected(client):
    admin = login(client, "admin-alpha")
    ah = auth_header(admin["token"])
    cu = client.post(
        "/api/v1/admin/users",
        headers=ah,
        json={
            "username": "temp-disabled",
            "display_name": "Temp",
            "password": FIXTURE_PASSWORD,
            "roles": ["learner"],
        },
    )
    assert cu.status_code == 200
    uid = cu.json()["user_id"]
    client.post(f"/api/v1/admin/users/{uid}/disable", headers=ah, json={"disabled": True})
    r = client.post(
        "/api/v1/auth/login",
        json=_login_json("temp-disabled"),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "USER_DISABLED"


def test_logout_and_reuse_rejected(client):
    body = login(client)
    h = auth_header(body["token"])
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401
    assert r.json()["detail"] == "SESSION_REVOKED"


def test_malformed_token(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer short"})
    assert r.status_code == 401
    assert r.json()["detail"] in {"MALFORMED_TOKEN", "INVALID_SESSION"}


def test_expired_session(prod_app, client):
    body = login(client)
    past = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prod_app.state.db.execute(
        "UPDATE sessions SET expires_at=? WHERE session_id=?",
        (past, body["session_id"]),
    )
    prod_app.state.db.commit()
    r = client.get("/api/v1/auth/me", headers=auth_header(body["token"]))
    assert r.status_code == 401
    assert r.json()["detail"] == "SESSION_EXPIRED"


def test_revoked_session(prod_app, client):
    body = login(client)
    prod_app.state.db.execute(
        "UPDATE sessions SET revoked=1 WHERE session_id=?", (body["session_id"],)
    )
    prod_app.state.db.commit()
    r = client.get("/api/v1/auth/me", headers=auth_header(body["token"]))
    assert r.status_code == 401
    assert r.json()["detail"] == "SESSION_REVOKED"


def test_fixture_headers_rejected_in_production(client):
    r = client.get(
        "/api/v1/assignments",
        headers={"X-Waike-Actor-Id": "learner-alpha", "X-Waike-Actor-Role": "learner"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "FIXTURE_AUTH_REJECTED"


def test_role_spoof_rejected(tmp_path, monkeypatch):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.main import HubConfig, create_app

    root = Path(__file__).resolve().parents[2]
    import os

    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        waike = Path(env)
    elif (root / "waike-research-ops").is_dir():
        waike = root / "waike-research-ops"
    else:
        waike = root.parent / "waike-research-ops"
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    app = create_app(
        HubConfig(production_auth_enabled=False, fixture_auth_enabled=True),
        db_path=tmp_path / "fx.sqlite3",
        seed=True,
    )
    c = TestClient(app)
    r = c.get(
        "/api/v1/assignments",
        headers={"X-Waike-Actor-Id": "learner-alpha", "X-Waike-Actor-Role": "instructor"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "ROLE_MISMATCH"


def test_password_hash_not_plaintext(prod_app):
    row = prod_app.state.db.execute(
        "SELECT password_hash FROM users WHERE user_id='learner-alpha'"
    ).fetchone()
    assert FIXTURE_PASSWORD not in row["password_hash"]
    assert row["password_hash"].startswith("$argon2") or row["password_hash"].startswith("scrypt$")


def test_session_stores_hash_not_token(prod_app, client):
    body = login(client)
    row = prod_app.state.db.execute(
        "SELECT token_hash FROM sessions WHERE session_id=?", (body["session_id"],)
    ).fetchone()
    assert row["token_hash"] == session_token_hash(body["token"])
