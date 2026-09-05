"""Lab engine — no fabricated hardware evidence."""

from helpers import auth_header, login


def test_local_software_lab_and_hardware_guard(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    lab = client.get("/api/v1/labs/lab_dc_local_software", headers=h)
    assert lab.status_code == 200
    assert lab.json()["mode"] == "LOCAL_SOFTWARE"
    assert lab.json()["spec"]["environment"]["sandbox"] is True

    ok = client.post(
        "/api/v1/labs/lab_dc_local_software/runs",
        headers=h,
        json={
            "evidence": {"stdout_hash": "abc123"},
            "artifact_hashes": ["deadbeef"],
            "client_mutation_id": "mut_lab_ok_0001",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["hardware_evidence_fabricated"] is False

    bad = client.post(
        "/api/v1/labs/lab_dc_local_software/runs",
        headers=h,
        json={
            "evidence": {"hardware_fabricated": True},
            "artifact_hashes": [],
            "client_mutation_id": "mut_lab_fab_0001",
            "fabricate_hardware": True,
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "HARDWARE_EVIDENCE_FABRICATION_FORBIDDEN"
