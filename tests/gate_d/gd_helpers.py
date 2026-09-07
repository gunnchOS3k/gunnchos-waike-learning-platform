"""Gate D helpers."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.modules.identity import FIXTURE_PASSWORD

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"

SITE_FOR_USER = {
    "admin-alpha": "site-alpha",
    "instructor-alpha": "site-alpha",
    "grader-alpha": "site-alpha",
    "guardian-alpha": "site-alpha",
    "learner-alpha": "site-alpha",
    "learner-beta": "site-alpha",
    "admin-beta": "site-beta",
    "instructor-beta": "site-beta",
    "learner-gamma": "site-beta",
}

SECTION = "sec_alpha_dc_w01"

PINS = {
    "device_os": "4f02a48780d300a5d3a7758937b20e3bf9364d0d",
    "waike": "fbf7685bc5686201ccaa0128ee83346d59b3d584",
    "gunnchai": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
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


def user_id(session: dict) -> str:
    return session["user"]["user_id"]


def write_json(name: str, data: dict) -> Path:
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / name
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
