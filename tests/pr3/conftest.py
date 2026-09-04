"""Shared PR3 fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))

from app.main import HubConfig, create_app  # noqa: E402
from app.modules.identity import FIXTURE_PASSWORD  # noqa: E402

# Site-scoped fixture usernames (UNIQUE(site_id, username)).
SITE_FOR_USER = {
    "admin-alpha": "site-alpha",
    "instructor-alpha": "site-alpha",
    "grader-alpha": "site-alpha",
    "learner-alpha": "site-alpha",
    "learner-beta": "site-alpha",
    "learner-a": "site-alpha",
    "admin-beta": "site-beta",
    "instructor-beta": "site-beta",
    "learner-gamma": "site-beta",
}


def waike_root() -> Path:
    import os

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


@pytest.fixture()
def prod_app(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(waike_root()))
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    db = tmp_path / "pr3.sqlite3"
    app = create_app(
        HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
        db_path=db,
        seed=True,
    )
    return app


@pytest.fixture()
def client(prod_app):
    return TestClient(prod_app)


def login(
    client: TestClient,
    username: str,
    password: str = FIXTURE_PASSWORD,
    site_id: str | None = None,
) -> dict:
    sid = site_id or SITE_FOR_USER.get(username, "site-alpha")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "site_id": sid},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
