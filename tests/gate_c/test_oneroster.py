"""OneRoster pilot subset + real LMS section/enrollment mapping + revoke."""

from __future__ import annotations

from helpers import auth_header, login


ORGS = """sourcedId,name,status,dateLastModified
org-alpha,Alpha Academy,active,2026-01-01T00:00:00Z
"""

USERS = """sourcedId,username,givenName,familyName,role,status,orgSourcedId
u-learner-1,or_learner,One,Roster,student,active,org-alpha
u-teacher-1,or_teacher,Tea,Cher,teacher,active,org-alpha
"""

COURSES = """sourcedId,title,status
course-dc,Digital Confidence,active
"""

CLASSES = """sourcedId,title,courseSourcedId,status,section_id
class-dc-w01,DC Week 1,course-dc,active,sec_alpha_dc_w01
"""

CLASSES_NEW = """sourcedId,title,courseSourcedId,status,classCode
class-new-01,New Roster Class,course-dc,active,OR-NEW-01
"""

ENROLLMENTS = """sourcedId,userSourcedId,classSourcedId,status
enr-1,u-learner-1,class-dc-w01,active
"""


def _admin(client):
    s = login(client, "admin-alpha")
    return auth_header(s["token"])


def _import_all(client, h, classes_csv=CLASSES):
    for entity, csv_text in [
        ("orgs", ORGS),
        ("users", USERS),
        ("courses", COURSES),
        ("classes", classes_csv),
        ("enrollments", ENROLLMENTS if classes_csv is CLASSES else
         "sourcedId,userSourcedId,classSourcedId,status\nenr-new,u-learner-1,class-new-01,active\n"),
    ]:
        r = client.post(
            "/api/v1/interop/oneroster/import",
            headers=h,
            json={"entity_file": entity, "csv_text": csv_text, "filename": f"{entity}.csv"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rejected"] == 0, r.text


def test_oneroster_matrix(client):
    h = _admin(client)
    r = client.get("/api/v1/interop/oneroster/matrix", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["claim"] == "NOT_FULL_ONEROSTER"
    assert body["supported"]["users"] is True
    assert body["fields"].get("local_section_mapping") is True


def test_oneroster_import_export_round_trip(client):
    h = _admin(client)
    _import_all(client, h)
    r2 = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": ORGS, "filename": "orgs.csv"},
    )
    assert r2.status_code == 200
    # Enable export for privacy gate
    client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )
    ex = client.get("/api/v1/interop/oneroster/export/users", headers=h)
    assert ex.status_code == 200
    assert "u-learner-1" in ex.json()["csv"]
    r3 = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "users", "csv_text": ex.json()["csv"], "filename": "users_rt.csv"},
    )
    assert r3.status_code == 200


