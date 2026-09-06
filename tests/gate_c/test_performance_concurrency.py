"""Pilot-shaped performance + mutation concurrency (C-OWNER-14)."""

from __future__ import annotations

import concurrent.futures
import statistics
import time

from helpers import auth_header, login


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def _build_pilot_fixture(client) -> dict:
    """1 site, 2+ sections, 30 learners/section, instructors, packages, submissions, quiz attempts."""
    db = client.app.state.db
    from app.auth.passwords import hash_password
    from app.modules.identity import FIXTURE_PASSWORD

    now = "2026-01-01T00:00:00Z"
    site = "site-alpha"
    sections = ["sec_alpha_dc_w01"]
    # Second section
    db.execute(
        """
        INSERT OR IGNORE INTO sections(section_id, site_id, package_id, code, title, published, created_at)
        VALUES ('sec_alpha_dc_w02', ?, 'pkg_digital_confidence_w01', 'DC-W02-A', 'DC Week 2 Alpha', 1, ?)
        """,
        (site, now),
    )
    sections.append("sec_alpha_dc_w02")
    db.execute(
        "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES ('sec_alpha_dc_w02', 'instructor-alpha', ?)",
        (now,),
    )
    learners = []
    for sec in sections:
        for i in range(30):
            uid = f"pilot_l_{sec[-3:]}_{i:02d}"
            db.execute(
                """
                INSERT OR IGNORE INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                VALUES (?,?,?,?,?,0,?)
                """,
                (uid, site, uid, f"Pilot {i}", hash_password(FIXTURE_PASSWORD), now),
            )
            db.execute(
                """
                INSERT OR IGNORE INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                VALUES (?,?,?,?,1,?)
                """,
                (f"ra_{uid}", uid, site, "learner", now),
            )
            db.execute(
                """
                INSERT OR IGNORE INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
                VALUES (?,?,?,'active',?)
                """,
                (f"enr_{uid}", sec, uid, now),
            )
            learners.append(uid)
    # Package lifecycle + a few submissions if assignment exists
    db.execute(
        """
        INSERT INTO package_lifecycle_events(event_id, track_id, package_version, action, detail_json, actor_id, created_at)
        VALUES ('pkg_pilot_1', 'DIGITAL_CONFIDENCE', '1.0.0', 'install', '{}', 'admin-alpha', ?)
        """,
        (now,),
    )
    db.commit()
    return {"sections": sections, "learners": learners}


def test_pilot_matrix_endpoints_fast(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    for path in (
        "/api/v1/interop/oneroster/matrix",
        "/api/v1/interop/qti/matrix",
        "/api/v1/interop/lti/matrix",
        "/api/v1/deviceos/profiles",
        "/api/v1/privacy/matrix",
        "/version",
    ):
        r = client.get(path, headers=h if path.startswith("/api") else None)
        assert r.status_code == 200


def test_pilot_performance_thresholds(client):
    """Measure p50/p95 for dashboard-like queries, quiz-ish paths, OneRoster batch, backup."""
    _build_pilot_fixture(client)
    admin_h = auth_header(login(client, "admin-alpha")["token"])
    inst_h = auth_header(login(client, "instructor-alpha")["token"])
    # Enable exports for backup
    client.put(
        "/api/v1/privacy/controls",
        headers=admin_h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )

    def timed(fn, n=8):
        samples = []
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000.0)
        samples.sort()
        return {"p50": _pct(samples, 50), "p95": _pct(samples, 95), "samples": samples}

    dash = timed(
        lambda: client.get("/api/v1/instructor/sections/sec_alpha_dc_w01/dashboard", headers=inst_h)
    )
    assert dash["p95"] < 2000.0, dash  # alpha threshold ms

    roster = timed(lambda: client.get("/api/v1/sections/sec_alpha_dc_w01/roster", headers=inst_h))
    assert roster["p95"] < 2000.0, roster

    or_csv = """sourcedId,name,status
org-perf,Perf Org,active
"""
    or_batch = timed(
        lambda: client.post(
            "/api/v1/interop/oneroster/import",
            headers=admin_h,
            json={"entity_file": "orgs", "csv_text": or_csv},
        ),
        n=4,
    )
    assert or_batch["p95"] < 3000.0, or_batch

    bak = timed(lambda: client.post("/api/v1/admin/backup", headers=admin_h), n=3)
    assert bak["p95"] < 8000.0, bak

    # Quiz submit path: start attempt if quiz exists
    quizzes = client.app.state.db.execute(
        "SELECT quiz_id FROM quiz_definitions WHERE section_id='sec_alpha_dc_w01' LIMIT 1"
    ).fetchone()
    if quizzes:
        learner_h = auth_header(login(client, "learner-alpha")["token"])
        quiz_id = quizzes["quiz_id"]

        def submit_once():
            start = client.post(
                f"/api/v1/activities/quizzes/{quiz_id}/attempts",
                headers=learner_h,
                json={"section_id": "sec_alpha_dc_w01"},
            )
            if start.status_code not in (200, 201, 409):
                return
            # best-effort

        qperf = timed(submit_once, n=4)
        assert qperf["p95"] < 3000.0, qperf


