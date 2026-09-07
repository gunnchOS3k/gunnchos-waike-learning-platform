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

LEARNER_REQUIRED_STEPS = (
    "auth",
    "enroll_nav",
    "lessons_nav",
    "assignments",
    "quizzes",
    "discussions",
    "groups",
    "labs",
    "save_resume_offline_sync",
    "mastery_portfolio",
    "projects_capstones",
)

INSTRUCTOR_REQUIRED_STEPS = (
    "auth_roles",
    "sections_activity",
    "assessment_queue",
    "grading_rubrics_feedback",
    "gradebook",
    "mastery_remediation",
    "discussion_group",
    "accommodations",
    "admin_operator",
)

ROLE_MATRIX_REQUIRED = (
    "learner",
    "instructor",
    "grader",
    "guardian",
    "site_admin",
)

REJECTED_STEP_STATUSES = {
    "PASS_OPTIONAL",
    "PENDING",
    "SKIPPED",
    "NOT_APPLICABLE",
    "UNKNOWN",
    "FAIL",
    "BLOCKED",
}


def _semantic_fail(scope: str, field: str, observed, required) -> dict:
    return {"scope": scope, "field": field, "observed": observed, "required": required}


def evaluate_journey_report(
    path: Path,
    *,
    scope: str,
    required_steps: tuple[str, ...],
) -> tuple[bool, list[dict]]:
    """Require top-level status PASS and every required step exactly 'PASS'."""
    details: list[dict] = []
    if not path.is_file():
        details.append(_semantic_fail(scope, "report_file", None, str(path.name)))
        return False, details
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        details.append(_semantic_fail(scope, "report_json", "invalid", "valid_json"))
        return False, details
    status = data.get("status")
    if status != "PASS":
        details.append(_semantic_fail(scope, "status", status, "PASS"))
    steps = data.get("steps")
    if not isinstance(steps, dict):
        details.append(_semantic_fail(scope, "steps", type(steps).__name__, "dict"))
        return False, details
    for key in required_steps:
        observed = steps.get(key, None)
        if observed != "PASS":
            details.append(_semantic_fail(scope, f"steps.{key}", observed, "PASS"))
        if isinstance(observed, str) and observed in REJECTED_STEP_STATUSES:
            details.append(
                _semantic_fail(scope, f"steps.{key}_rejected_token", observed, "PASS")
            )
        if isinstance(observed, str) and observed.startswith("PASS") and observed != "PASS":
            details.append(
                _semantic_fail(scope, f"steps.{key}_startswith_pass", observed, "PASS")
            )
    return len(details) == 0, details


def evaluate_role_matrix(path: Path) -> tuple[bool, list[dict]]:
    details: list[dict] = []
    if not path.is_file():
        details.append(_semantic_fail("role_matrix", "report_file", None, path.name))
        return False, details
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        details.append(_semantic_fail("role_matrix", "report_json", "invalid", "valid_json"))
        return False, details
    roles = data.get("roles")
    if not isinstance(roles, dict):
        details.append(_semantic_fail("role_matrix", "roles", type(roles).__name__, "dict"))
        return False, details
    for role in ROLE_MATRIX_REQUIRED:
        row = roles.get(role)
        if not isinstance(row, dict):
            details.append(_semantic_fail("role_matrix", f"roles.{role}", row, "dict"))
            continue
        lp = row.get("least_privilege")
        if lp != "PASS":
            details.append(
                _semantic_fail("role_matrix", f"roles.{role}.least_privilege", lp, "PASS")
            )
    return len(details) == 0, details


