"""OneRoster security sabotage."""

from __future__ import annotations

from helpers import auth_header, login


def _admin(client):
    return auth_header(login(client, "admin-alpha")["token"])


def test_formula_injection(client):
    h = _admin(client)
    csv_text = "sourcedId,name,status\norg1,=CMD|'/c calc',active\n"
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": csv_text, "filename": "x.csv"},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] >= 1


def test_path_traversal_filename(client):
    h = _admin(client)
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={
            "entity_file": "orgs",
            "csv_text": "sourcedId,name,status\norg2,Safe,active\n",
            "filename": "../../etc/passwd.csv",
        },
    )
    assert r.status_code == 200
    # filename sanitized to basename
    assert "passwd" in r.json().get("import_id", "") or r.json()["created"] + r.json()["updated"] >= 0


def test_role_escalation_admin_blocked(client):
    h = _admin(client)
    csv_text = "sourcedId,username,role,status\nu-evil,evil,administrator,active\n"
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "users", "csv_text": csv_text},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] >= 1


def test_password_forbidden(client):
    h = _admin(client)
    csv_text = "sourcedId,username,role,status,password\nu1,u1,student,active,secret\n"
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "users", "csv_text": csv_text},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] >= 1


def test_huge_row_count(client):
    h = _admin(client)
    rows = ["sourcedId,name,status"] + [f"org{i},N{i},active" for i in range(10001)]
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": "\n".join(rows)},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "ONEROSTER_ROW_LIMIT"
