"""Startup security: default runtime must not seed known test accounts."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import HubConfig, create_app
from app.modules.identity import FIXTURE_PASSWORD, IdentityService

ROOT = Path(__file__).resolve().parents[2]


def _waike() -> Path:
    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    raise FileNotFoundError("waike-research-ops missing")


def test_create_app_default_has_zero_synthetic_users(tmp_path, monkeypatch):
    """DEFAULT_RUNTIME_HAS_NO_TEST_ACCOUNTS"""
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    monkeypatch.delenv("WAIKE_ENV", raising=False)
    app = create_app(db_path=tmp_path / "clean.sqlite3")  # seed=False default
    n = app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert n == 0
    assert app.state.seeded_test_fixtures is False
    print("DEFAULT_RUNTIME_HAS_NO_TEST_ACCOUNTS")


def test_default_runtime_production_auth_enabled(tmp_path, monkeypatch):
    """DEFAULT_RUNTIME_PRODUCTION_AUTH_ENABLED"""
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    app = create_app(db_path=tmp_path / "prod.sqlite3", seed=False)
    body = TestClient(app).get("/version").json()
    assert body["production_auth_enabled"] is True
    print("DEFAULT_RUNTIME_PRODUCTION_AUTH_ENABLED")


def test_default_runtime_fixture_auth_disabled(tmp_path, monkeypatch):
    """DEFAULT_RUNTIME_FIXTURE_AUTH_DISABLED"""
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    app = create_app(db_path=tmp_path / "fxoff.sqlite3", seed=False)
    body = TestClient(app).get("/version").json()
    assert body["fixture_auth_enabled"] is False
    print("DEFAULT_RUNTIME_FIXTURE_AUTH_DISABLED")


def test_default_runtime_rejects_fixture_password(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    app = create_app(db_path=tmp_path / "nopw.sqlite3", seed=False)
    client = TestClient(app)
    for username in ("learner-alpha", "admin-alpha", "instructor-alpha"):
        r = client.post(
            "/api/v1/auth/login",
            json={
                "username": username,
                "password": FIXTURE_PASSWORD,
                "site_id": "site-alpha",
            },
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "UNKNOWN_USER"


def test_module_level_create_app_seed_false_contract(tmp_path, monkeypatch):
    """Module-level app uses create_app(seed=False); env must not be set for bare import."""
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    monkeypatch.setenv("WAIKE_ENV", "development")
    app = create_app(db_path=tmp_path / "module_contract.sqlite3", seed=False)
    assert app.state.seeded_test_fixtures is False
    assert app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0


def test_explicit_seed_still_creates_deterministic_fixtures(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    app = create_app(
        HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
        db_path=tmp_path / "seeded.sqlite3",
        seed=True,
    )
    client = TestClient(app)
    r = client.post(
        "/api/v1/auth/login",
        json={
            "username": "learner-alpha",
            "password": FIXTURE_PASSWORD,
            "site_id": "site-alpha",
        },
    )
    assert r.status_code == 200
    assert r.json()["user"]["user_id"] == "learner-alpha"


def test_env_opt_in_seeds_only_outside_bare_production(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.setenv("WAIKE_SEED_TEST_FIXTURES", "true")
    monkeypatch.setenv("WAIKE_ENV", "development")
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    app = create_app(db_path=tmp_path / "envseed.sqlite3", seed=False)
    assert app.state.seeded_test_fixtures is True
    n = app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert n > 0


def test_production_env_blocks_seed_without_fixture_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    monkeypatch.setenv("WAIKE_SEED_TEST_FIXTURES", "true")
    monkeypatch.setenv("WAIKE_ENV", "production")
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    app = create_app(db_path=tmp_path / "prodblock.sqlite3", seed=False)
    assert app.state.seeded_test_fixtures is False
    n = app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert n == 0


def test_bootstrap_admin_empty_db(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    app = create_app(db_path=tmp_path / "boot.sqlite3", seed=False)
    identity: IdentityService = app.state.identity
    result = identity.bootstrap_admin(
        site_id="site-prod",
        site_name="Prod Site",
        username="root-admin",
        display_name="Root Admin",
        password="SecureBootstrapPass1!",
    )
    assert result["status"] == "created"
    assert result["password_reset"] is False
    n_users = app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert n_users == 1
    n_sites = app.state.db.execute("SELECT COUNT(*) AS c FROM sites").fetchone()["c"]
    assert n_sites == 1
    # No synthetic learners
    synth = app.state.db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username LIKE 'learner-%' OR username LIKE '%-alpha'"
    ).fetchone()["c"]
    assert synth == 0
    client = TestClient(app)
    ok = client.post(
        "/api/v1/auth/login",
        json={
            "username": "root-admin",
            "password": "SecureBootstrapPass1!",
            "site_id": "site-prod",
        },
    )
    assert ok.status_code == 200


def test_bootstrap_admin_second_call_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    app = create_app(db_path=tmp_path / "boot2.sqlite3", seed=False)
    identity: IdentityService = app.state.identity
    first = identity.bootstrap_admin(
        site_id="site-prod",
        site_name="Prod Site",
        username="root-admin",
        display_name="Root Admin",
        password="SecureBootstrapPass1!",
    )
    assert first["status"] == "created"
    second = identity.bootstrap_admin(
        site_id="site-prod",
        site_name="Prod Site",
        username="other-admin",
        display_name="Other",
        password="DifferentPass999!",
    )
    assert second["status"] == "already_bootstrapped"
    assert second["password_reset"] is False
    assert second["username"] == "root-admin"
    client = TestClient(app)
    # Original password still works; new password does not
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "username": "root-admin",
                "password": "SecureBootstrapPass1!",
                "site_id": "site-prod",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "username": "root-admin",
                "password": "DifferentPass999!",
                "site_id": "site-prod",
            },
        ).status_code
        == 401
    )


def test_bootstrap_admin_missing_password_fails(tmp_path, monkeypatch):
    from app.modules.assessment_lifecycle import ServiceError

    monkeypatch.setenv("WAIKE_ROOT", str(_waike()))
    app = create_app(db_path=tmp_path / "boot3.sqlite3", seed=False)
    try:
        app.state.identity.bootstrap_admin(
            site_id="site-prod",
            site_name="Prod",
            username="a",
            display_name="A",
            password="",
        )
        assert False, "expected ServiceError"
    except ServiceError as e:
        assert e.code == "BOOTSTRAP_PASSWORD_REQUIRED"
    assert app.state.db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
