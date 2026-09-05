"""LOCAL_SOFTWARE lab runner closure.

The learner supplies data; the server supplies the interpreter, the command, the
working directory and the environment. Evidence hashes are what the server computed,
never what the client claimed.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from helpers import SECTION, auth_header, login

LAB = "lab_dc_local_software"


def _run(client, token: str, mid: str, learner_input: str, **extra):
    body = {"client_mutation_id": mid, "learner_input": learner_input}
    body.update(extra)
    return client.post(
        f"/api/v1/labs/{LAB}/runs", headers=auth_header(token), json=body
    )


def test_server_computes_the_evidence_hash_itself(client):
    learner = login(client, "learner-alpha")
    text = "my lab answer"
    r = _run(client, learner["token"], "mut_lab_compute_001", text)
    assert r.status_code == 200, r.text
    run = r.json()

    assert run["status"] == "completed"
    assert run["evidence_source"] == "server_computed"
    assert run["runner_id"] == "python_hash_fixture_v1"
    assert run["runner_exit_code"] == 0

    computed = run["computed_evidence"]
    assert computed["input_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert computed["stdout_sha256"]
    # The fixture's own output must be reproducible from its declared inputs.
    payload = json.loads(computed["stdout_preview"])
    assert payload["fixture"] == "hash_fixture_v1"
    assert payload["input_sha256"] == computed["input_sha256"]
    assert not computed["timed_out"]


def test_a_fabricated_hash_cannot_replace_the_computed_one(client):
    learner = login(client, "learner-alpha")
    text = "honest work"
    fake = "f" * 64
    r = _run(
        client,
        learner["token"],
        "mut_lab_fakehash_01",
        text,
        artifact_hashes=[fake],
        evidence={"input_sha256": fake, "stdout_sha256": fake, "score": 100},
    )
    assert r.status_code == 200, r.text
    run = r.json()

    real = hashlib.sha256(text.encode()).hexdigest()
    assert run["computed_evidence"]["input_sha256"] == real
    assert fake not in json.dumps(run["computed_evidence"])
    # The claim is retained for review but is clearly labelled as the learner's.
    assert run["claimed"]["claimed_artifact_hashes"] == [fake]
    assert run["evidence_source"] == "server_computed"


def test_authoritative_hashes_come_from_the_runner(client, prod_app):
    learner = login(client, "learner-alpha")
    text = "authoritative"
    r = _run(
        client,
        learner["token"],
        "mut_lab_authoritative1",
        text,
        artifact_hashes=["deadbeef" * 8],
    )
    assert r.status_code == 200, r.text
    row = prod_app.state.db.execute(
        "SELECT artifact_hashes_json FROM lab_runs WHERE client_mutation_id=?",
        ("mut_lab_authoritative1",),
    ).fetchone()
    stored = json.loads(row["artifact_hashes_json"])
    assert hashlib.sha256(text.encode()).hexdigest() in stored
    assert "deadbeef" * 8 not in stored


@pytest.mark.parametrize(
    "hostile",
    [
        {"command": "rm -rf /"},
        {"argv": ["/bin/sh", "-c", "cat /etc/passwd"]},
        {"interpreter": "/bin/bash"},
        {"runner_id": "arbitrary_shell"},
        {"fixture": "../../../../bin/sh"},
    ],
)
def test_the_learner_cannot_choose_what_gets_executed(client, hostile):
    """Extra fields naming a command must be ignored, not honoured."""
    learner = login(client, "learner-alpha")
    mid = f"mut_lab_hostile_{abs(hash(str(hostile))) % 10**6:06d}"
    r = _run(client, learner["token"], mid, "input", **hostile)
    # Either the field is rejected outright or it is ignored; never executed.
    if r.status_code == 200:
        run = r.json()
        assert run["runner_id"] == "python_hash_fixture_v1"
        assert run["evidence_source"] == "server_computed"
        assert "passwd" not in json.dumps(run["computed_evidence"])
    else:
        assert r.status_code in (400, 422), r.text


def test_runner_output_is_capped_and_the_run_stays_bounded(client):
    """A very large input must not blow past the runner's caps or its time limit."""
    learner = login(client, "learner-alpha")
    huge = "A" * (2 * 1024 * 1024)
    r = _run(client, learner["token"], "mut_lab_huge_input01", huge)
    assert r.status_code in (200, 400, 413), r.text
    if r.status_code != 200:
        return
    run = r.json()
    computed = run["computed_evidence"]
    # Previews are bounded regardless of how much the fixture wrote.
    assert len(computed["stdout_preview"]) <= 2048
    assert len(computed["stderr_preview"]) <= 2048
    # The fixture reads at most its declared cap, so it hashes capped bytes.
    assert computed["input_bytes"] <= len(huge)
    assert run["runner_duration_ms"] is not None
    assert not computed["timed_out"]


