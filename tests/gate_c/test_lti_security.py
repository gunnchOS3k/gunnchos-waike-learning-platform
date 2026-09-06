"""LTI sabotage suite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.assessment_lifecycle import ServiceError
from app.modules.lti import assert_safe_jwks_url
from helpers import auth_header, login


def _setup(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    r = client.post(
        "/api/v1/interop/lti/registrations",
        headers=h,
        json={
            "issuer": "https://lms.example.test",
            "client_id": "waike-tool-1",
            "deployment_id": "dep-1",
            "auth_login_url": "https://lms.example.test/oidc",
            "auth_token_url": "https://lms.example.test/token",
            "jwks_url": "https://lms.example.test/jwks",
            "target_link_uri": "https://waike.local/lti/launch",
        },
    )
    rid = r.json()["registration_id"]
    init = client.post(f"/api/v1/interop/lti/oidc/init/{rid}").json()["authorization_redirect"]
    return rid, init


def test_wrong_issuer(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], issuer="https://evil.test"
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_WRONG_ISSUER"


def test_wrong_audience(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], audience="other-client"
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_WRONG_AUDIENCE"


def test_expired(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], exp_delta=-10
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_EXPIRED"


def test_state_mismatch(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"]
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": "wrong-state"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_STATE_MISMATCH"


def test_reused_nonce(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"]
    )
    r1 = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r1.status_code == 200
    # new state but same nonce in token
    init2 = client.post(f"/api/v1/interop/lti/oidc/init/{rid}").json()["authorization_redirect"]
    token2 = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], sub="other"
    )
    r2 = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token2, "state": init2["state"]},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] in {"LTI_REUSED_NONCE", "LTI_STATE_MISMATCH"}


def test_wrong_deployment(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], deployment_id="dep-evil"
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_WRONG_DEPLOYMENT"


def test_cross_site_target(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid,
        nonce=init["nonce"],
        roles=["Learner"],
        target_link_uri="https://evil.example/phish",
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_CROSS_SITE_TARGET"


def test_ssrf_jwks_url_blocked(client):
    for bad in (
        "http://lms.example.test/jwks",
        "file:///etc/passwd",
        "https://127.0.0.1/jwks",
        "https://localhost/jwks",
        "https://169.254.169.254/latest/meta-data",
    ):
        try:
            assert_safe_jwks_url(bad, resolve_dns=False)
            assert False, bad
        except ServiceError as e:
            assert e.code == "LTI_JWKS_URL_BLOCKED"


def test_missing_kid(client):
    rid, init = _setup(client)
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"], kid=None
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_MISSING_KID"


def test_expired_state(client):
    rid, init = _setup(client)
    stale = (datetime.now(tz=timezone.utc) - timedelta(minutes=11)).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.app.state.db.execute(
        "UPDATE lti_states SET created_at=? WHERE state=?",
        (stale, init["state"]),
    )
    client.app.state.db.commit()
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid, nonce=init["nonce"], roles=["Learner"]
    )
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_STATE_EXPIRED"


def test_no_silent_test_key_fallback(client):
    """Without fetch_jwks / jwks arg, validation must not call ensure_test_keys."""
    rid, init = _setup(client)
    lti = client.app.state.lti

    def boom(_url: str):
        raise ServiceError("LTI_JWKS_FETCH_FAILED", 400)

    lti.fetch_jwks = boom
    token = lti.mint_test_id_token(registration_id=rid, nonce=init["nonce"], roles=["Learner"])
    r = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "LTI_JWKS_FETCH_FAILED"
