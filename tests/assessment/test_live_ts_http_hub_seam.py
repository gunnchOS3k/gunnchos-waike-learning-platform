"""Live HTTP seam: TypeScript createHttpHubClient against a real local hub process.

Runs from assessment CI after hub deps are installed. Spawns uvicorn, then Node fetch
using the same paths/headers as apps/client/src/lib/hub/client.ts.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENT_ID = "digital_confidence_w01"


def _waike() -> Path:
    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    raise FileNotFoundError("waike-research-ops missing")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_health(base: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception as e:  # noqa: BLE001 — retry until ready
            last = e
            time.sleep(0.2)
    raise RuntimeError(f"hub did not become healthy: {last}")


@pytest.fixture()
def live_hub(tmp_path):
    port = _free_port()
    db = tmp_path / "live_hub.sqlite3"
    waike = _waike()
    env = os.environ.copy()
    env["WAIKE_ROOT"] = str(waike)
    env["WAIKE_HUB_DB"] = str(db)
    env["WAIKE_FIXTURE_AUTH"] = "1"
    env["WAIKE_SEED_TEST_FIXTURES"] = "true"
    env["WAIKE_ENV"] = "development"
    env["PYTHONPATH"] = str(ROOT / "services" / "hub") + os.pathsep + env.get("PYTHONPATH", "")
    # uvicorn loads app.main:app (seed=False); WAIKE_SEED_TEST_FIXTURES opts into fixtures.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT / "services" / "hub"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(base)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_typescript_http_client_against_live_hub(live_hub, tmp_path):
    """Node fetch client mirrors createHttpHubClient against real HTTP hub."""
    script = tmp_path / "http_hub_client_seam.mjs"
    script.write_text(
        f"""
const base = {json.dumps(live_hub)};
const ASSIGNMENT_ID = {json.dumps(ASSIGNMENT_ID)};

function headers(actorId, role) {{
  return {{
    "Content-Type": "application/json",
    "X-Waike-Actor-Id": actorId,
    "X-Waike-Actor-Role": role,
  }};
}}

async function req(path, actorId, role, init = {{}}) {{
  const res = await fetch(`${{base}}${{path}}`, {{
    ...init,
    headers: {{ ...headers(actorId, role), ...(init.headers || {{}}) }},
  }});
  if (!res.ok) {{
    const body = await res.text();
    throw new Error(`${{res.status}}:${{body}}`);
  }}
  return res.json();
}}

const learner = {{
  listAssignments: () => req("/api/v1/assignments", "learner-a", "learner"),
  getAssignment: (id) => req(`/api/v1/assignments/${{id}}`, "learner-a", "learner"),
  saveDraft: (id, text) =>
    req(`/api/v1/assignments/${{id}}/draft`, "learner-a", "learner", {{
      method: "PUT",
      body: JSON.stringify({{ text_response: text, artifact_name: null, artifact_base64: null }}),
    }}),
  submit: (id, key, text) =>
    req(`/api/v1/assignments/${{id}}/submit`, "learner-a", "learner", {{
      method: "POST",
      body: JSON.stringify({{ idempotency_key: key, text_response: text }}),
    }}),
  getSubmission: (id) => req(`/api/v1/submissions/${{id}}`, "learner-a", "learner"),
}};

const instructor = {{
  queue: (id) => req(`/api/v1/instructor/assignments/${{id}}/queue`, "instructor-1", "instructor"),
  grade: (submissionId, body) =>
    req(`/api/v1/instructor/submissions/${{submissionId}}/grade`, "instructor-1", "instructor", {{
      method: "POST",
      body: JSON.stringify({{ ...body, return_to_learner: true }}),
    }}),
}};

const listed = await learner.listAssignments();
if (!listed.some((a) => a.assignment_id === ASSIGNMENT_ID)) throw new Error("assignment missing");
const detail = await learner.getAssignment(ASSIGNMENT_ID);
if (!detail.source_path.endsWith("week_01.yaml")) throw new Error("not real WAIKE assignment");
await learner.saveDraft(ASSIGNMENT_ID, "Live TS HTTP seam draft");
const sub = await learner.submit(ASSIGNMENT_ID, "idem-live-ts-seam", "Live TS HTTP seam submit");
const queue = await instructor.queue(ASSIGNMENT_ID);
if (!queue.some((q) => q.submission_id === sub.submission_id)) throw new Error("not in queue");
const scores = detail.rubric.criteria.map((c) => {{
  const level = c.levels.find((l) => Number(l.score) === 4);
  return {{ criterion_id: c.criterion_id, points: 4, level_id: level.level_id, comment: "live" }};
}});
const graded = await instructor.grade(sub.submission_id, {{
  criterion_scores: scores,
  feedback_body: "Live TS HTTP seam feedback",
}});
if (graded.mastery.mastered !== 1) throw new Error("expected mastery from score");
const view = await learner.getSubmission(sub.submission_id);
if (!view.grade || !view.feedback.some((f) => f.body.includes("Live TS HTTP seam feedback"))) {{
  throw new Error("learner did not receive grade/feedback");
}}
if (JSON.stringify(graded).includes("force_mastery_gap")) throw new Error("force_mastery_gap leaked");
console.log(JSON.stringify({{ ok: true, submission_id: sub.submission_id, mastered: graded.mastery.mastered }}));
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node seam failed\\nstdout={proc.stdout}\\nstderr={proc.stderr}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["mastered"] == 1