def test_oneroster_maps_class_to_real_section(client):
    h = _admin(client)
    for entity, csv_text in [
        ("orgs", ORGS),
        ("users", USERS),
        ("courses", COURSES),
        ("classes", CLASSES_NEW),
    ]:
        r = client.post(
            "/api/v1/interop/oneroster/import",
            headers=h,
            json={"entity_file": entity, "csv_text": csv_text},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rejected"] == 0
    ore = client.app.state.db.execute(
        "SELECT local_ref, payload_json FROM oneroster_entities WHERE entity_type='class' AND sourced_id='class-new-01'"
    ).fetchone()
    assert ore is not None
    assert ore["local_ref"]
    # section_id must not be hidden inside title
    sec = client.app.state.db.execute(
        "SELECT section_id, title, code FROM sections WHERE section_id=?",
        (ore["local_ref"],),
    ).fetchone()
    assert sec is not None
    assert ore["local_ref"] not in (sec["title"] or "")
    assert sec["title"] == "New Roster Class"


def test_oneroster_enrollment_maps_and_revokes(client):
    h = _admin(client)
    _import_all(client, h)
    # Real LMS enrollment exists
    user_ref = client.app.state.db.execute(
        "SELECT local_ref FROM oneroster_entities WHERE entity_type='user' AND sourced_id='u-learner-1'"
    ).fetchone()["local_ref"]
    enr = client.app.state.db.execute(
        "SELECT enrollment_id, status FROM enrollments WHERE user_id=? AND section_id='sec_alpha_dc_w01' AND status='active'",
        (user_ref,),
    ).fetchone()
    assert enr is not None

    # Issue a lease then revoke via inactive enrollment
    lease = client.app.state.db.execute(
        """
        INSERT INTO offline_leases(
          lease_id, user_id, site_id, section_id, device_id,
          issued_at, expires_at, capabilities_json, revoked_at, revoke_reason
        ) VALUES ('lease_or_1', ?, 'site-alpha', 'sec_alpha_dc_w01', 'dev1',
                  datetime('now'), datetime('now','+1 day'), '["sync"]', NULL, NULL)
        """,
        (user_ref,),
    )
    client.app.state.db.commit()

    inactive = """sourcedId,userSourcedId,classSourcedId,status
enr-1,u-learner-1,class-dc-w01,inactive
"""
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "enrollments", "csv_text": inactive},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rejected"] == 0
    enr2 = client.app.state.db.execute(
        "SELECT status FROM enrollments WHERE enrollment_id=?",
        (enr["enrollment_id"],),
    ).fetchone()
    assert enr2["status"] == "inactive"
    lease_row = client.app.state.db.execute(
        "SELECT revoked_at, revoke_reason FROM offline_leases WHERE lease_id='lease_or_1'"
    ).fetchone()
    assert lease_row["revoked_at"] is not None
    assert "oneroster" in (lease_row["revoke_reason"] or "")


def test_oneroster_atomic_reject_no_partial(client):
    h = _admin(client)
    client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": ORGS},
    )
    # One good + one bad user → entire batch rejected, no mutate
    bad_users = """sourcedId,username,givenName,familyName,role,status,orgSourcedId
u-ok,ok_user,Ok,User,student,active,org-alpha
u-bad,bad_user,Bad,Admin,administrator,active,org-alpha
"""
    before = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM oneroster_entities WHERE entity_type='user'"
    ).fetchone()["c"]
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "users", "csv_text": bad_users},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] >= 1
    assert r.json()["created"] == 0
    assert r.json()["report"]["mutated"] is False
    after = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM oneroster_entities WHERE entity_type='user'"
    ).fetchone()["c"]
    assert after == before
    assert (
        client.app.state.db.execute(
            "SELECT 1 FROM users WHERE username='ok_user'"
        ).fetchone()
        is None
    )


def test_oneroster_learner_forbidden(client):
    s = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=auth_header(s["token"]),
        json={"entity_file": "orgs", "csv_text": ORGS},
    )
    assert r.status_code == 403


def test_oneroster_round_trip_compares_lms_tables(client):
    h = _admin(client)
    _import_all(client, h)
    # Compare real sections/enrollments — not only oneroster_entities
    class_ent = client.app.state.db.execute(
        "SELECT local_ref FROM oneroster_entities WHERE entity_type='class' AND sourced_id='class-dc-w01'"
    ).fetchone()
    assert class_ent["local_ref"] == "sec_alpha_dc_w01"
    sec = client.app.state.db.execute(
        "SELECT * FROM sections WHERE section_id=?", (class_ent["local_ref"],)
    ).fetchone()
    assert sec is not None
    user_ref = client.app.state.db.execute(
        "SELECT local_ref FROM oneroster_entities WHERE entity_type='user' AND sourced_id='u-learner-1'"
    ).fetchone()["local_ref"]
    enr = client.app.state.db.execute(
        "SELECT * FROM enrollments WHERE user_id=? AND section_id=? AND status='active'",
        (user_ref, "sec_alpha_dc_w01"),
    ).fetchone()
    assert enr is not None
