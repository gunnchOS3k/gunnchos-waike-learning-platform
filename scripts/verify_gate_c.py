#!/usr/bin/env python3
"""Aggregate Gate C interop + Device OS + hardening (honest PASS/BLOCKED).

Fails when owner blockers remain. Does not fabricate certifications.
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

CLAIM_INTEROP = "INTEROPERABILITY_AND_DEVICEOS_DIGITAL_INTEGRATION_COMPLETE"
CLAIM_HARDEN = "PLATFORM_HARDENING_DIGITALLY_COMPLETE"

ACCEPTED_DEVICE_OS_MAIN = "28562a8456207540c205a1c8a6434a491b0a4771"
DEVICE_OS_INTEGRATION_HEAD = "67cf98255e41d953e56eb142af063940e05c8dbb"

OWNER_IDS = [
    "C-OWNER-01",
    "C-OWNER-02",
    "C-OWNER-03",
    "C-OWNER-04",
    "C-OWNER-05",
    "C-OWNER-06",
    "C-OWNER-07",
    "C-OWNER-08",
    "C-OWNER-09",
    "C-OWNER-10",
    "C-OWNER-11",
    "C-OWNER-12",
    "C-OWNER-13",
    "C-OWNER-14",
]


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


def _check_macos_dmg_meta() -> dict[str, object]:
    """When CI_MACOS_DMG_META is present, require real DMG verification JSON ok:true.

    Otherwise require MACOS reports with dmg_sha256 not UNSIGNED_CI_BUILD when artifact
    meta says expected; at minimum record code invariants.
    """
    meta_env = os.environ.get("CI_MACOS_DMG_META", "").strip()
    result: dict[str, object] = {"checked": False, "ok": True, "notes": []}
    ver_json = REPORTS / "MACOS_DMG_VERIFICATION.json"
    sums = REPORTS / "MACOS_SHA256SUMS.txt"
    artifact_meta = REPORTS / "MACOS_ARTIFACT_META.txt"

    if meta_env:
        result["checked"] = True
        path = Path(meta_env)
        if not path.is_file():
            result["ok"] = False
            result["notes"].append(f"CI_MACOS_DMG_META missing file: {meta_env}")
            return result
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            result["ok"] = False
            result["notes"].append(f"invalid DMG meta JSON: {e}")
            return result
        if data.get("ok") is not True:
            result["ok"] = False
            result["notes"].append("CI_MACOS_DMG_META present but ok!=true")
        return result

    if ver_json.is_file():
        result["checked"] = True
        try:
            data = json.loads(ver_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["ok"] = False
            result["notes"].append("MACOS_DMG_VERIFICATION.json unparseable")
            return result
        # Unsigned CI builds are honest — do not claim notarization.
        if data.get("signing_notarization") == "UNSIGNED_CI_BUILD":
            result["notes"].append("UNSIGNED_CI_BUILD recorded (honest; not notarized)")
        if data.get("ok") is True:
            result["notes"].append("DMG verification ok:true")
        # If artifact meta expects a real sha and sums say UNSIGNED, flag as owner gap for C-OWNER-01 (other WS)
        if artifact_meta.is_file() and sums.is_file():
            meta_txt = artifact_meta.read_text(encoding="utf-8")
            sums_txt = sums.read_text(encoding="utf-8")
            if "expected_dmg_sha256" in meta_txt and "UNSIGNED_CI_BUILD" in sums_txt:
                result["ok"] = False
                result["notes"].append("artifact meta expects dmg_sha256 but sums are UNSIGNED_CI_BUILD")
    return result


def _owner_blockers_from_code() -> dict[str, str]:
    """Static/code invariants proving owner workstreams are wired."""
    checks: dict[str, str] = {}
    client = ROOT / "apps/client/src/lib/hub/client.ts"
    admin = ROOT / "apps/client/src/components/admin/AdminHardeningPanel.tsx"
    app = ROOT / "apps/client/src/App.tsx"
    interop = ROOT / "apps/client/src/components/interop/InteropPanels.tsx"
    kb = ROOT / "apps/client/src/test/keyboard.gate-c.test.tsx"
    a11y = ROOT / "apps/client/src/test/a11y.gate-c.test.tsx"
    oneroster = ROOT / "services/hub/app/modules/oneroster.py"
    qti = ROOT / "services/hub/app/modules/qti.py"
    hard = ROOT / "services/hub/app/modules/hardening.py"
    lti = ROOT / "services/hub/app/modules/lti.py"
    backup = ROOT / "services/hub/app/modules/backup_restore.py"
    bridge = ROOT / "services/hub/app/modules/deviceos_bridge.py"
    routes = ROOT / "services/hub/app/api/routes_gate_c.py"
    workflow = ROOT / ".github/workflows/gate-c.yml"
    dmg_script = ROOT / "scripts/verify_macos_dmg.py"
    contract = ROOT / "contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json"
    perf = ROOT / "tests/gate_c/test_performance_concurrency.py"
    backup_test = ROOT / "tests/gate_c/test_backup_restore.py"

    def has(path: Path, *needles: str) -> bool:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        return all(n in text for n in needles)

    checks["C-OWNER-01"] = (
        "PASS"
        if has(workflow, "pnpm exec tauri build", "verify_macos_dmg.py", "bundle/dmg/*.dmg")
        and has(dmg_script, "hdiutil", "dmg_sha256", "NOT_NOTARIZED")
        and has(workflow, "if-no-files-found: error")
        else "FAIL"
    )
    checks["C-OWNER-02"] = (
        "PASS"
        if contract.is_file()
        and has(bridge, "launch_learning_os", "learning_os_launcher", "PermissionsManager")
        and has(contract, "thin_launcher_companion", "waike_learning_os")
        else "FAIL"
    )
    checks["C-OWNER-03"] = (
        "PASS"
        if has(lti, "assert_safe_jwks_url", "default_fetch_jwks", "Never falls back")
        and has(lti, "lti_external_identities", "STATE_TTL_SECONDS")
        else "FAIL"
    )
    checks["C-OWNER-04"] = (
        "PASS"
        if has(backup, "Connection.backup", "_site_filter_connection", "members")
        and has(backup, "hub.sqlite3")
        else "FAIL"
    )
    checks["C-OWNER-05"] = (
        "PASS"
        if has(routes, "/admin/restore", "destructive_restore")
        and has(backup_test, "display_name")
        and not has(backup_test, 'or result["destructive"] is True')
        and not has(backup_test, "or result['destructive'] is True")
        else "FAIL"
    )
    checks["C-OWNER-06"] = (
        "PASS"
        if has(client, "createBackup", "diagnostics", "onerosterMatrix")
        and has(admin, "hub.createBackup", "hub.diagnostics")
        and has(app, "AdminHardeningPanel", "InteropStatusPanel")
        and has(interop, "hub.onerosterMatrix")
        else "FAIL"
    )
    checks["C-OWNER-07"] = (
        "PASS"
        if has(hard, "retry_after", "window_start", "clock")
        and has(hard, "DELETE FROM rate_limit_buckets")
        else "FAIL"
    )
    checks["C-OWNER-08"] = (
        "PASS"
        if has(hard, "parse_semver", "semver_lt", "PACKAGE_TRANSITIONS", "revoked")
        and has(hard, "assert_can_open")
        else "FAIL"
    )
    checks["C-OWNER-09"] = (
        "PASS"
        if has(oneroster, "mapped_section_id", "INACTIVE_STATUSES", "txn.enter", "oneroster_enrollment_inactive")
        else "FAIL"
    )
    checks["C-OWNER-10"] = (
        "PASS"
        if has(qti, "imsqtiasi_v3p0", "external_identifier", "QTI_MALFORMED_NUMERIC", "require_staff_scope")
        else "FAIL"
    )
    checks["C-OWNER-11"] = (
        "PASS"
        if has(hard, "assert_export_allowed", "PRIVACY_EXPORT_BLOCKED", "deactivate_user", "ferpa_claim")
        else "FAIL"
    )
    checks["C-OWNER-12"] = (
        "PASS"
        if has(hard, "subsystems", "db_integrity", "redacted_bundle")
        else "FAIL"
    )
    checks["C-OWNER-13"] = (
        "PASS"
        if has(kb, "App", "AdminHardeningPanel", "keyboard")
        and has(a11y, "App", "AdminHardeningPanel")
        else "FAIL"
    )
    checks["C-OWNER-14"] = (
        "PASS"
        if has(perf, "_build_pilot_fixture", "test_mutation_concurrency", "p95")
        else "FAIL"
    )
    for oid in OWNER_IDS:
        checks.setdefault(oid, "FAIL")
    return checks


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
        "owner_blockers": {},
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
            "device_os": os.environ.get("DEVICE_OS_PIN_REF", DEVICE_OS_INTEGRATION_HEAD),
            "device_os_accepted_main": ACCEPTED_DEVICE_OS_MAIN,
        },
    }
    device_os_pin = str(results["pins"]["device_os"])  # type: ignore[index]
    device_os_pr_required = device_os_pin != ACCEPTED_DEVICE_OS_MAIN
    results["device_os_pr_required"] = device_os_pr_required
    results["tested_against"] = (
        f"device_os_pr_head:{device_os_pin}" if device_os_pr_required else "accepted_device_os_main"
    )

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
    prior_a = run(
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
            "services/hub/tests",
            "--tb=line",
        ],
        env=env,
    )
    env_b = dict(env)
    env_b["PYTHONPATH"] = "tools/course_compiler:services/hub"
    prior_b = run([py, "-m", "pytest", "-q", "tests/gate_b", "--tb=line"], env=env_b)
    prior_counts = _parse_pytest_counts(plain(prior_a))
    prior_b_counts = _parse_pytest_counts(plain(prior_b))
    for k, v in prior_b_counts.items():
        prior_counts[k] = prior_counts.get(k, 0) + v
    prior_rc = 0 if prior_a.returncode == 0 and prior_b.returncode == 0 else 1
    results["test_counts"]["prior_regression"] = prior_counts
    results["exit_codes"] = {"prior_regression": prior_rc, "prior_a": prior_a.returncode, "prior_b": prior_b.returncode}
    results["checks"]["prior_regression"] = prior_rc == 0 and prior_counts["failed"] == 0
    if prior_counts.get("skipped", 0):
        results["GATE_C_REQUIRED_TESTS_SKIPPED"] = prior_counts["skipped"]

    class _Prior:
        returncode = prior_rc

    prior = _Prior()

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

    # Owner blockers (code invariants + targeted suites already in gate_c)
    owner = _owner_blockers_from_code()
    results["owner_blockers"] = owner
    results["checks"]["owner_blockers_all_pass"] = all(v == "PASS" for v in owner.values())

    dmg = _check_macos_dmg_meta()
    results["checks"]["macos_dmg_meta"] = dmg["ok"]
    results["macos_dmg"] = dmg

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
            "device_os_pr_required": device_os_pr_required,
            "tested_against": results["tested_against"],
            "device_os_pin": device_os_pin,
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
    harden_ok = (
        bool(results["checks"].get("gate_c"))
        and bool(results["checks"].get("prior_regression"))
        and bool(results["checks"].get("owner_blockers_all_pass"))
    )
    skipped = int(results["GATE_C_REQUIRED_TESTS_SKIPPED"] or 0)

    # Cross-repo stop: do not earn Gate C claims until Device OS PR is merged to main
    # and Platform is re-pinned. Pipeline may still be green for coordinated review.
    claims: list[str] = []
    blocked: list[str] = []
    digital_ready = (
        interop_ok
        and harden_ok
        and skipped == 0
        and bool(results["checks"].get("owner_blockers_all_pass"))
        and dmg["ok"]
        and prior.returncode == 0
        and gate_c.returncode == 0
    )
    if device_os_pr_required:
        blocked.extend([CLAIM_INTEROP, CLAIM_HARDEN])
        results["owner_action"] = "REVIEW_CROSS_REPO_PR_DEPENDENCY_ORDER"
    else:
        if interop_ok and skipped == 0 and results["checks"].get("owner_blockers_all_pass"):
            claims.append(CLAIM_INTEROP)
        else:
            blocked.append(CLAIM_INTEROP)
        if harden_ok and skipped == 0 and dmg["ok"]:
            claims.append(CLAIM_HARDEN)
        else:
            blocked.append(CLAIM_HARDEN)
        results["owner_action"] = (
            "MERGE_GATE_C_THEN_RERUN_ACCELERATED_MASTER_PROMPT"
            if claims == [CLAIM_INTEROP, CLAIM_HARDEN]
            else "GATE_C_NOT_READY"
        )

    results["claims"] = claims
    results["claims_blocked"] = blocked

    owner_fail = [k for k, v in owner.items() if v != "PASS"]
    if owner_fail:
        results["blocked"].append(f"owner_blockers:{','.join(owner_fail)}")  # type: ignore[union-attr]
    if not dmg["ok"]:
        results["blocked"].append("macos_dmg_meta")  # type: ignore[union-attr]

    if owner_fail or prior.returncode != 0 or gate_c.returncode != 0 or not dmg["ok"]:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        if prior.returncode != 0:
            results["blocked"].append("prior_regression")  # type: ignore[union-attr]
        if gate_c.returncode != 0:
            results["blocked"].append("gate_c")  # type: ignore[union-attr]
        results["owner_action"] = "GATE_C_NOT_READY"
        rc = 1
    elif device_os_pr_required and digital_ready:
        results["status"] = "REVIEW_CROSS_REPO_PR_DEPENDENCY_ORDER"
        rc = 0
    elif claims == [CLAIM_INTEROP, CLAIM_HARDEN]:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        rc = 0
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        results["owner_action"] = "GATE_C_NOT_READY"
        rc = 1

    (REPORTS / "GATE_C_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    claim_lines = [f"- `{c}`" for c in claims] or ["- (none)"]
    blocked_lines = [f"- `{c}`" for c in blocked] or ["- (none)"]
    owner_lines = [f"- `{k}`: **{v}**" for k, v in owner.items()]
    md = [
        "# Gate C Verification",
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
        "## Owner blockers",
        *owner_lines,
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
    print(json.dumps({"status": results["status"], "claims": claims, "owner_blockers": owner, "rc": rc}, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