def evaluate_journeys_semantic() -> tuple[bool, list[dict], dict]:
    details: list[dict] = []
    learner_ok, learner_d = evaluate_journey_report(
        REPORTS / "GATE_D_LEARNER_JOURNEY.json",
        scope="learner_journey",
        required_steps=LEARNER_REQUIRED_STEPS,
    )
    instructor_ok, instructor_d = evaluate_journey_report(
        REPORTS / "GATE_D_INSTRUCTOR_JOURNEY.json",
        scope="instructor_journey",
        required_steps=INSTRUCTOR_REQUIRED_STEPS,
    )
    roles_ok, roles_d = evaluate_role_matrix(REPORTS / "GATE_D_ROLE_JOURNEY_MATRIX.json")
    details.extend(learner_d)
    details.extend(instructor_d)
    details.extend(roles_d)
    summary = {
        "learner_ok": learner_ok,
        "instructor_ok": instructor_ok,
        "role_matrix_ok": roles_ok,
        "detail_count": len(details),
    }
    return learner_ok and instructor_ok and roles_ok, details, summary



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

    # Prior regression PR1–Gate C (isolate helpers module namespaces)
    prior_a = run(
        [
            py, "-m", "pytest", "-q",
            "tests/compatibility", "tests/security", "tests/integration",
            "tests/assessment", "tests/pr3", "tests/gate_a", "services/hub/tests",
            "--tb=line",
        ],
        env=env,
    )
    env_c = dict(env)
    prior_c = run([py, "-m", "pytest", "-q", "tests/gate_c", "--tb=line"], env=env_c)
    env_b = dict(env)
    env_b["PYTHONPATH"] = "tools/course_compiler:services/hub"
    prior_b = run([py, "-m", "pytest", "-q", "tests/gate_b", "--tb=line"], env=env_b)
    prior_counts = _parse_pytest_counts(plain(prior_a))
    for part in (prior_c, prior_b):
        for k, v in _parse_pytest_counts(plain(part)).items():
            prior_counts[k] = prior_counts.get(k, 0) + v
    prior_rc = 0 if prior_a.returncode == 0 and prior_b.returncode == 0 and prior_c.returncode == 0 else 1

    class _Prior:
        returncode = prior_rc

    prior = _Prior()
    results["test_counts"]["prior_regression"] = prior_counts
    results["exit_codes"]["prior_regression"] = prior_rc  # type: ignore[index]
    results["checks"]["prior_regression"] = prior_rc == 0 and prior_counts["failed"] == 0
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
    # Prefer PR head SHA over ephemeral merge ref so evidence matches branch tip.
    platform_sha = (
        os.environ.get("GATE_D_HEAD_SHA")
        or os.environ.get("GITHUB_EVENT_PULL_REQUEST_HEAD_SHA")
        or ""
    ).strip()
    if not platform_sha:
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

    # Native + Device OS evidence must be this-run CI artifacts bound to PR head SHA.
    require_native = os.environ.get("GATE_D_REQUIRE_NATIVE", "").strip() in ("1", "true", "TRUE")
    require_deviceos = os.environ.get("GATE_D_REQUIRE_DEVICEOS_E2E", "").strip() in (
        "1",
        "true",
        "TRUE",
    )
    # In GitHub Actions, always require this-run native + Device OS E2E binding.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        require_native = True
        require_deviceos = True

    def _parse_meta(path: Path) -> dict[str, str]:
        meta: dict[str, str] = {}
        if not path.is_file():
            return meta
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                meta[k.strip()] = v.strip()
        return meta

    native_notes: list[str] = []
    linux_meta = _parse_meta(REPORTS / "LINUX_ARTIFACT_META.txt")
    macos_meta = _parse_meta(REPORTS / "MACOS_ARTIFACT_META.txt")
    linux_sums_ok = (REPORTS / "LINUX_SHA256SUMS.txt").is_file()
    macos_sums_ok = (REPORTS / "MACOS_SHA256SUMS.txt").is_file()
    linux_head = linux_meta.get("artifact_head_sha", "")
    macos_head = macos_meta.get("artifact_head_sha", "")
    linux_format = linux_meta.get("format", "")
    macos_format = macos_meta.get("format", "")

    linux_ok = bool(
        linux_meta
        and linux_sums_ok
        and linux_head
        and linux_head == platform_sha
        and linux_format == "ELF_binary_not_zip"
    )
    if not linux_ok:
        native_notes.append(
            "linux this-run meta/sums/head/format binding failed "
            f"(head={linux_head!r} expected={platform_sha!r} format={linux_format!r})"
        )

    macos_ver_path = REPORTS / "MACOS_DMG_VERIFICATION.json"
    macos_ver: dict = {}
    macos_ok = False
    if macos_ver_path.is_file():
        try:
            macos_ver = json.loads(macos_ver_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            native_notes.append("MACOS_DMG_VERIFICATION.json invalid JSON")
            macos_ver = {}
    recovery = str(macos_ver.get("recovery_status") or "")
    if recovery == "RECOVERED_EXACT_PR1_ARTIFACT":
        native_notes.append("rejected stale PR1 RECOVERED_EXACT_PR1_ARTIFACT as Gate D native proof")
    elif not macos_ver_path.is_file():
        native_notes.append("missing MACOS_DMG_VERIFICATION.json")
    elif macos_ver.get("ok") is not True:
        native_notes.append("MACOS_DMG_VERIFICATION ok!=true")
    elif not macos_meta:
        native_notes.append("missing MACOS_ARTIFACT_META.txt")
    elif not macos_sums_ok:
        native_notes.append("missing MACOS_SHA256SUMS.txt")
    else:
        ver_head = str(
            macos_ver.get("artifact_head_sha")
            or macos_ver.get("source_commit")
            or macos_head
            or ""
        )
        dmg_path = str(macos_ver.get("dmg_path") or macos_ver.get("preserved_dmg_path") or "")
        zip_confused = dmg_path.lower().endswith(".zip") or macos_format != "DMG_not_zip"
        if zip_confused:
            native_notes.append("ZIP-as-DMG confusion or format!=DMG_not_zip")
        elif ver_head != platform_sha or macos_head != platform_sha:
            native_notes.append(
                f"macos artifact_head_sha mismatch ver={ver_head!r} meta={macos_head!r} "
                f"expected={platform_sha!r}"
            )
        elif recovery != "THIS_RUN_NATIVE_BUILD":
            native_notes.append(f"macos recovery_status not this-run: {recovery!r}")
        else:
            macos_ok = True

    native = {
        "generated_utc": now,
        "platform_sha": platform_sha,
        "this_run_only": True,
        "linux": {
            "meta": bool(linux_meta),
            "sums": linux_sums_ok,
            "artifact_head_sha": linux_head,
            "format": linux_format,
            "ok": linux_ok,
        },
        "macos": {
            "meta": bool(macos_meta),
            "sums": macos_sums_ok,
            "verification": macos_ver_path.is_file(),
            "artifact_head_sha": macos_head,
            "format": macos_format,
            "recovery_status": recovery,
            "ok": macos_ok,
        },
        "zip_is_not_dmg": macos_format == "DMG_not_zip"
        and not str(macos_ver.get("dmg_path") or "").lower().endswith(".zip"),
        "signing_notarization": "EXTERNAL_UNSIGNED_CI_BUILD",
        "notarization_claimed": False,
        "notes": native_notes,
        "require_native": require_native,
    }
    native_pass = bool(linux_ok and macos_ok and native["zip_is_not_dmg"])
    native["ok"] = native_pass
    _write_json("GATE_D_NATIVE_ARTIFACT_MANIFEST.json", native)
    results["checks"]["native_artifacts"] = native_pass if require_native else True
    if require_native and not native_pass:
        results["blocked"].append("native_artifacts_this_run")  # type: ignore[union-attr]

    # Device OS real Tauri E2E — CI-produced only; reject committed local-path evidence.
    deviceos_path = REPORTS / "DEVICEOS_REAL_TAURI_E2E.json"
    deviceos_notes: list[str] = []
    deviceos_ok = False
    if deviceos_path.is_file():
        try:
            de = json.loads(deviceos_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            de = {}
            deviceos_notes.append("DEVICEOS_REAL_TAURI_E2E.json invalid JSON")
        blob = json.dumps(de)
        if "/Users/gunnchos" in blob or "/Users/" in blob:
            deviceos_notes.append("rejected local absolute path Device OS E2E evidence")
        prov = de.get("provenance") or {}
        e2e_sha = str(prov.get("platform_source_sha") or de.get("platform_sha_at_local_run") or "")
        if e2e_sha != platform_sha:
            deviceos_notes.append(
                f"Device OS E2E platform_source_sha {e2e_sha!r} != head {platform_sha!r}"
            )
        launched = bool(de.get("launched") or de.get("acknowledged"))
        if de.get("mock") is True:
            deviceos_notes.append("Device OS E2E marked mock=true")
        if not deviceos_notes and launched and e2e_sha == platform_sha:
            deviceos_ok = True
    else:
        deviceos_notes.append("missing DEVICEOS_REAL_TAURI_E2E.json")
    deviceos_report = {
        "generated_utc": now,
        "platform_sha": platform_sha,
        "ok": deviceos_ok,
        "notes": deviceos_notes,
        "require_deviceos": require_deviceos,
    }
    _write_json("GATE_D_DEVICEOS_E2E_BINDING.json", deviceos_report)
    results["checks"]["deviceos_e2e_binding"] = deviceos_ok if require_deviceos else True
    if require_deviceos and not deviceos_ok:
        results["blocked"].append("deviceos_e2e_binding")  # type: ignore[union-attr]

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

    journeys_ok, journey_details, journey_summary = evaluate_journeys_semantic()
    results["checks"]["journeys"] = journeys_ok
    results["journey_semantic"] = journey_summary
    if journey_details:
        results["journey_semantic_failures"] = journey_details
        results["blocked"].append("journey_semantic")  # type: ignore[union-attr]

    # Clean-room semantic: require measured ok:true (not file presence alone).
    clean_room_report = REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.json"
    clean_room_semantic = False
    if clean_room_report.is_file():
        try:
            cr_data = json.loads(clean_room_report.read_text(encoding="utf-8"))
            clean_room_semantic = cr_data.get("ok") is True
            if not clean_room_semantic:
                results["blocked"].append("clean_room_ok_false")  # type: ignore[union-attr]
        except json.JSONDecodeError:
            results["blocked"].append("clean_room_json_invalid")  # type: ignore[union-attr]
    results["checks"]["clean_room_semantic"] = clean_room_semantic
    # Prefer measured clean-room ok over mere script exit when report present.
    if clean_room_report.is_file():
        results["checks"]["clean_room"] = bool(
            results["checks"].get("clean_room")
        ) and clean_room_semantic

    adv = REPORTS / "GATE_D_ADVERSARIAL_REVIEW.json"
    adv_ok = False
    if adv.is_file():
        adv_ok = json.loads(adv.read_text()).get("status") == "PASS"
    results["checks"]["adversarial"] = adv_ok

    skipped = int(results["GATE_D_REQUIRED_TESTS_SKIPPED"] or 0)
    native_check = bool(results["checks"].get("native_artifacts"))
    deviceos_check = bool(results["checks"].get("deviceos_e2e_binding"))
    digital_ready = (
        bool(results["checks"].get("clean_room"))
        and bool(results["checks"].get("prior_regression"))
        and bool(results["checks"].get("gate_d"))
        and bool(results["checks"].get("required_artifacts"))
        and tracks_ok
        and journeys_ok
        and adv_ok
        and native_check
        and deviceos_check
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
        if not native_check:
            results["blocked"].append("native_artifacts")  # type: ignore[union-attr]
        if not deviceos_check:
            results["blocked"].append("deviceos_e2e")  # type: ignore[union-attr]
        rc = 1

    results["claims"] = claims
    results["claims_blocked"] = blocked

    _write_json("GATE_D_VERIFICATION.json", results)
    claim_lines = [f"- `{c}`" for c in claims] or ["- (none)"]
    blocked_lines = [f"- `{c}`" for c in blocked] or ["- (none)"]
    md = [
        "# Gate D Verification",
        "",
        f"Generated: {now}",
        f"Status: **{results['status']}**",
        "",
        "## Claims earned",
        *claim_lines,
        "",
        "## Claims blocked",
        *blocked_lines,
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
    if journey_details:
        md.extend(["", "## Journey semantic failures"])
        for d in journey_details[:40]:
            md.append(
                f"- `{d['scope']}` / `{d['field']}`: observed=`{d['observed']}` required=`{d['required']}`"
            )
    (REPORTS / "GATE_D_VERIFICATION.md").write_text("\n".join(md) + "\n")

    # This-run FULL_COMPLETION_STATE for CI artifact only (committed baseline stays PENDING).
    state = {
        "schema": "waike.learning_os.full_completion_state.v1",
        "platform_repo": "gunnchOS3k/gunnchos-waike-learning-platform",
        "platform_branch": "cursor/waike-learning-gate-d-full-acceptance",
        "accepted_platform_main": "58daf1a0cc22b60c4246eb4195b74bcb0a714a38",
        "gate_c_merge_commit": "58daf1a0cc22b60c4246eb4195b74bcb0a714a38",
        "current_wave": "GATE_D_FULL_ACCEPTANCE",
        "status": results["status"],
        "source": "verify_gate_d_this_run",
        "waves": {
            "PR1_FOUNDATION": "MERGED",
            "PR2_ASSESSMENT_LIFECYCLE": "MERGED",
            "PR3_IDENTITY_INSTRUCTOR": "MERGED",
            "GATE_A_OFFLINE_ACTIVITIES": "MERGED",
            "GATE_B_AI_18_TRACKS": "MERGED",
            "GATE_C_INTEROP_DEVICE_HARDENING": "MERGED",
            "GATE_D_FULL_ACCEPTANCE": "CLAIMS_EARNED_PENDING_OWNER_MERGE"
            if digital_ready
            else "GATE_D_NOT_READY",
        },
        "claims_earned": claims,
        "claims_pending": blocked,
        "claims_withdrawn_until_reproof": []
        if digital_ready
        else [CLAIM_AUTO, CLAIM_18, CLAIM_JOURNEYS, CLAIM_ALPHA],
        "device_os_accepted_main": PINS["device_os"],
        "waike_pin": PINS["waike"],
        "gunnchai_pin": PINS["gunnchai"],
        "owner_action": results.get("owner_action"),
        "last_verified_utc": now,
        "platform_sha": platform_sha,
        "honesty": (
            "This-run CI artifact: digital Gate D claims earned only when clean-room + prior "
            "regression + Gate D suites pass with zero skips, semantic journey/role PASS fields, "
            "this-run native Linux/macOS artifacts bound to PR head SHA, and CI Device OS E2E "
            "evidence bound to the same head. Committed FULL_COMPLETION_STATE.json baseline remains "
            "PENDING_FINAL_EXACT_HEAD_CI until owner merges. External gates remain OPEN."
            if digital_ready
            else (
                "Gate D not ready — see GATE_D_VERIFICATION.json blocked list / "
                "journey_semantic_failures. Owner action: GATE_D_NOT_READY."
            )
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
