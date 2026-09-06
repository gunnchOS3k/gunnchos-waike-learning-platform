"""Gate C test helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.modules.identity import FIXTURE_PASSWORD

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))

SITE_FOR_USER = {
    "admin-alpha": "site-alpha",
    "instructor-alpha": "site-alpha",
    "grader-alpha": "site-alpha",
    "learner-alpha": "site-alpha",
    "admin-beta": "site-beta",
}


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
