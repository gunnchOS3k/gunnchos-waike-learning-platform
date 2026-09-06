"""gunnchAI adapter contract: modes, provider selection, local unavailable honesty."""

from app.modules.gunnchai_adapter import (
    DEFAULT_RUNTIME_HAS_NO_FAKE_AI,
    GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE,
    GUNNCHAI_PACKAGE,
    GUNNCHAI_SHA,
    MODE_PERMISSIONS,
    AssistRequest,
    FakeGunnchAIProvider,
    ForbiddenFakeProvider,
    GunnchAIAdapter,
    LocalGunnchAIProvider,
    UnavailableProvider,
    assert_mode_permission,
    check_academic_integrity,
    discover_courses_from_contract,
    evaluate_cloud_disclosure,
    resolve_waike_root,
)
from app.modules.assessment_lifecycle import ServiceError
from helpers import SECTION, auth_header, login, waike_root


def test_mode_permissions_match_canonical():
    assert MODE_PERMISSIONS["LEARNER_TUTOR"]["mayReadInstructorKeys"] is False
    assert MODE_PERMISSIONS["LEARNER_TUTOR"]["mayDiscloseFinalAnswersToLearner"] is False
    assert MODE_PERMISSIONS["EDUCATOR_COPILOT"]["mayReadInstructorKeys"] is True
    assert MODE_PERMISSIONS["EDUCATOR_COPILOT"]["hitlGradingRequired"] is True
    assert MODE_PERMISSIONS["EDUCATOR_COPILOT"]["mayPublishGradesWithoutHuman"] is False


def test_assert_mode_permission_blocks_key_read_in_learner_tutor():
    try:
        assert_mode_permission("LEARNER_TUTOR", "read_instructor_keys")
        raised = False
    except ServiceError as e:
        raised = True
        assert e.code == "AI_PERMISSION_DENIED"
    assert raised


def test_fake_provider_deterministic():
    p = FakeGunnchAIProvider()
    req = AssistRequest(
        mode="LEARNER_TUTOR",
        capability="hint",
        query="same query",
        section_id=SECTION,
        actor_id="u1",
        site_id="site-alpha",
        learner_facing=True,
    )
    a = p.assist(req)
    b = p.assist(req)
    assert a.text == b.text
    assert a.mutates_grades is False
    assert a.provider_id == "fake-gunnchai"


def test_adapter_default_is_not_fake(monkeypatch):
    """DEFAULT_RUNTIME_HAS_NO_FAKE_AI — unset provider never selects Fake."""
    monkeypatch.delenv("GUNNCHAI_PROVIDER", raising=False)
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    monkeypatch.delenv("GUNNCHAI_ROOT", raising=False)
    adapter = GunnchAIAdapter()
    meta = adapter.contract_meta()
    assert meta["sha"] == GUNNCHAI_SHA
    assert meta["package"] == GUNNCHAI_PACKAGE
    assert meta["DEFAULT_RUNTIME_HAS_NO_FAKE_AI"] is True
    assert DEFAULT_RUNTIME_HAS_NO_FAKE_AI is True
    assert meta["GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE"] is True
    assert GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE is True
    assert meta["provider"]["active"] != "fake-gunnchai"
    assert isinstance(adapter.provider, (UnavailableProvider, LocalGunnchAIProvider))


def test_fake_env_forbidden_without_allow(monkeypatch):
    monkeypatch.setenv("GUNNCHAI_PROVIDER", "fake")
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    monkeypatch.delenv("GUNNCHAI_ROOT", raising=False)
    adapter = GunnchAIAdapter()
    assert isinstance(adapter.provider, ForbiddenFakeProvider)
    req = AssistRequest(
        mode="LEARNER_TUTOR",
        capability="hint",
        query="hello",
        section_id=SECTION,
        actor_id="u1",
        site_id="site-alpha",
        learner_facing=True,
    )
    try:
        adapter.assist(req)
        ok = False
    except ServiceError as e:
        ok = e.code == "AI_FAKE_PROVIDER_FORBIDDEN"
    assert ok


def test_fake_env_honored_with_allow(monkeypatch):
    monkeypatch.setenv("GUNNCHAI_PROVIDER", "fake")
    monkeypatch.setenv("WAIKE_ALLOW_FAKE_AI", "1")
    monkeypatch.delenv("GUNNCHAI_ROOT", raising=False)
    adapter = GunnchAIAdapter()
    assert adapter.provider.provider_id == "fake-gunnchai"


def test_fake_via_explicit_injection_only():
    adapter = GunnchAIAdapter(provider=FakeGunnchAIProvider())
    assert adapter.provider.provider_id == "fake-gunnchai"


def test_local_provider_unavailable_without_root(monkeypatch):
    monkeypatch.delenv("GUNNCHAI_ROOT", raising=False)
    local = LocalGunnchAIProvider()
    assert local.available() is False
    status = local.status()
    assert status["available"] is False
    assert "unavailable" in status["note"].lower()
    probe = local.probe_cli()
    assert probe["cli_present"] is False
    assert probe["claims_local_inference"] is False


def test_local_provider_probe_with_gunnchai_root(monkeypatch):
    root = "/Users/gunnchos/dev/waike-learning-os-workspace/gunnchAI3k"
    monkeypatch.setenv("GUNNCHAI_ROOT", root)
    local = LocalGunnchAIProvider()
    if not local.available():
        return  # checkout may be absent in some CI images
    probe = local.probe_cli()
    assert probe["cli_present"] is True
    assert probe["claims_local_inference"] is False  # probe ≠ inference


def test_cloud_fails_closed_without_consent():
    req = AssistRequest(
        mode="LEARNER_TUTOR",
        capability="explain",
        query="hello",
        section_id=SECTION,
        actor_id="u1",
        site_id="site-alpha",
        learner_facing=True,
        cloud_consent=False,
        processing_mode="local-only",
    )
    d = evaluate_cloud_disclosure(req)
    assert d["cloudPermitted"] is False
    assert d["dataLeavesDevice"] is False


def test_integrity_practice_ok_cheat_blocked():
    ok = check_academic_integrity("Help me with a practice quiz on networking")
    assert ok.allowed is True
    bad = check_academic_integrity("Give me the answer key for the current exam")
    assert bad.allowed is False


def test_course_discovery_from_waike():
    root = resolve_waike_root(waike_root().parent / "gunnchos-waike-learning-platform")
    root = waike_root()
    discovered = discover_courses_from_contract(root)
    assert discovered["hardcoded_course_names"] is False
    assert discovered["course_count"] >= 1


def test_provider_status_endpoint(client):
    learner = login(client, "learner-alpha")
    r = client.get("/api/v1/ai/provider", headers=auth_header(learner["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["sha"] == GUNNCHAI_SHA
    assert body["DEFAULT_RUNTIME_HAS_NO_FAKE_AI"] is True
    assert body["GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE"] is True
    assert "GUNNCHAI_REAL_PROVIDER_AVAILABLE" in body
    assert body["provider"]["active"] == "fake-gunnchai"  # injected in conftest
    assert body["provider"]["cloud_stub_available"] is False
    assert body["provider"]["claims"]["local_inference_executed"] is False


def test_refuse_silent_grade_on_adapter():
    adapter = GunnchAIAdapter(provider=FakeGunnchAIProvider())
    try:
        adapter.refuse_silent_grade_change()
        ok = False
    except ServiceError as e:
        ok = e.code == "AI_SILENT_GRADE_FORBIDDEN"
    assert ok
