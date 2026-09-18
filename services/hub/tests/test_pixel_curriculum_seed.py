"""Full 18-track curriculum seed for Pixel pilot."""

from __future__ import annotations

import os
from pathlib import Path

from app.main import HubConfig, create_app
from app.pilot.full_curriculum_seed import EXPECTED_TRACK_IDS


def test_pixel_pilot_loads_all_18(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    monkeypatch.setenv("WAIKE_SEED_TEST_FIXTURES", "true")
    monkeypatch.setenv(
        "WAIKE_DEV_DB_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    app = create_app(
        config=HubConfig(production_auth_enabled=True, fixture_auth_enabled=False),
        db_path=tmp_path / "pilot.db",
        seed=True,
    )
    inv = app.state.curriculum_inventory
    assert inv is not None
    assert inv["all_18_loaded"] is True
    assert inv["loaded_track_ids"] == list(EXPECTED_TRACK_IDS)
    assert inv["duplicate_sot"] is False
