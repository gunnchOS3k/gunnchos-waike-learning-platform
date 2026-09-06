"""Hardening: privacy behavior, admin, rate limit, observability, packages, migration, diagnostics truth."""

from __future__ import annotations

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
    body = diag.json()
    assert "006_gate_c" in body["schema_migrations"] or "005_ai_policy" in body["schema_migrations"]
    assert "subsystems" in body
    assert body["redaction"] is True


def test_privacy_export_blocks_oneroster_qti_backup(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": False, "retention_days": 365},
    )
    # OneRoster export blocked
    r = client.get("/api/v1/interop/oneroster/export/users", headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "PRIVACY_EXPORT_BLOCKED"
    # Backup blocked
    b = client.post("/api/v1/admin/backup", headers=h)
    assert b.status_code == 403
    assert b.json()["detail"] == "PRIVACY_EXPORT_BLOCKED"
    # QTI export blocked (need an item first with export enabled, then disable)
    client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )
    ih = auth_header(login(client, "instructor-alpha")["token"])
    xml = """<?xml version="1.0"?><assessmentItem identifier="priv_q"><itemBody><prompt>P</prompt>
      <textEntryInteraction/></itemBody>
      <responseDeclaration><correctResponse><value>x</value></correctResponse></responseDeclaration></assessmentItem>"""
    imp = client.post(
        "/api/v1/interop/qti/import",
        headers=ih,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert imp.status_code == 200
    client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": False, "retention_days": 365},
    )
    ex = client.get(f"/api/v1/interop/qti/export/{imp.json()['item_id']}", headers=ih)
    assert ex.status_code == 403


def test_privacy_youth_mode_minimizes_pii(client):
    from app.modules.hardening import minimize_pii

    out = minimize_pii(
        {"display_name": "Alice", "score": 10, "email": "a@x.com"},
        youth_mode=True,
        data_minimization=True,
    )
    assert out["display_name"] == "[YOUTH_REDACTED]"
    assert out["email"] == "[YOUTH_REDACTED]"
    assert out["score"] == 10


def test_privacy_deactivate_revokes_sessions_and_leases(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    # Login learner to create session
    learner = login(client, "learner-alpha")
    uid = learner["user"]["user_id"]
    client.app.state.db.execute(
        """
        INSERT INTO offline_leases(
          lease_id, user_id, site_id, section_id, device_id,
          issued_at, expires_at, capabilities_json
        ) VALUES ('lease_priv_1', ?, 'site-alpha', 'sec_alpha_dc_w01', 'dev',
                  datetime('now'), datetime('now','+1 day'), '[]')
        """,
        (uid,),
    )
    client.app.state.db.commit()
    r = client.post(f"/api/v1/privacy/deactivate/{uid}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["disabled"] is True
    assert r.json()["leases_revoked"] >= 1
    user = client.app.state.db.execute("SELECT disabled FROM users WHERE user_id=?", (uid,)).fetchone()
    assert int(user["disabled"]) == 1
    sess = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM sessions WHERE user_id=? AND revoked=0", (uid,)
    ).fetchone()
    assert sess["c"] == 0


def test_privacy_retention_dry_run_and_apply(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    dry = client.post("/api/v1/privacy/retention", headers=h)
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert dry.json()["ferpa_claim"] is False
    applied = client.post("/api/v1/privacy/retention?apply=true", headers=h)
    assert applied.status_code == 200
    assert applied.json()["applied"] is True


def test_ferpa_claim_stays_false(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    p = client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": True, "data_minimization": True, "export_allowed": True, "retention_days": 30},
    )
    assert p.json()["ferpa_claim"] is False
    m = client.get("/api/v1/privacy/matrix", headers=h)
    assert m.json()["ferpa_claim"] is False


def test_diagnostics_truthful_never_ok_when_broken(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    # Force a broken subsystem by pointing storage path at a non-file and clearing deviceos
    obs = client.app.state.observability
    obs.db_path = None
    obs.deviceos = None
    obs.waike_root = None
    obs.gunnchai_root = None
    # Also force db integrity probe to still work; unavailable subsystems must spoil global OK
    diag = obs.diagnostics(
        __import__("app.auth", fromlist=["Actor", "Role"]).Actor(
            actor_id="admin-alpha",
            role=__import__("app.auth", fromlist=["Role"]).Role.SITE_ADMIN,
            display_name="A",
            site_id="site-alpha",
            roles=(__import__("app.auth", fromlist=["Role"]).Role.SITE_ADMIN,),
        )
    )
    assert diag["health"] != "ok"
    names = {s["name"]: s["status"] for s in diag["subsystems"]}
    assert names["deviceos_contracts"] == "unavailable"
    assert "redacted_bundle" in diag


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
    assert "007_gate_c_owner" in versions


def test_observability_emit(client):
    eid = client.app.state.observability.emit(
        "info", "gate_c", "hello", {"password": "no", "x": 1}
    )
    row = client.app.state.db.execute(
        "SELECT redacted_detail_json FROM observability_events WHERE event_id=?", (eid,)
    ).fetchone()
    assert "no" not in row["redacted_detail_json"] or "[REDACTED]" in row["redacted_detail_json"]
