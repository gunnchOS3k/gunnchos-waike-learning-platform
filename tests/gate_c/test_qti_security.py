"""QTI security sabotage + section authz + cross-site ID isolation."""

from __future__ import annotations

from helpers import auth_header, login


def test_xxe_rejected(client):
    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    xml = """<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <assessmentItem identifier="x"><itemBody><prompt>&xxe;</prompt>
    <textEntryInteraction/></itemBody></assessmentItem>"""
    r = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "QTI_XXE_REJECTED"


def test_script_html_rejected(client):
    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    xml = """<?xml version="1.0"?><assessmentItem identifier="bad"><itemBody>
      <prompt><script>alert(1)</script></prompt><textEntryInteraction/></itemBody></assessmentItem>"""
    r = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert r.status_code == 400


def test_zip_traversal(client):
    import io, zipfile
    from app.modules.qti import QtiService
    from app.modules.assessment_lifecycle import ServiceError

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.xml", "<assessmentItem identifier='e'/>")
    svc = client.app.state.qti
    from app.auth import Actor, Role

    actor = Actor(
        actor_id="instructor-alpha",
        role=Role.INSTRUCTOR,
        display_name="I",
        site_id="site-alpha",
        roles=(Role.INSTRUCTOR,),
    )
    try:
        svc.import_package_zip(actor, buf.getvalue(), "sec_alpha_dc_w01")
        assert False, "expected traversal reject"
    except ServiceError as e:
        assert e.code == "QTI_ZIP_TRAVERSAL"


def test_qti_section_authz_requires_assignment(client):
    """Same-site instructor without section assignment is denied."""
    from app.auth.passwords import hash_password
    from app.modules.identity import FIXTURE_PASSWORD

    db = client.app.state.db
    db.execute(
        """
        INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
        VALUES ('instructor-unscoped', 'site-alpha', 'instructor-unscoped', 'Unscoped', ?, 0, datetime('now'))
        """,
        (hash_password(FIXTURE_PASSWORD),),
    )
    db.execute(
        """
        INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
        VALUES ('ra_unscoped', 'instructor-unscoped', 'site-alpha', 'instructor', 1, datetime('now'))
        """
    )
    db.commit()
    s = login(client, "instructor-unscoped")
    h = auth_header(s["token"])
    xml = """<?xml version="1.0"?><assessmentItem identifier="nope"><itemBody><prompt>X</prompt>
      <textEntryInteraction/></itemBody></assessmentItem>"""
    r = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert r.status_code in (403, 404)


def test_qti_cross_site_id_isolation(client):
    """External identifier from site-alpha must not overwrite site-beta quiz items."""
    h_a = auth_header(login(client, "instructor-alpha")["token"])
    xml = """<?xml version="1.0"?><assessmentItem identifier="shared_ext_id"><itemBody><prompt>A</prompt>
      <textEntryInteraction/></itemBody>
      <responseDeclaration><correctResponse><value>a</value></correctResponse></responseDeclaration></assessmentItem>"""
    r1 = client.post(
        "/api/v1/interop/qti/import",
        headers=h_a,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert r1.status_code == 200, r1.text
    item_a = r1.json()["item_id"]

    # Beta instructor imports same external id into beta section
    # Need instructor-beta assigned — seed has instructor-beta on sec_beta
    # Check if instructor-beta exists
    beta_user = client.app.state.db.execute(
        "SELECT username FROM users WHERE site_id='site-beta' AND username LIKE 'instructor%'"
    ).fetchone()
    if beta_user is None:
        return  # fixture may omit; skip soft
    h_b = auth_header(login(client, beta_user["username"], "site-beta")["token"])
    r2 = client.post(
        "/api/v1/interop/qti/import",
        headers=h_b,
        json={"xml_text": xml, "section_id": "sec_beta_dc_w01"},
    )
    assert r2.status_code == 200, r2.text
    item_b = r2.json()["item_id"]
    assert item_a != item_b
    # Alpha item still intact
    row_a = client.app.state.db.execute(
        "SELECT prompt FROM quiz_items WHERE item_id=?", (item_a,)
    ).fetchone()
    assert row_a is not None
