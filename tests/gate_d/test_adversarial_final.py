"""Independent falsification pass — static + behavioral semantic soft-pass catches."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from gd_helpers import PINS, ROOT, REPORTS, write_json

GATE_D_TESTS = ROOT / "tests" / "gate_d"
WF = ROOT / ".github" / "workflows" / "gate-d.yml"
VERIFY = ROOT / "scripts" / "verify_gate_d.py"
CLEAN_ROOM = ROOT / "scripts" / "clean_room_reconstruct.py"

SOFT_FAIL_SCAN_ROOTS: tuple[Path, ...] = (
    ROOT / "tests" / "gate_d",
    ROOT / "tests" / "gate_c",
    ROOT / "tests" / "gate_b",
    ROOT / "tests" / "gate_a",
    ROOT / "tests" / "assessment",
    ROOT / "tests" / "pr3",
    ROOT / "tests" / "compatibility",
    ROOT / "tests" / "security",
    ROOT / "tests" / "integration",
    ROOT / "services" / "hub" / "tests",
)

CLAIM_BEARING_PATHS: tuple[Path, ...] = (
    ROOT / "tests" / "gate_d",
    ROOT / "scripts" / "verify_gate_d.py",
    ROOT / "scripts" / "clean_room_reconstruct.py",
    ROOT / ".github" / "workflows" / "gate-d.yml",
)

_OR_TRUE_LINE = re.compile(
    r"(?:assert\b.*\bor\s+[Tt]rue\b)|(?:==\s+.+\s+or\s+[Tt]rue\b)|(?:\bor\s+[Tt]rue\b.*assert)"
)


def _iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _scan_or_true_tautologies() -> list[dict]:
    findings: list[dict] = []
    for root in SOFT_FAIL_SCAN_ROOTS:
        for path in _iter_python_files(root):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if (
                    not stripped
                    or stripped.startswith("#")
                    or stripped.startswith('"""')
                    or stripped.startswith("'''")
                ):
                    continue
                if _OR_TRUE_LINE.search(line):
                    findings.append(
                        {
                            "id": "D-ADV-OR-TRUE",
                            "severity": "Critical",
                            "finding": f"soft-fail tautology in {rel}:{i}: {stripped}",
                        }
                    )
    return findings


