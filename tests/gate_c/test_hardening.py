"""Hardening: privacy, admin, rate limit, observability, packages, migration."""

from __future__ import annotations

from pathlib import Path

from helpers import auth_header, login


def test_admin_privacy_diagnostics(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    d = client.get("/api/v1/admin/dashboard", headers=h)
    assert d.status_code == 200
    assert "backup_restore" in d.json()["workflows"]
    p = client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": True, "data_minimization": True, "export_allowed": False, "retention_days": 180},
    )
    assert p.status_code == 200
    assert p.json()["ferpa_claim"] is False
    assert p.json()["controls"]["youth_mode"] is True
    diag = client.get("/api/v1/diagnostics", headers=h)
    assert diag.status_code == 200
    assert "006_gate_c" in diag.json()["schema_migrations"] or "005_ai_policy" in diag.json()["schema_migrations"]


def test_rate_limit(client):
    from app.modules.assessment_lifecycle import ServiceError

    lim = client.app.state.rate_limiter
    lim.limit = 5
    key = "test-burst"
    for _ in range(5):
        lim.check(key)
    try:
        lim.check(key)
        assert False
    except ServiceError as e:
        assert e.code == "RATE_LIMITED"


def test_redaction(client):
    from app.modules.hardening import redact_obj, redact_text

    assert "[REDACTED]" in redact_text("password=supersecret")
    assert redact_obj({"token": "abc", "ok": "yes"})["token"] == "[REDACTED]"


def test_package_lifecycle_downgrade_blocked(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    r = client.post(
        "/api/v1/packages/lifecycle",
        headers=h,
        json={"track_id": "DIGITAL_CONFIDENCE", "package_version": "2.0.0", "action": "install"},
    )
    assert r.status_code == 200
    blocked = client.app.state.packages.assert_no_silent_downgrade(
        "DIGITAL_CONFIDENCE", "2.0.0", "1.0.0"
    )
    assert blocked["action"] == "downgrade_blocked"


def test_migration_ladder_gate_c_present(client):
    versions = [
        r[0]
        for r in client.app.state.db.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert "001_assessment_lifecycle" in versions
    assert "004_offline_sync_activities" in versions
    assert "005_ai_policy" in versions
    assert "006_gate_c" in versions


def test_observability_emit(client):
    eid = client.app.state.observability.emit(
        "info", "gate_c", "hello", {"password": "no", "x": 1}
    )
    row = client.app.state.db.execute(
        "SELECT redacted_detail_json FROM observability_events WHERE event_id=?", (eid,)
    ).fetchone()
    assert "no" not in row["redacted_detail_json"] or "[REDACTED]" in row["redacted_detail_json"]
