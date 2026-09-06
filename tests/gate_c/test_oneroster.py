"""OneRoster pilot subset + round-trip."""

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

ENROLLMENTS = """sourcedId,userSourcedId,classSourcedId,status
enr-1,u-learner-1,class-dc-w01,active
"""


def _admin(client):
    s = login(client, "admin-alpha")
    return auth_header(s["token"])


def test_oneroster_matrix(client):
    h = _admin(client)
    r = client.get("/api/v1/interop/oneroster/matrix", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["claim"] == "NOT_FULL_ONEROSTER"
    assert body["supported"]["users"] is True


def test_oneroster_import_export_round_trip(client):
    h = _admin(client)
    for entity, csv_text in [
        ("orgs", ORGS),
        ("users", USERS),
        ("courses", COURSES),
        ("classes", CLASSES),
        ("enrollments", ENROLLMENTS),
    ]:
        r = client.post(
            "/api/v1/interop/oneroster/import",
            headers=h,
            json={"entity_file": entity, "csv_text": csv_text, "filename": f"{entity}.csv"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rejected"] == 0
    # idempotent re-import
    r2 = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": ORGS, "filename": "orgs.csv"},
    )
    assert r2.status_code == 200
    # export
    ex = client.get("/api/v1/interop/oneroster/export/users", headers=h)
    assert ex.status_code == 200
    assert "u-learner-1" in ex.json()["csv"]
    # clean re-import of export
    r3 = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "users", "csv_text": ex.json()["csv"], "filename": "users_rt.csv"},
    )
    assert r3.status_code == 200


def test_oneroster_learner_forbidden(client):
    s = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=auth_header(s["token"]),
        json={"entity_file": "orgs", "csv_text": ORGS},
    )
    assert r.status_code == 403