def _scan_semantic_soft_passes() -> list[dict]:
    findings: list[dict] = []
    patterns = [
        (r"PASS_OPTIONAL", "PASS_OPTIONAL token"),
        (r'startswith\(\s*["\']PASS["\']\s*\)', 'startswith("PASS") soft-pass'),
        (
            r"status_code\s+in\s*\(\s*200\s*,\s*404\s*\)",
            "status_code in (200, 404) soft path",
        ),
        (
            r"journeys_ok\s*=\s*\(.*\.is_file\(\)",
            "journeys_ok file-existence-only",
        ),
    ]
    for root in CLAIM_BEARING_PATHS:
        paths = [root] if root.is_file() else _iter_python_files(root)
        if root.suffix in {".yml", ".yaml"} and root.is_file():
            paths = [root]
        for path in paths:
            # Sabotage fixtures intentionally embed soft-pass tokens to prove rejection.
            if path.name == "test_adversarial_final.py":
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                stripped = line.strip()
                # Allow reject-list membership of PASS_OPTIONAL (not soft-pass acceptance).
                reject_list_line = (
                    path.name == "verify_gate_d.py"
                    and "PASS_OPTIONAL" in stripped
                    and (
                        stripped.startswith('"PASS_OPTIONAL"')
                        or stripped.startswith("'PASS_OPTIONAL'")
                        or "REJECTED_STEP_STATUSES" in stripped
                    )
                )
                for pat, label in patterns:
                    if reject_list_line and pat == r"PASS_OPTIONAL":
                        continue
                    # Allow reject-detection of startswith PASS* (not soft acceptance).
                    if (
                        path.name == "verify_gate_d.py"
                        and pat == r'startswith\(\s*["\']PASS["\']\s*\)'
                        and "observed != \"PASS\"" in text
                        and "startswith" in stripped
                    ):
                        continue
                    if re.search(pat, line):
                        findings.append(
                            {
                                "id": "D-ADV-SEMANTIC-SOFT",
                                "severity": "Critical",
                                "finding": f"{label} in {rel}:{i}: {stripped}",
                            }
                        )
    # verify must not treat journeys as file-only
    verify_src = VERIFY.read_text(encoding="utf-8")
    if "evaluate_journeys_semantic" not in verify_src and "INSTRUCTOR_REQUIRED_STEPS" not in verify_src:
        findings.append(
            {
                "id": "D-ADV-JOURNEY-SEMANTIC",
                "severity": "Critical",
                "finding": "verify_gate_d.py missing semantic journey evaluation",
            }
        )
    # Soft-pass startswith usage (not reject-detection of startswith PASS*).
    if re.search(r'all\(v\.startswith\(\s*["\']PASS["\']\s*\)', verify_src):
        findings.append(
            {
                "id": "D-ADV-VERIFY-STARTSWITH",
                "severity": "Critical",
                "finding": "verify_gate_d.py still uses startswith(PASS) soft-pass acceptance",
            }
        )
    clean_src = CLEAN_ROOM.read_text(encoding="utf-8")
    if '"uncommitted_deps": False' in clean_src or "'uncommitted_deps': False" in clean_src:
        findings.append(
            {
                "id": "D-ADV-CLEANROOM-HARDCODE",
                "severity": "Critical",
                "finding": "clean_room_reconstruct.py hardcodes uncommitted_deps False",
            }
        )
    if "hidden_fixtures" in clean_src and "fixture_only_production_proof" not in clean_src:
        findings.append(
            {
                "id": "D-ADV-CLEANROOM-HIDDEN",
                "severity": "Critical",
                "finding": "clean_room still uses hidden_fixtures instead of measured fixture_only_production_proof",
            }
        )
    return findings


