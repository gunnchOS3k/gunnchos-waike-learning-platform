"""QTI security sabotage."""

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
    svc = QtiService(client.app.state.db)
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
