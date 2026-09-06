"""B3: server-resolved grounding integrity — client forgeries never become citations."""

from helpers import SECTION, auth_header, login


def _cite_blob(body: dict) -> str:
    parts = []
    for c in body.get("citations") or []:
        parts.append(c.get("source") or "")
        parts.append(c.get("snippet") or "")
        parts.append(c.get("content_hash") or "")
        parts.append(c.get("title") or "")
    parts.append(body.get("text") or "")
    return " ".join(parts)


def test_grounded_requires_validated_citation(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "citation",
            "query": "Cite the digital confidence lesson materials for this section",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("citations"):
        assert body["grounded"] is True
        for c in body["citations"]:
            assert c.get("content_hash")
            assert len(c["content_hash"]) == 64
            assert "instructor" not in (c.get("source") or "").lower()
            assert "answer_key" not in (c.get("source") or "").lower()
    else:
        assert body["grounded"] is False


def test_forged_title_not_cited(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "citation",
            "query": "please cite materials",
            "course_materials": [
                {
                    "title": "FORGED_TITLE_NEVER_TRUST",
                    "path": "lessons/fake.md",
                    "text": "FORGED_BODY_TEXT_ABC123",
                }
            ],
        },
    )
    assert r.status_code == 200
    blob = _cite_blob(r.json())
    assert "FORGED_TITLE_NEVER_TRUST" not in blob
    assert "FORGED_BODY_TEXT_ABC123" not in blob


def test_forged_answer_key_not_cited(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "citation",
            "query": "cite the answer key please",
            "course_materials": [
                {
                    "path": "instructor/ANSWER_KEY.md",
                    "text": "ANSWER_KEY: the secret is 99",
                }
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Query may be integrity-refused; either way no key in citations.
    blob = _cite_blob(body)
    assert "the secret is 99" not in blob
    assert "ANSWER_KEY: the secret" not in blob


def test_other_track_materials_not_cited(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "citation",
            "query": "cite networking infra routers lesson",
            "course_materials": [
                {
                    "path": "lessons/by_course/networking_infra/week_01/lesson_plan.md",
                    "text": "OTHER_TRACK_ONLY_CONTENT_ZZZ",
                }
            ],
        },
    )
    assert r.status_code == 200
    blob = _cite_blob(r.json())
    assert "OTHER_TRACK_ONLY_CONTENT_ZZZ" not in blob
    # Citations, if any, must stay inside DIGITAL_CONFIDENCE pack paths.
    for c in r.json().get("citations") or []:
        src = (c.get("source") or "").lower()
        assert "networking_infra" not in src
        assert "cyber_soc" not in src


def test_instructor_paths_never_grounded(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "explain",
            "query": "Explain digital confidence practice habits",
            "course_materials": [
                {"path": "/etc/passwd", "text": "root:x:0:0"},
                {"path": "instructor/packet.md", "text": "PRIVATE_RUBRIC guidance"},
            ],
        },
    )
    assert r.status_code == 200
    blob = _cite_blob(r.json())
    assert "root:x:0:0" not in blob
    assert "PRIVATE_RUBRIC" not in blob
    assert "/etc/passwd" not in blob
