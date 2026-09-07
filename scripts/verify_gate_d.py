#!/usr/bin/env python3
"""Aggregate Gate D clean-room full-system acceptance (honest PASS/BLOCKED).

Earns claims only when suites + artifacts prove digital release-candidate readiness.
Does not fabricate external/physical/certification evidence.
"""

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

PINS = {
    "device_os": "4f02a48780d300a5d3a7758937b20e3bf9364d0d",
    "waike": "fbf7685bc5686201ccaa0128ee83346d59b3d584",
    "gunnchai": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
}

CLAIM_AUTO = "AUTOMATED_FULL_PLATFORM_PASS"
CLAIM_18 = "ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE"
CLAIM_JOURNEYS = "LEARNER_AND_INSTRUCTOR_WORKFLOWS_DIGITALLY_COMPLETE"
CLAIM_ALPHA = "READY_FOR_STAFF_ALPHA_AND_HUMAN_VALIDATION"

REQUIRED_ARTIFACTS = [
    "GATE_D_CLEAN_ROOM_RECONSTRUCTION.json",
    "GATE_D_ALL_18_TRACK_ACCEPTANCE.json",
    "GATE_D_ROLE_JOURNEY_MATRIX.json",
    "GATE_D_SECURITY_ADVERSARIAL_MATRIX.json",
    "GATE_D_ADVERSARIAL_REVIEW.md",
    "GATE_D_EVIDENCE_MANIFEST.json",
    "GATE_D_DEPENDENCY_PROVENANCE.json",
    "EXTERNAL_HUMAN_PHYSICAL_GATES.md",
]


def plain(proc: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))


def run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=e, text=True, capture_output=True)


def _parse_pytest_counts(out: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "error": 0}
    for key in counts:
        m = re.search(rf"(\d+)\s+{key}", out)
        if m:
            counts[key] = int(m.group(1))
    return counts


