"""Importable Gate A helpers (conftest fixtures stay in conftest.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.modules.identity import FIXTURE_PASSWORD

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

SECTION = "sec_alpha_dc_w01"


def login(client: TestClient, username: str, site_id: str | None = None) -> dict:
    sid = site_id or SITE_FOR_USER.get(username, "site-alpha")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": FIXTURE_PASSWORD, "site_id": sid},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def user_id(session: dict) -> str:
    return session["user"]["user_id"]


def waike_root():
    import os
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
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
