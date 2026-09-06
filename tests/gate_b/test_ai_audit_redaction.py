"""Audit redaction: ai_assist_audit never stores raw query / keys / bodies."""

import json

from helpers import SECTION, auth_header, login, user_id


def test_audit_stores_query_hash_not_query(client, prod_app):
    learner = login(client, "learner-alpha")
    secret_query = "UNIQUE_AUDIT_QUERY_TOKEN_SHOULD_NOT_PERSIST_XYZ"
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={
            "section_id": SECTION,
            "capability": "hint",
            "query": secret_query,
        },
    )
    assert r.status_code == 200, r.text
    rows = prod_app.state.db.execute(
        """
        SELECT query_hash, detail_json, capability, actor_id
        FROM ai_assist_audit
        WHERE actor_id=?
        ORDER BY created_at DESC LIMIT 5
        """,
        (user_id(learner),),
    ).fetchall()
    assert rows
    for row in rows:
        assert row["query_hash"]
        assert secret_query not in (row["query_hash"] or "")
        detail = json.loads(row["detail_json"] or "{}")
        dumped = json.dumps(detail)
        assert secret_query not in dumped
        assert "password" not in dumped.lower() or "[redacted]" in dumped
        for key in ("query", "answer_key", "instructor_context", "course_materials", "body"):
            if key in detail:
                assert detail[key] == "[redacted]"


def test_public_detail_scrubs_query(client, prod_app):
    from app.modules.gunnchai_adapter import AssistResponse, GunnchAIAdapter

    class LeakDetail:
        provider_id = "leak"

        def available(self):
            return True

        def assist(self, req):
            return AssistResponse(
                ok=True,
                text="ok",
                grounded=False,
                citations=[],
                provider_id=self.provider_id,
                mode=req.mode,
                capability=req.capability,
                disclosure="local",
                detail={"query": req.query, "query_hash": "abc", "refused": False},
            )

    prod_app.state.ai.adapter = GunnchAIAdapter(provider=LeakDetail())
    learner = login(client, "learner-alpha")
    q = "SHOULD_NOT_APPEAR_IN_PUBLIC_DETAIL"
    r = client.post(
        "/api/v1/ai/learner/assist",
        headers=auth_header(learner["token"]),
        json={"section_id": SECTION, "capability": "hint", "query": q},
    )
    assert r.status_code == 200
    body = r.json()
    assert q not in json.dumps(body.get("detail") or {})
    assert "query" not in (body.get("detail") or {})


def test_write_audit_redacts_sensitive_keys(prod_app):
    from app.auth import Actor, Role

    ai = prod_app.state.ai
    actor = Actor(
        actor_id="learner-alpha",
        role=Role.LEARNER,
        display_name="Learner Alpha",
        site_id="site-alpha",
        roles=(Role.LEARNER,),
        username="learner-alpha",
    )
    ai._write_audit(
        actor,
        section_id=SECTION,
        mode="LEARNER_TUTOR",
        capability="hint",
        policy="AI_ALLOWED",
        allowed=1,
        refusal_code=None,
        query_hash="deadbeef",
        provider_id="fake-gunnchai",
        detail={
            "query": "raw question text",
            "answer_key": "SECRET_KEY",
            "instructor_context": {"key": "x"},
            "api_key": "sk-test",
            "safe_flag": True,
        },
    )
    row = prod_app.state.db.execute(
        "SELECT detail_json FROM ai_assist_audit WHERE query_hash='deadbeef' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    detail = json.loads(row["detail_json"])
    assert detail["query"] == "[redacted]"
    assert detail["answer_key"] == "[redacted]"
    assert detail["instructor_context"] == "[redacted]"
    assert detail["api_key"] == "[redacted]"
    assert detail["safe_flag"] is True
