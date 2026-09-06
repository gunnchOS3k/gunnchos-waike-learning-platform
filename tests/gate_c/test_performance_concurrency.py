"""Pilot-shaped performance + concurrency smoke."""

from __future__ import annotations

import concurrent.futures

from helpers import auth_header, login


def test_pilot_matrix_endpoints_fast(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    for path in (
        "/api/v1/interop/oneroster/matrix",
        "/api/v1/interop/qti/matrix",
        "/api/v1/interop/lti/matrix",
        "/api/v1/deviceos/profiles",
        "/api/v1/privacy/matrix",
        "/version",
    ):
        r = client.get(path, headers=h if path.startswith("/api") else None)
        assert r.status_code == 200


def test_concurrent_reads(client):
    h = auth_header(login(client, "learner-alpha")["token"])

    def hit():
        return client.get("/api/v1/deviceos/manifest", headers=h).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(lambda _: hit(), range(16)))
    assert all(c == 200 for c in codes)
