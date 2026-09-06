"""LTI sabotage suite."""

from __future__ import annotations

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
