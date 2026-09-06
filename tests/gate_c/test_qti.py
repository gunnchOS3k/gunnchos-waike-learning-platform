"""QTI 3 subset round-trip + section auth + ID isolation."""

from __future__ import annotations

from helpers import auth_header, login

SC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<assessmentItem identifier="qti_sc_1" title="SC">
  <itemBody><prompt>Pick one</prompt>
    <choiceInteraction responseIdentifier="RESPONSE" cardinality="single">
      <simpleChoice identifier="a">A</simpleChoice>
      <simpleChoice identifier="b">B</simpleChoice>
    </choiceInteraction>
  </itemBody>
  <responseDeclaration identifier="RESPONSE"><correctResponse><value>b</value></correctResponse></responseDeclaration>
</assessmentItem>
"""

QTI3_NS = "http://www.imsglobal.org/xsd/imsqtiasi_v3p0"


def test_qti_matrix_and_round_trip(client):
    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    # Enable export
    ah = auth_header(login(client, "admin-alpha")["token"])
    client.put(
        "/api/v1/privacy/controls",
        headers=ah,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )
    m = client.get("/api/v1/interop/qti/matrix", headers=h)
    assert m.status_code == 200
    assert m.json()["claim"] == "NOT_FULL_QTI"
    assert m.json()["xmlns"] == QTI3_NS
    imp = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": SC_XML, "section_id": "sec_alpha_dc_w01"},
    )
    assert imp.status_code == 200, imp.text
    item_id = imp.json()["item_id"]
    assert item_id != "qti_sc_1" or imp.json()["item"]["external_identifier"] == "qti_sc_1"
    # external stored separately
    row = client.app.state.db.execute(
        "SELECT item_id, external_identifier FROM quiz_items WHERE item_id=?",
        (item_id,),
    ).fetchone()
    assert row["external_identifier"] == "qti_sc_1"
    ex = client.get(f"/api/v1/interop/qti/export/{item_id}", headers=h)
    assert ex.status_code == 200
    assert QTI3_NS in ex.json()["xml"]
    assert "choiceInteraction" in ex.json()["xml"]
    imp2 = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": ex.json()["xml"], "section_id": "sec_alpha_dc_w01", "quiz_id": imp.json()["quiz_id"]},
    )
    assert imp2.status_code == 200


def test_qti_all_supported_types(client):
    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    fixtures = {
        "multi": """<?xml version="1.0"?><assessmentItem identifier="qti_ms"><itemBody><prompt>MS</prompt>
          <choiceInteraction cardinality="multiple"><simpleChoice identifier="a">A</simpleChoice>
          <simpleChoice identifier="c">C</simpleChoice></choiceInteraction></itemBody>
          <responseDeclaration><correctResponse><value>a</value><value>c</value></correctResponse></responseDeclaration></assessmentItem>""",
        "tf": """<?xml version="1.0"?><assessmentItem identifier="qti_tf"><itemBody><prompt>TF</prompt>
          <choiceInteraction cardinality="single"><simpleChoice identifier="true">T</simpleChoice>
          <simpleChoice identifier="false">F</simpleChoice></choiceInteraction></itemBody>
          <responseDeclaration><correctResponse><value>true</value></correctResponse></responseDeclaration></assessmentItem>""",
        "short": """<?xml version="1.0"?><assessmentItem identifier="qti_short"><itemBody><prompt>Short</prompt>
          <textEntryInteraction responseIdentifier="RESPONSE"/></itemBody>
          <responseDeclaration><correctResponse><value>hello</value></correctResponse></responseDeclaration></assessmentItem>""",
        "num": """<?xml version="1.0"?><assessmentItem identifier="qti_num"><itemBody><prompt>Num</prompt>
          <extendedTextInteraction responseIdentifier="RESPONSE"/></itemBody>
          <responseDeclaration baseType="float"><correctResponse><value>42</value></correctResponse></responseDeclaration></assessmentItem>""",
        "file": """<?xml version="1.0"?><assessmentItem identifier="qti_file"><itemBody><prompt>File</prompt>
          <uploadInteraction responseIdentifier="RESPONSE"/></itemBody>
          <responseDeclaration><correctResponse></correctResponse></responseDeclaration></assessmentItem>""",
    }
    for xml in fixtures.values():
        r = client.post(
            "/api/v1/interop/qti/import",
            headers=h,
            json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
        )
        assert r.status_code == 200, r.text


def test_qti_malformed_numeric_rejected(client):
    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    xml = """<?xml version="1.0"?><assessmentItem identifier="qti_bad_num"><itemBody><prompt>Num</prompt>
      <extendedTextInteraction responseIdentifier="RESPONSE"/></itemBody>
      <responseDeclaration baseType="float"><correctResponse><value>not-a-number</value></correctResponse></responseDeclaration></assessmentItem>"""
    r = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": xml, "section_id": "sec_alpha_dc_w01"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "QTI_MALFORMED_NUMERIC"


def test_qti_semantic_round_trip_service(client):
    from app.auth import Actor, Role

    s = login(client, "instructor-alpha")
    h = auth_header(s["token"])
    ah = auth_header(login(client, "admin-alpha")["token"])
    client.put(
        "/api/v1/privacy/controls",
        headers=ah,
        json={"youth_mode": False, "data_minimization": True, "export_allowed": True, "retention_days": 365},
    )
    imp = client.post(
        "/api/v1/interop/qti/import",
        headers=h,
        json={"xml_text": SC_XML, "section_id": "sec_alpha_dc_w01"},
    )
    assert imp.status_code == 200
    actor = Actor(
        actor_id="instructor-alpha",
        role=Role.INSTRUCTOR,
        display_name="I",
        site_id="site-alpha",
        roles=(Role.INSTRUCTOR,),
    )
    rt = client.app.state.qti.round_trip_semantic(actor, imp.json()["item_id"])
    assert rt["type_match"] is True
    assert rt["prompt_match"] is True
    assert rt["xmlns"] == QTI3_NS
