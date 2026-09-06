"""Shared Gate B fixtures (auth + 18-track pack roots)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
COMPILER = ROOT / "tools" / "course_compiler"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))
if str(COMPILER) not in sys.path:
    sys.path.insert(0, str(COMPILER))

from app.main import HubConfig, create_app  # noqa: E402
from app.modules.identity import FIXTURE_PASSWORD  # noqa: E402
from course_compiler.compiler import compile_all  # noqa: E402
from course_compiler.tracks import CANONICAL_TRACK_IDS  # noqa: E402

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
PACK_OUT_18 = ROOT / "pack_out_18"


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


def _packs_complete(root: Path) -> bool:
    return all((root / tid / "learner_pack_manifest.json").is_file() for tid in CANONICAL_TRACK_IDS)


@pytest.fixture(scope="session")
def packs_18(tmp_path_factory):
    """Reuse pack_out_18 when present; otherwise compile all 18 once per session."""
    if _packs_complete(PACK_OUT_18):
        return PACK_OUT_18
    out = tmp_path_factory.mktemp("pack_out_18")
    results = compile_all(tracks=list(CANONICAL_TRACK_IDS), out_root=out)
    assert results["ok"] is True, results.get("failures")
    return out


@pytest.fixture()
def prod_app(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(waike_root()))
    # Do NOT set GUNNCHAI_PROVIDER=fake as the production default path.
    # Inject Fake explicitly for gate_b assist tests that need responses.
    monkeypatch.delenv("GUNNCHAI_PROVIDER", raising=False)
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    monkeypatch.delenv("GUNNCHAI_ROOT", raising=False)
    # Point grounding resolver at compiled pack_out_18 when present.
    pack_out = ROOT / "pack_out_18"
    if pack_out.is_dir():
        monkeypatch.setenv("WAIKE_PACK_OUT", str(pack_out))
    db = tmp_path / "gate_b_ai.sqlite3"
    app = create_app(
        HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
        db_path=db,
        seed=True,
    )
    from app.modules.gunnchai_adapter import FakeGunnchAIProvider, GunnchAIAdapter

    app.state.ai.adapter = GunnchAIAdapter(provider=FakeGunnchAIProvider())
    return app


@pytest.fixture()
def client(prod_app):
    return TestClient(prod_app)


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