def _write_json(name: str, data: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
        "pins": dict(PINS),
        "GATE_D_REQUIRED_TESTS_SKIPPED": 0,
        "claim_boundary": {
            "does_not_claim": [
                "physical Device Quartet",
                "production signing/notarization",
                "WCAG certification",
                "FERPA certification",
                "OneRoster/QTI/LTI certification",
                "field pilot / manufacturing",
            ]
        },
    }

    py = str(ROOT / ".venv" / "bin" / "python3")
    if not Path(py).exists():
        py = sys.executable

    env = {
        "PYTHONPATH": "tools/course_compiler:services/hub",
        "WAIKE_ROOT": os.environ.get("WAIKE_ROOT", str(ROOT.parent / "waike-research-ops")),
        "DEVICE_OS_ROOT": os.environ.get(
            "DEVICE_OS_ROOT", str(ROOT.parent / "gunnchos-device-os")
        ),
        "GUNNCHAI_ROOT": os.environ.get("GUNNCHAI_ROOT", str(ROOT.parent / "gunnchAI3k")),
        "WAIKE_ALLOW_FAKE_AI": "1",
    }

    # Clean-room report
    cr = run([py, "scripts/clean_room_reconstruct.py"], env=env)
    results["exit_codes"] = {"clean_room": cr.returncode}
    results["checks"]["clean_room"] = cr.returncode == 0

    # Prior regression PR1–Gate C
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
            "tests/gate_c",
            "services/hub/tests",
            "--tb=line",
        ],
        env=env,
    )
    prior_counts = _parse_pytest_counts(plain(prior))
    results["test_counts"]["prior_regression"] = prior_counts
    results["exit_codes"]["prior_regression"] = prior.returncode  # type: ignore[index]
    results["checks"]["prior_regression"] = prior.returncode == 0 and prior_counts["failed"] == 0
    if prior_counts.get("skipped"):
        results["GATE_D_REQUIRED_TESTS_SKIPPED"] = prior_counts["skipped"]

    # Gate D suite
    gate_d = run([py, "-m", "pytest", "-q", "tests/gate_d", "--tb=line"], env=env)
    gate_out = plain(gate_d)
    gate_counts = _parse_pytest_counts(gate_out)
    results["test_counts"]["gate_d"] = gate_counts
    results["exit_codes"]["gate_d"] = gate_d.returncode  # type: ignore[index]
    results["checks"]["gate_d"] = gate_d.returncode == 0 and gate_counts["failed"] == 0
    if gate_counts.get("skipped"):
        results["GATE_D_REQUIRED_TESTS_SKIPPED"] = int(  # type: ignore[operator]
            results["GATE_D_REQUIRED_TESTS_SKIPPED"] or 0
        ) + gate_counts["skipped"]

    # Dependency provenance
    platform_sha = (
        run(["git", "rev-parse", "HEAD"]).stdout or ""
    ).strip() or os.environ.get("GITHUB_SHA", "")
    provenance = {
        "generated_utc": now,
        "platform_sha": platform_sha,
        "accepted_platform_main_merge_gate_c": "58daf1a0cc22b60c4246eb4195b74bcb0a714a38",
        "pins": PINS,
        "sources": {
            "waike": "https://github.com/gunnchOS3k/waike-research-ops",
            "device_os": "https://github.com/gunnchOS3k/gunnchos-device-os",
            "gunnchai": "https://github.com/gunnchOS3k/gunnchAI3k",
            "platform": "https://github.com/gunnchOS3k/gunnchos-waike-learning-platform",
        },
    }
    _write_json("GATE_D_DEPENDENCY_PROVENANCE.json", provenance)

    # Native artifact manifest (honest about CI artifacts when present)
    native = {
        "generated_utc": now,
        "linux": {
            "meta": (REPORTS / "LINUX_ARTIFACT_META.txt").is_file(),
            "sums": (REPORTS / "LINUX_SHA256SUMS.txt").is_file(),
        },
        "macos": {
            "meta": (REPORTS / "MACOS_ARTIFACT_META.txt").is_file(),
            "sums": (REPORTS / "MACOS_SHA256SUMS.txt").is_file(),
            "verification": (REPORTS / "MACOS_DMG_VERIFICATION.json").is_file(),
        },
        "zip_is_not_dmg": True,
        "signing_notarization": "EXTERNAL_UNSIGNED_CI_BUILD",
        "notarization_claimed": False,
    }
    if native["macos"]["verification"]:
        try:
            ver = json.loads((REPORTS / "MACOS_DMG_VERIFICATION.json").read_text())
            native["macos"]["ok"] = ver.get("ok") is True
        except json.JSONDecodeError:
            native["macos"]["ok"] = False
    _write_json("GATE_D_NATIVE_ARTIFACT_MANIFEST.json", native)

    # External ledger refresh (honest OPEN)
    external_md = f"""# External / Human / Physical Gates

Generated: {now}

Gate D digital completion does **not** clear these:

1. OneRoster / QTI / LTI **external certification** or LMS vendor interoperability field proof
2. Physical **Device Quartet** hardware validation (Student 14.5 / Handheld Hybrid / DS-XL Coder / Edge IO Wearables)
3. Production **signing / notarization** of native artifacts
4. FERPA / institutional privacy certification
5. Independent security or accessibility (WCAG) certification
6. Human pedagogical / staff alpha / field pilot acceptance

Status: **OPEN / EXTERNAL** — recorded honestly; not fabricated.
"""
    (REPORTS / "EXTERNAL_HUMAN_PHYSICAL_GATES.md").write_text(external_md)

    # Evidence manifest
    evidence_files = sorted(p.name for p in REPORTS.glob("GATE_D_*"))
    evidence = {
        "generated_utc": now,
        "platform_sha": platform_sha,
        "files": evidence_files,
        "pins": PINS,
    }
    _write_json("GATE_D_EVIDENCE_MANIFEST.json", evidence)

    missing = [f for f in REQUIRED_ARTIFACTS if not (REPORTS / f).is_file()]
    results["checks"]["required_artifacts"] = len(missing) == 0
    if missing:
        results["blocked"].append(f"missing_artifacts:{missing}")  # type: ignore[union-attr]

    # Track acceptance
    track = REPORTS / "GATE_D_ALL_18_TRACK_ACCEPTANCE.json"
    tracks_ok = False
    if track.is_file():
        tdata = json.loads(track.read_text())
        tracks_ok = bool(tdata.get("all_pass")) and int(tdata.get("track_count") or 0) == 18
    results["checks"]["all_18_tracks"] = tracks_ok

    journeys_ok = (REPORTS / "GATE_D_LEARNER_JOURNEY.json").is_file() and (
        REPORTS / "GATE_D_INSTRUCTOR_JOURNEY.json"
    ).is_file() and (REPORTS / "GATE_D_ROLE_JOURNEY_MATRIX.json").is_file()
    results["checks"]["journeys"] = journeys_ok

    adv = REPORTS / "GATE_D_ADVERSARIAL_REVIEW.json"
    adv_ok = False
    if adv.is_file():
        adv_ok = json.loads(adv.read_text()).get("status") == "PASS"
    results["checks"]["adversarial"] = adv_ok

    skipped = int(results["GATE_D_REQUIRED_TESTS_SKIPPED"] or 0)
    digital_ready = (
        bool(results["checks"].get("clean_room"))
        and bool(results["checks"].get("prior_regression"))
        and bool(results["checks"].get("gate_d"))
        and bool(results["checks"].get("required_artifacts"))
        and tracks_ok
        and journeys_ok
        and adv_ok
        and skipped == 0
        and prior.returncode == 0
        and gate_d.returncode == 0
    )

    claims: list[str] = []
    blocked: list[str] = []
    if digital_ready:
        claims.extend([CLAIM_AUTO, CLAIM_18, CLAIM_JOURNEYS, CLAIM_ALPHA])
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        results["owner_action"] = "MERGE_GATE_D_FINAL_ACCEPTANCE"
        rc = 0
    else:
        for c in (CLAIM_AUTO, CLAIM_18, CLAIM_JOURNEYS, CLAIM_ALPHA):
            blocked.append(c)
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        results["owner_action"] = "GATE_D_NOT_READY"
        if prior.returncode != 0:
            results["blocked"].append("prior_regression")  # type: ignore[union-attr]
        if gate_d.returncode != 0:
            results["blocked"].append("gate_d")  # type: ignore[union-attr]
        if not tracks_ok:
            results["blocked"].append("all_18_tracks")  # type: ignore[union-attr]
        if not journeys_ok:
            results["blocked"].append("journeys")  # type: ignore[union-attr]
        if not adv_ok:
            results["blocked"].append("adversarial")  # type: ignore[union-attr]
        rc = 1

    results["claims"] = claims
    results["claims_blocked"] = blocked

    _write_json("GATE_D_VERIFICATION.json", results)
    md = [
        "# Gate D Verification",
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
        f"- gate_d: `{gate_counts}`",
        f"- GATE_D_REQUIRED_TESTS_SKIPPED: `{skipped}`",
        "",
        f"Owner action: `{results.get('owner_action')}`",
        "",
        "## Claim boundary",
        "- Does not claim physical Device Quartet, notarization, WCAG/FERPA/standards certification, or field pilot.",
    ]
    (REPORTS / "GATE_D_VERIFICATION.md").write_text("\n".join(md) + "\n")

    # Update FULL_COMPLETION_STATE.json
    state = {
        "schema": "waike.learning_os.full_completion_state.v1",
        "platform_repo": "gunnchOS3k/gunnchos-waike-learning-platform",
        "platform_branch": "cursor/waike-learning-gate-d-full-acceptance",
        "accepted_platform_main": "58daf1a0cc22b60c4246eb4195b74bcb0a714a38",
        "gate_c_merge_commit": "58daf1a0cc22b60c4246eb4195b74bcb0a714a38",
        "current_wave": "GATE_D_FULL_ACCEPTANCE",
        "status": results["status"],
        "waves": {
            "PR1_FOUNDATION": "MERGED",
            "PR2_ASSESSMENT_LIFECYCLE": "MERGED",
            "PR3_IDENTITY_INSTRUCTOR": "MERGED",
            "GATE_A_OFFLINE_ACTIVITIES": "MERGED",
            "GATE_B_AI_18_TRACKS": "MERGED",
            "GATE_C_INTEROP_DEVICE_HARDENING": "MERGED",
            "GATE_D_FULL_ACCEPTANCE": "CLAIMS_EARNED_PENDING_OWNER_MERGE"
            if digital_ready
            else "IN_PROGRESS_OR_BLOCKED",
        },
        "claims_earned": claims,
        "claims_pending": blocked,
        "device_os_accepted_main": PINS["device_os"],
        "waike_pin": PINS["waike"],
        "gunnchai_pin": PINS["gunnchai"],
        "owner_action": results.get("owner_action"),
        "last_verified_utc": now,
        "platform_sha": platform_sha,
        "honesty": (
            "Digital Gate D claims earned only when clean-room + prior regression + Gate D suites "
            "pass with zero skips and required evidence artifacts. External/physical/certification "
            "gates remain OPEN."
            if digital_ready
            else "Gate D not ready — see GATE_D_VERIFICATION.json blocked list."
        ),
    }
    _write_json("FULL_COMPLETION_STATE.json", state)

    print(
        json.dumps(
            {
                "status": results["status"],
                "claims": claims,
                "owner_action": results.get("owner_action"),
                "rc": rc,
            },
            indent=2,
        )
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
