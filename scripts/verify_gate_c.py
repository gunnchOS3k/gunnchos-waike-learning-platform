#!/usr/bin/env python3
"""Aggregate Gate C interop + Device OS + hardening (honest PASS/BLOCKED)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SOURCE_DATE_EPOCH = os.environ.get("SOURCE_DATE_EPOCH", "1700000000")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

CLAIM_INTEROP = "INTEROPERABILITY_AND_DEVICEOS_DIGITAL_INTEGRATION_COMPLETE"
CLAIM_HARDEN = "PLATFORM_HARDENING_DIGITALLY_COMPLETE"


def plain(proc: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or ROOT, env=e, text=True, capture_output=True)


def _parse_pytest_counts(out: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "error": 0}
    for key in counts:
        m = re.search(rf"(\d+)\s+{key}", out)
        if m:
            counts[key] = int(m.group(1))
    return counts


def _write_matrix(name: str, data: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    lines = [f"# {name}", "", f"Generated: {data.get('generated_utc')}", ""]
    for k, v in data.items():
        if k == "generated_utc":
            continue
        lines.append(f"- **{k}**: `{v}`")
    (REPORTS / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: dict[str, object] = {
        "generated_utc": now,
        "status": "AUTOMATED_PIPELINE_BLOCKED_BY_CODE",
        "claims": [],
        "claims_blocked": [],
        "checks": {},
        "test_counts": {},
        "blocked": [],
        "GATE_C_REQUIRED_TESTS_SKIPPED": 0,
        "claim_boundary": {
            "does_not_claim": [
                "OneRoster/QTI/LTI certification",
                "physical Device Quartet",
                "FERPA certification",
                "security/accessibility certification",
                "production signing/notarization",
                "Gate D full-system acceptance",
            ]
        },
        "pins": {
            "waike": os.environ.get("WAIKE_PIN_REF", "fbf7685bc5686201ccaa0128ee83346d59b3d584"),
            "gunnchai": os.environ.get("GUNNCHAI_PIN_REF", "4b4f411710e8cdb8102a7e11502f8497f68156b1"),
            "device_os": os.environ.get("DEVICE_OS_PIN_REF", "28562a8456207540c205a1c8a6434a491b0a4771"),
        },
    }

    py = str(ROOT / ".venv" / "bin" / "python3")
    if not Path(py).exists():
        py = sys.executable

    env = {
        "PYTHONPATH": "services/hub",
        "WAIKE_ROOT": os.environ.get("WAIKE_ROOT", str(ROOT.parent / "waike-research-ops")),
        "DEVICE_OS_ROOT": os.environ.get(
            "DEVICE_OS_ROOT", str(ROOT.parent / "gunnchos-device-os")
        ),
        "GUNNCHAI_ROOT": os.environ.get("GUNNCHAI_ROOT", str(ROOT.parent / "gunnchAI3k")),
        "WAIKE_ALLOW_FAKE_AI": "1",
    }

    # Prior regression (PR1–Gate B)
    prior = run(
        [
            py,
            "-m",
            "pytest",
            "-q",
            "tests/compatibility",
            "tests/security",
            "tests/integration",
            "tests/assessment",
            "tests/pr3",
            "tests/gate_a",
            "tests/gate_b",
            "services/hub/tests",
            "--tb=line",
        ],
        env=env,
    )
    prior_out = plain(prior)
    prior_counts = _parse_pytest_counts(prior_out)
    results["test_counts"]["prior_regression"] = prior_counts
    results["exit_codes"] = {"prior_regression": prior.returncode}
    results["checks"]["prior_regression"] = prior.returncode == 0 and prior_counts["failed"] == 0
    if prior_counts.get("skipped", 0):
        results["GATE_C_REQUIRED_TESTS_SKIPPED"] = prior_counts["skipped"]

    # Gate C suite
    gate_c = run([py, "-m", "pytest", "-q", "tests/gate_c", "--tb=line"], env=env)
    gate_out = plain(gate_c)
    gate_counts = _parse_pytest_counts(gate_out)
    results["test_counts"]["gate_c"] = gate_counts
    results["exit_codes"]["gate_c"] = gate_c.returncode  # type: ignore[index]
    results["checks"]["gate_c"] = gate_c.returncode == 0 and gate_counts["failed"] == 0
    if gate_counts.get("skipped", 0):
        results["GATE_C_REQUIRED_TESTS_SKIPPED"] = (  # type: ignore[operator]
            int(results["GATE_C_REQUIRED_TESTS_SKIPPED"] or 0) + gate_counts["skipped"]
        )

    # Discovery presence
    for req in (
        "GATE_C_DISCOVERY.json",
        "GATE_C_DEVICEOS_CONTRACT_DISCOVERY.json",
    ):
        results["checks"][req] = (REPORTS / req).is_file()

    # Emit support matrices from live services via quick import
    sys.path.insert(0, str(ROOT / "services" / "hub"))
    from app.modules.oneroster import OneRosterService  # noqa: E402
    from app.modules.qti import QtiService  # noqa: E402
    from app.modules.lti import LtiService  # noqa: E402
    from app.modules.device_profiles import matrix as dq_matrix  # noqa: E402
    from app.modules.deviceos_bridge import DeviceOsBridge  # noqa: E402
    import sqlite3

    conn = sqlite3.connect(":memory:")
    or_m = OneRosterService(conn).support_matrix()
    qti_m = QtiService(conn).support_matrix()
    lti_m = LtiService(conn).support_matrix()
    _write_matrix(
        "GATE_C_ONEROSTER_MATRIX",
        {"generated_utc": now, **or_m},
    )
    _write_matrix("GATE_C_QTI_MATRIX", {"generated_utc": now, **qti_m})
    _write_matrix("GATE_C_LTI_MATRIX", {"generated_utc": now, **lti_m})
    _write_matrix(
        "GATE_C_DEVICE_QUARTET_DIGITAL_PROFILE",
        {"generated_utc": now, **dq_matrix()},
    )
    bridge = DeviceOsBridge(conn)
    _write_matrix(
        "GATE_C_DEVICEOS_MATRIX",
        {
            "generated_utc": now,
            "manifest": bridge.manifest(),
            "contracts": bridge.discover_contracts(),
            "device_os_pr_required": False,
            "tested_against": "accepted_device_os_main",
        },
    )

    interop_ok = bool(results["checks"].get("gate_c")) and all(
        (REPORTS / f).is_file()
        for f in (
            "GATE_C_ONEROSTER_MATRIX.json",
            "GATE_C_QTI_MATRIX.json",
            "GATE_C_LTI_MATRIX.json",
            "GATE_C_DEVICEOS_MATRIX.json",
            "GATE_C_DEVICE_QUARTET_DIGITAL_PROFILE.json",
        )
    )
    harden_ok = bool(results["checks"].get("gate_c")) and bool(results["checks"].get("prior_regression"))
    skipped = int(results["GATE_C_REQUIRED_TESTS_SKIPPED"] or 0)

    claims: list[str] = []
    blocked: list[str] = []
    if interop_ok and skipped == 0:
        claims.append(CLAIM_INTEROP)
    else:
        blocked.append(CLAIM_INTEROP)
    if harden_ok and skipped == 0:
        claims.append(CLAIM_HARDEN)
    else:
        blocked.append(CLAIM_HARDEN)

    results["claims"] = claims
    results["claims_blocked"] = blocked
    if claims == [CLAIM_INTEROP, CLAIM_HARDEN] and prior.returncode == 0 and gate_c.returncode == 0:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        rc = 0
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        if prior.returncode != 0:
            results["blocked"].append("prior_regression")  # type: ignore[union-attr]
        if gate_c.returncode != 0:
            results["blocked"].append("gate_c")  # type: ignore[union-attr]
        rc = 1

    (REPORTS / "GATE_C_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# Gate C Verification",
        "",
        f"Generated: {now}",
        f"Status: **{results['status']}**",
        "",
        "## Claims earned",
        *[f"- `{c}`" for c in claims] or ["- (none)"],
        "",
        "## Claims blocked",
        *[f"- `{c}`" for c in blocked] or ["- (none)"],
        "",
        "## Test counts",
        f"- prior_regression: `{prior_counts}`",
        f"- gate_c: `{gate_counts}`",
        f"- GATE_C_REQUIRED_TESTS_SKIPPED: `{skipped}`",
        "",
        "## Claim boundary",
        "- Does not claim certifications, physical Device Quartet, FERPA, or Gate D.",
    ]
    (REPORTS / "GATE_C_VERIFICATION.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"status": results["status"], "claims": claims, "rc": rc}, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
