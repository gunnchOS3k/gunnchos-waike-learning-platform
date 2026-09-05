"""PR3 → Gate A forward migration."""

from pathlib import Path

from app.db import connect, migrate
from app.main import HubConfig, create_app
from helpers import waike_root


def test_migration_adds_004(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ROOT", str(waike_root()))
    db = tmp_path / "mig.sqlite3"
    # Create app seeds through m004
    app = create_app(HubConfig(production_auth_enabled=True, fixture_auth_enabled=False), db_path=db, seed=False)
    versions = {r[0] for r in app.state.db.execute("SELECT version FROM schema_migrations")}
    assert "003_identity_sections_gradebook" in versions
    assert "004_offline_sync_activities" in versions
    # Tables exist
    tables = {
        r[0]
        for r in app.state.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for t in ("offline_leases", "sync_mutations", "sync_receipts", "quiz_definitions", "lab_definitions"):
        assert t in tables
