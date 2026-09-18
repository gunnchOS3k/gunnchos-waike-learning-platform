"""Pixel pilot curriculum seed + CORS exact-origin tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cors_origins import hub_allow_origins
from app.main import HubConfig, create_app
from app.pilot.full_curriculum_seed import (
    EXPECTED_TRACK_IDS,
    CurriculumLoadError,
    inventory_from_db,
    load_registry,
    seed_full_curriculum,
)

ROOT = Path(__file__).resolve().parents[2]


def test_registry_has_exact_18_tracks():
    meta = load_registry(ROOT)
    assert [t["track_id"] for t in meta["tracks"]] == list(EXPECTED_TRACK_IDS)


def test_seed_full_curriculum_loads_all_18(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(ROOT))
    monkeypatch.delenv("WAIKE_PIXEL_PILOT", raising=False)
    monkeypatch.delenv("WAIKE_SEED_TEST_FIXTURES", raising=False)
    monkeypatch.delenv("WAIKE_FIXTURE_AUTH", raising=False)
    app = create_app(
        config=HubConfig(fixture_auth_enabled=False, production_auth_enabled=True),
        db_path=tmp_path / "hub.sqlite3",
        seed=False,
    )
    inv = seed_full_curriculum(app.state.db)
    assert inv["all_18_loaded"] is True
    assert inv["loaded_track_ids"] == list(EXPECTED_TRACK_IDS)
    assert inv["duplicate_sot"] is False
    again = inventory_from_db(app.state.db)
    assert again["all_18_loaded"] is True


def test_pixel_cors_includes_loopback_not_wildcard(monkeypatch):
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    origins = hub_allow_origins()
    assert "*" not in origins
    assert "http://127.0.0.1:1420" in origins
    assert "http://ipc.localhost" in origins


def test_pixel_cors_rejects_wildcard_env(monkeypatch):
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    monkeypatch.setenv("WAIKE_PIXEL_PILOT_ORIGINS", "http://evil.example,*")
    with pytest.raises(ValueError, match="CORS_WILDCARD"):
        hub_allow_origins()


def test_pixel_loopback_cors_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    app = create_app(
        config=HubConfig(fixture_auth_enabled=False, production_auth_enabled=True),
        db_path=tmp_path / "hub.sqlite3",
        seed=False,
    )
    client = TestClient(app)
    r = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://127.0.0.1:1420",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:1420"