def test_identical_mutation_id_replays_the_same_run(client):
    learner = login(client, "learner-alpha")
    first = _run(client, learner["token"], "mut_lab_replay_0001", "same input")
    assert first.status_code == 200, first.text
    second = _run(client, learner["token"], "mut_lab_replay_0001", "same input")
    assert second.status_code == 200, second.text
    assert second.json()["run_id"] == first.json()["run_id"]
    assert second.json().get("idempotent_replay") is True


def test_hardware_evidence_can_never_be_fabricated(client):
    learner = login(client, "learner-alpha")
    r = _run(
        client,
        learner["token"],
        "mut_lab_fabricate_01",
        "input",
        fabricate_hardware=True,
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "HARDWARE_EVIDENCE_FABRICATION_FORBIDDEN"

    r2 = _run(
        client,
        learner["token"],
        "mut_lab_fabricate_02",
        "input",
        evidence={"hardware_fabricated": True},
    )
    assert r2.status_code == 400, r2.text


def test_lab_run_is_visible_to_the_learner_and_assigned_staff_only(client):
    learner = login(client, "learner-alpha")
    assert _run(client, learner["token"], "mut_lab_visible_001", "visible").status_code == 200

    mine = client.get(f"/api/v1/labs/{LAB}/runs", headers=auth_header(learner["token"]))
    assert mine.status_code == 200
    assert len(mine.json()) >= 1

    staff = login(client, "instructor-alpha")
    theirs = client.get(f"/api/v1/labs/{LAB}/runs", headers=auth_header(staff["token"]))
    assert theirs.status_code == 200

    outsider = login(client, "learner-gamma", "site-beta")
    denied = client.get(f"/api/v1/labs/{LAB}/runs", headers=auth_header(outsider["token"]))
    assert denied.status_code in (403, 404)


def test_runner_registry_only_lists_trusted_fixtures(client):
    from app.modules.lab_runner import FIXTURE_ROOT, TRUSTED_RUNNERS

    assert TRUSTED_RUNNERS, "there must be an explicit allowlist"
    for runner_id, spec in TRUSTED_RUNNERS.items():
        fixture = (FIXTURE_ROOT / spec.fixture).resolve()
        # Every fixture must be a real file inside the trusted root.
        assert fixture.is_file(), f"{runner_id} points at a missing fixture"
        assert fixture.is_relative_to(FIXTURE_ROOT.resolve())
        assert spec.time_limit_s > 0


def test_an_unknown_runner_id_is_refused(client, prod_app):
    prod_app.state.db.execute(
        "UPDATE lab_definitions SET runner_id=? WHERE lab_id=?", ("totally_untrusted", LAB)
    )
    prod_app.state.db.commit()
    learner = login(client, "learner-alpha")
    r = _run(client, learner["token"], "mut_lab_unknown_run1", "input")
    assert r.status_code == 400, r.text
    assert "RUNNER" in r.json()["detail"]
