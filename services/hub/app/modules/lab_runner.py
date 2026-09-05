"""Constrained LOCAL_SOFTWARE lab runner.

Trust boundary (documented, not overstated):

* The executed program is always a repo-controlled fixture selected by ``runner_id`` from
  the lab definition. A learner supplies *data* only; they can never supply a command, an
  interpreter, an argument, or a path.
* Each run gets a fresh temp workdir, a scrubbed environment, ``shell=False``, a wall-clock
  timeout, and a hard cap on captured output.
* Evidence hashes are computed here from the bytes the runner actually produced. A hash
  claimed by the client is recorded as a *claim* and never substituted for the computed value.
* This is process-level confinement, not an OS sandbox. There is no seccomp/namespace/
  cgroup isolation, so an untrusted fixture could still reach the filesystem or network.
  Only fixtures in ``TRUSTED_RUNNERS`` — which are reviewed repo code — may execute.
* Hardware labs stay external: nothing in this module attests to physical devices.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "lab_fixtures"

# Only these interpreters may ever be spawned.
ALLOWED_RUNTIMES = {"python"}

MAX_OUTPUT_BYTES = 64 * 1024
MAX_INPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class RunnerSpec:
    runner_id: str
    runtime: str
    fixture: str
    time_limit_s: float
    max_output_bytes: int = MAX_OUTPUT_BYTES
    input_filename: str = "input.txt"


TRUSTED_RUNNERS: dict[str, RunnerSpec] = {
    "python_hash_fixture_v1": RunnerSpec(
        runner_id="python_hash_fixture_v1",
        runtime="python",
        fixture="hash_fixture.py",
        time_limit_s=15.0,
    ),
}


class LabRunnerError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _interpreter(runtime: str) -> str:
    if runtime not in ALLOWED_RUNTIMES:
        raise LabRunnerError("RUNTIME_NOT_ALLOWED")
    if runtime == "python":
        return sys.executable
    raise LabRunnerError("RUNTIME_NOT_ALLOWED")


def _scrubbed_env(workdir: Path) -> dict[str, str]:
    """Minimal deterministic environment: no inherited secrets, proxies, or PYTHON* vars."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(workdir),
        "TMPDIR": str(workdir),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "SOURCE_DATE_EPOCH": "1700000000",
    }


def resolve_runner(runner_id: str | None) -> RunnerSpec:
    if not runner_id:
        raise LabRunnerError("RUNNER_NOT_DECLARED")
    spec = TRUSTED_RUNNERS.get(runner_id)
    if spec is None:
        raise LabRunnerError("RUNNER_NOT_TRUSTED")
    return spec


def run_local_software(spec: RunnerSpec, learner_input: str) -> dict[str, Any]:
    """Execute the trusted fixture and return server-computed evidence."""
    fixture_path = (FIXTURE_ROOT / spec.fixture).resolve()
    try:
        fixture_path.relative_to(FIXTURE_ROOT.resolve())
    except ValueError as e:
        raise LabRunnerError("RUNNER_NOT_TRUSTED") from e
    if not fixture_path.is_file():
        raise LabRunnerError("RUNNER_FIXTURE_MISSING")

    payload = (learner_input or "").encode("utf-8")[:MAX_INPUT_BYTES]
    workdir = Path(tempfile.mkdtemp(prefix="waike-lab-"))
    started = time.monotonic()
    try:
        (workdir / spec.input_filename).write_bytes(payload)
        argv = [_interpreter(spec.runtime), str(fixture_path)]
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, shell=False, trusted fixture
                argv,
                cwd=str(workdir),
                env=_scrubbed_env(workdir),
                capture_output=True,
                timeout=spec.time_limit_s,
                shell=False,
                check=False,
            )
            timed_out = False
            stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            exit_code = None
        duration_ms = int((time.monotonic() - started) * 1000)

        truncated = len(stdout) > spec.max_output_bytes or len(stderr) > spec.max_output_bytes
        stdout = stdout[: spec.max_output_bytes]
        stderr = stderr[: spec.max_output_bytes]

        return {
            "runner_id": spec.runner_id,
            "runtime": spec.runtime,
            "fixture": spec.fixture,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "truncated": truncated,
            "duration_ms": duration_ms,
            "input_bytes": len(payload),
            # Computed from the bytes the runner produced — the sole authoritative hashes.
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "input_sha256": hashlib.sha256(payload).hexdigest(),
            "stdout_preview": stdout.decode("utf-8", errors="replace")[:2048],
            "stderr_preview": stderr.decode("utf-8", errors="replace")[:2048],
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
