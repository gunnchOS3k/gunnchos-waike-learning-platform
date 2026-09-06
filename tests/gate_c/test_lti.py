"""LTI 1.3 foundation tests."""

from __future__ import annotations

from helpers import auth_header, login


def _register(client):
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
    assert r.status_code == 200, r.text
    return r.json()["registration_id"]


def test_lti_matrix_and_valid_launch(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    m = client.get("/api/v1/interop/lti/matrix", headers=h)
    assert m.json()["claim"] == "NOT_LTI_CERTIFIED"
    rid = _register(client)
    init = client.post(f"/api/v1/interop/lti/oidc/init/{rid}")
    assert init.status_code == 200
    state = init.json()["authorization_redirect"]["state"]
    nonce = init.json()["authorization_redirect"]["nonce"]
    lti = client.app.state.lti
    token = lti.mint_test_id_token(
        registration_id=rid,
        nonce=nonce,
        roles=["http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"],
    )
    launch = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": state},
    )
    assert launch.status_code == 200, launch.text
    assert launch.json()["mapped_role"] == "learner"
    assert launch.json()["certification_claim"] is False


def test_lti_admin_role_capped(client):
    rid = _register(client)
    init = client.post(f"/api/v1/interop/lti/oidc/init/{rid}").json()["authorization_redirect"]
    token = client.app.state.lti.mint_test_id_token(
        registration_id=rid,
        nonce=init["nonce"],
        roles=["Administrator"],
    )
    launch = client.post(
        "/api/v1/interop/lti/launch",
        json={"registration_id": rid, "id_token": token, "state": init["state"]},
    )
    assert launch.status_code == 200
    assert launch.json()["mapped_role"] != "site_admin"