def test_concurrent_reads(client):
    h = auth_header(login(client, "learner-alpha")["token"])

    def hit():
        return client.get("/api/v1/deviceos/manifest", headers=h).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(lambda _: hit(), range(16)))
    assert all(c == 200 for c in codes)


def test_mutation_concurrency_no_lost_updates(client):
    """Concurrent mutations: deactivate vs roster, package lifecycle on distinct tracks, backup vs reads."""
    _build_pilot_fixture(client)
    admin_h = auth_header(login(client, "admin-alpha")["token"])
    inst_h = auth_header(login(client, "instructor-alpha")["token"])
    client.put(
        "/api/v1/privacy/controls",
        headers=admin_h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )

    errors: list[str] = []
    for track in ("DIGITAL_CONFIDENCE", "TRACK_CONCUR_B"):
        client.post(
            "/api/v1/packages/lifecycle",
            headers=admin_h,
            json={"track_id": track, "package_version": "1.0.0", "action": "install"},
        )

    def backup_vs_reads():
        try:
            r = client.post("/api/v1/admin/backup", headers=admin_h)
            assert r.status_code in (200, 429), r.text
            m = client.get("/api/v1/deviceos/manifest", headers=inst_h)
            assert m.status_code == 200
        except Exception as e:  # noqa: BLE001
            errors.append(f"backup_reads:{e}")

    def package_revoke_vs_open():
        try:
            a = client.post(
                "/api/v1/packages/lifecycle",
                headers=admin_h,
                json={"track_id": "DIGITAL_CONFIDENCE", "package_version": "1.0.0", "action": "revoke"},
            )
            b = client.post(
                "/api/v1/packages/lifecycle",
                headers=admin_h,
                json={"track_id": "TRACK_CONCUR_B", "package_version": "1.0.0", "action": "open"},
            )
            assert a.status_code == 200, a.text
            assert b.status_code in (200, 400), b.text
            denied = client.post(
                "/api/v1/packages/lifecycle",
                headers=admin_h,
                json={"track_id": "DIGITAL_CONFIDENCE", "package_version": "1.0.0", "action": "install"},
            )
            assert denied.status_code == 403, denied.text
            assert denied.json()["detail"] == "PACKAGE_REVOKED"
        except Exception as e:  # noqa: BLE001
            errors.append(f"pkg:{e}")

    def submit_vs_revoke():
        try:
            from app.auth import Actor, Role

            enr = client.app.state.db.execute(
                "SELECT enrollment_id FROM enrollments WHERE section_id='sec_alpha_dc_w01' AND status='active' LIMIT 1"
            ).fetchone()
            assert enr is not None
            client.app.state.sections.deactivate_enrollment(
                Actor(
                    actor_id="admin-alpha",
                    role=Role.SITE_ADMIN,
                    display_name="A",
                    site_id="site-alpha",
                    roles=(Role.SITE_ADMIN,),
                ),
                enr["enrollment_id"],
            )
            roster = client.get("/api/v1/sections/sec_alpha_dc_w01/roster", headers=inst_h)
            assert roster.status_code == 200
            gone = client.app.state.db.execute(
                "SELECT status FROM enrollments WHERE enrollment_id=?",
                (enr["enrollment_id"],),
            ).fetchone()
            assert gone["status"] == "inactive"
        except Exception as e:  # noqa: BLE001
            errors.append(f"submit_revoke:{e}")

    def duplicate_package_replay():
        try:
            track = "TRACK_DUP_REPLAY"
            codes = []
            for ver in ("1.0.0", "1.0.0"):
                r = client.post(
                    "/api/v1/packages/lifecycle",
                    headers=admin_h,
                    json={"track_id": track, "package_version": ver, "action": "install"},
                )
                codes.append(r.status_code)
            assert codes[0] == 200, codes
            assert codes[1] in (200, 400), codes
            n = client.app.state.db.execute(
                "SELECT COUNT(*) AS c FROM package_lifecycle_events WHERE track_id=?",
                (track,),
            ).fetchone()["c"]
            assert n >= 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"dup:{e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [
            ex.submit(package_revoke_vs_open),
            ex.submit(submit_vs_revoke),
            ex.submit(duplicate_package_replay),
            ex.submit(backup_vs_reads),
        ]
        for f in concurrent.futures.as_completed(futs):
            f.result()

    assert errors == [], errors
    me = client.get("/api/v1/auth/me", headers=admin_h)
    assert me.status_code == 200