def _run_behavioral_sabotage() -> tuple[list[dict], list[dict]]:
    """Execute negative semantic cases; return (findings, executed_cases)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_gate_d as vgd  # noqa: WPS433

    findings: list[dict] = []
    executed: list[dict] = []

    # Case: instructor report with PASS_OPTIONAL → verifier fail
    path = REPORTS / "_adv_instructor_pass_optional.json"
    path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "steps": {k: "PASS" for k in vgd.INSTRUCTOR_REQUIRED_STEPS}
                | {"accommodations": "PASS_OPTIONAL"},
            }
        ),
        encoding="utf-8",
    )
    ok, details = vgd.evaluate_journey_report(
        path, scope="instructor_journey", required_steps=vgd.INSTRUCTOR_REQUIRED_STEPS
    )
    executed.append(
        {
            "case": "instructor_pass_optional",
            "ok_expected_false": True,
            "ok": ok,
            "details": details,
        }
    )
    if ok:
        findings.append(
            {
                "id": "D-ADV-BEH-PASS-OPTIONAL",
                "severity": "Critical",
                "finding": "verifier accepted PASS_OPTIONAL accommodations",
            }
        )
    path.unlink(missing_ok=True)

    # Case: missing required step → fail
    path = REPORTS / "_adv_instructor_missing_step.json"
    steps = {k: "PASS" for k in vgd.INSTRUCTOR_REQUIRED_STEPS if k != "mastery_remediation"}
    path.write_text(json.dumps({"status": "PASS", "steps": steps}), encoding="utf-8")
    ok, details = vgd.evaluate_journey_report(
        path, scope="instructor_journey", required_steps=vgd.INSTRUCTOR_REQUIRED_STEPS
    )
    executed.append(
        {"case": "missing_mastery_remediation_step", "ok": ok, "details": details}
    )
    if ok:
        findings.append(
            {
                "id": "D-ADV-BEH-MISSING-STEP",
                "severity": "Critical",
                "finding": "verifier accepted missing mastery_remediation step",
            }
        )
    path.unlink(missing_ok=True)

    # Case: learner top PASS + one step FAIL → fail
    path = REPORTS / "_adv_learner_step_fail.json"
    steps = {k: "PASS" for k in vgd.LEARNER_REQUIRED_STEPS}
    steps["labs"] = "FAIL"
    path.write_text(json.dumps({"status": "PASS", "steps": steps}), encoding="utf-8")
    ok, details = vgd.evaluate_journey_report(
        path, scope="learner_journey", required_steps=vgd.LEARNER_REQUIRED_STEPS
    )
    executed.append({"case": "learner_step_fail", "ok": ok, "details": details})
    if ok:
        findings.append(
            {
                "id": "D-ADV-BEH-LEARNER-FAIL-STEP",
                "severity": "Critical",
                "finding": "verifier accepted learner labs=FAIL under status PASS",
            }
        )
    path.unlink(missing_ok=True)

    # Case: role matrix missing guardian → fail
    path = REPORTS / "_adv_roles_no_guardian.json"
    roles = {
        r: {"least_privilege": "PASS"}
        for r in vgd.ROLE_MATRIX_REQUIRED
        if r != "guardian"
    }
    path.write_text(json.dumps({"roles": roles}), encoding="utf-8")
    ok, details = vgd.evaluate_role_matrix(path)
    executed.append({"case": "role_matrix_missing_guardian", "ok": ok, "details": details})
    if ok:
        findings.append(
            {
                "id": "D-ADV-BEH-NO-GUARDIAN",
                "severity": "Critical",
                "finding": "verifier accepted role matrix without guardian",
            }
        )
    path.unlink(missing_ok=True)

    # Case: mastery absence token → fail (missing key)
    path = REPORTS / "_adv_no_mastery.json"
    steps = {k: "PASS" for k in vgd.INSTRUCTOR_REQUIRED_STEPS}
    del steps["mastery_remediation"]
    path.write_text(json.dumps({"status": "PASS", "steps": steps}), encoding="utf-8")
    ok, details = vgd.evaluate_journey_report(
        path, scope="instructor_journey", required_steps=vgd.INSTRUCTOR_REQUIRED_STEPS
    )
    executed.append({"case": "mastery_absence", "ok": ok, "details": details})
    if ok:
        findings.append(
            {
                "id": "D-ADV-BEH-MASTERY-ABSENCE",
                "severity": "Critical",
                "finding": "verifier accepted mastery absence",
            }
        )
    path.unlink(missing_ok=True)

    return findings, executed


def test_adversarial_final_review(client):
    findings: list[dict] = []
    findings.extend(_scan_or_true_tautologies())
    findings.extend(_scan_semantic_soft_passes())

    wf = WF.read_text(encoding="utf-8")
    body = "\n".join(l for l in wf.splitlines() if not l.lstrip().startswith("#"))
    if "continue-on-error: true" in body:
        findings.append(
            {
                "id": "D-ADV-001",
                "severity": "High",
                "finding": "continue-on-error in Gate D workflow",
            }
        )
    for i, line in enumerate(wf.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if re.search(r"\|\|\s*true", line):
            findings.append(
                {
                    "id": "D-ADV-002",
                    "severity": "High",
                    "finding": f"|| true mask in Gate D workflow:{i}: {line.strip()}",
                }
            )

    for sha in PINS.values():
        assert sha in wf, f"pin {sha} missing from gate-d.yml"

    e2e_upload = re.search(
        r"name:\s*deviceos-real-tauri-e2e-gate-d[\s\S]*?if-no-files-found:\s*(\w+)",
        wf,
    )
    if not e2e_upload or e2e_upload.group(1) != "error":
        findings.append(
            {
                "id": "D-ADV-DEVICEOS-UPLOAD",
                "severity": "Critical",
                "finding": "Device OS E2E artifact upload not if-no-files-found: error",
            }
        )

    verify_src = VERIFY.read_text(encoding="utf-8")
    if "RECOVERED_EXACT_PR1_ARTIFACT" not in verify_src:
        findings.append(
            {
                "id": "D-ADV-STALE-DMG",
                "severity": "Critical",
                "finding": "verify_gate_d must reject RECOVERED_EXACT_PR1_ARTIFACT",
            }
        )

    all18 = (GATE_D_TESTS / "test_all_18_tracks.py").read_text(encoding="utf-8")
    if "matrix_final_status" not in all18:
        findings.append(
            {
                "id": "D-ADV-ALL18-AUTO",
                "severity": "Critical",
                "finding": "test_all_18_tracks must consume matrix_final_status",
            }
        )

    # Behavioral: accommodations wrong-role + wrong-section denial (live).
    from gd_helpers import SECTION, auth_header, login, user_id

    learner = login(client, "learner-alpha")
    lid = user_id(learner)
    lh = auth_header(learner["token"])
    deny_learner = client.post(
        "/api/v1/accommodations",
        headers=lh,
        json={"learner_id": lid, "section_id": SECTION, "attempt_override": 9},
    )
    executed_live = [
        {
            "case": "accommodations_wrong_role_learner",
            "status_code": deny_learner.status_code,
        }
    ]
    if deny_learner.status_code != 403:
        findings.append(
            {
                "id": "D-ADV-BEH-ACC-ROLE",
                "severity": "Critical",
                "finding": f"learner accommodation upsert not denied ({deny_learner.status_code})",
            }
        )

    inst = login(client, "instructor-alpha")
    deny_section = client.post(
        "/api/v1/accommodations",
        headers=auth_header(inst["token"]),
        json={
            "learner_id": lid,
            "section_id": "sec_beta_dc_w01",
            "attempt_override": 9,
        },
    )
    executed_live.append(
        {
            "case": "accommodations_wrong_section",
            "status_code": deny_section.status_code,
        }
    )
    if deny_section.status_code not in (403, 404):
        findings.append(
            {
                "id": "D-ADV-BEH-ACC-SECTION",
                "severity": "Critical",
                "finding": f"wrong-section accommodation not denied ({deny_section.status_code})",
            }
        )

    beh_findings, beh_cases = _run_behavioral_sabotage()
    findings.extend(beh_findings)

    md_lines = [
        "# Gate D Adversarial Final Review",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Hunt checklist",
        "- soft-fail assert tautologies across Gate D + prior-regression suites",
        "- PASS_OPTIONAL / startswith(PASS) / 200|404 required-scope soft paths",
        "- journeys_ok file-existence-only / hardcoded clean-room false",
        "- behavioral sabotage: accommodations denials, mastery absence, PASS_OPTIONAL verifier fail",
        "",
        "## Behavioral cases executed",
        *[f"- `{c.get('case')}` → `{c}`" for c in executed_live + beh_cases],
        "",
        f"## Findings: {len(findings)}",
    ]
    for f in findings:
        md_lines.append(f"- `{f['id']}` {f['severity']}: {f['finding']}")
    if not findings:
        md_lines.append("- none — digital falsification pass clean")
    (ROOT / "reports" / "GATE_D_ADVERSARIAL_REVIEW.md").write_text("\n".join(md_lines) + "\n")
    write_json(
        "GATE_D_ADVERSARIAL_REVIEW.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "findings": findings,
            "behavioral_cases_executed": executed_live + beh_cases,
            "soft_fail_scan_roots": [p.relative_to(ROOT).as_posix() for p in SOFT_FAIL_SCAN_ROOTS],
            "status": "PASS" if not findings else "FAIL",
        },
    )
    assert not findings, findings
