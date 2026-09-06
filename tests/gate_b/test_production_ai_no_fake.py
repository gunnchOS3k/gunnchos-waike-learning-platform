"""Production runtime must not default to FakeGunnchAIProvider (Gate B B1)."""

from __future__ import annotations

from app.modules.assessment_lifecycle import ServiceError
from app.modules.gunnchai_adapter import FakeGunnchAIProvider, GunnchAIAdapter


def test_default_runtime_has_no_fake_ai(monkeypatch):
    """DEFAULT_RUNTIME_HAS_NO_FAKE_AI — unset provider must not select Fake."""
    monkeypatch.delenv("GUNNCHAI_PROVIDER", raising=False)
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    adapter = GunnchAIAdapter()
    assert not isinstance(adapter.provider, FakeGunnchAIProvider)
    meta = adapter.contract_meta()
    label = meta.get("DEFAULT_RUNTIME_HAS_NO_FAKE_AI")
    if label is not None:
        assert label is True
    print("DEFAULT_RUNTIME_HAS_NO_FAKE_AI")


def test_env_fake_without_allow_rejected(monkeypatch):
    """GUNNCHAI_PROVIDER=fake without WAIKE_ALLOW_FAKE_AI=1 must be refused."""
    monkeypatch.setenv("GUNNCHAI_PROVIDER", "fake")
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    try:
        adapter = GunnchAIAdapter()
    except ServiceError as exc:
        assert exc.code in {"AI_FAKE_PROVIDER_FORBIDDEN", "AI_PROVIDER_UNAVAILABLE"}
        return
    except Exception as exc:  # noqa: BLE001 — accept explicit refuse errors from B1
        assert "fake" in str(exc).lower() or "forbidden" in str(exc).lower()
        return
    # Fall-through: adapter constructed but must not activate Fake without allow.
    assert not isinstance(adapter.provider, FakeGunnchAIProvider)
    assert getattr(adapter.provider, "forbidden_fake", False) or not adapter.provider.available()
