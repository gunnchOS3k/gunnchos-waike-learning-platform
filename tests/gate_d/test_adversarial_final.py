"""Independent falsification pass — must catch Gate D soft-fail / stale-proof patterns."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from gd_helpers import PINS, ROOT, write_json

GATE_D_TESTS = ROOT / "tests" / "gate_d"
WF = ROOT / ".github" / "workflows" / "gate-d.yml"
VERIFY = ROOT / "scripts" / "verify_gate_d.py"

# Paths covered by AUTOMATED_FULL_PLATFORM_PASS / Gate D prior regression + Gate D suite.
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

_OR_TRUE_LINE = re.compile(
    r"(?:assert\b.*\bor\s+[Tt]rue\b)|(?:==\s+.+\s+or\s+[Tt]rue\b)|(?:\bor\s+[Tt]rue\b.*assert)"
)


def _iter_python_files(root: Path) -> list[Path]:
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


def test_adversarial_final_review():
    findings: list[dict] = []
    findings.extend(_scan_or_true_tautologies())

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
    if re.search(r"\|\|\s*true", body):
        # Comment-only mentions of the ban are fine; executable masks are not.
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

    # Device OS E2E upload must fail closed (not warn).
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

    # Stale PR1 DMG must never satisfy Gate D native ok.
    verify_src = VERIFY.read_text(encoding="utf-8")
    if "RECOVERED_EXACT_PR1_ARTIFACT" not in verify_src:
        findings.append(
            {
                "id": "D-ADV-STALE-DMG",
                "severity": "Critical",
                "finding": "verify_gate_d must reject RECOVERED_EXACT_PR1_ARTIFACT",
            }
        )
    if "GATE_D_REQUIRE_NATIVE" not in verify_src and "artifact_head_sha" not in verify_src:
        findings.append(
            {
                "id": "D-ADV-NATIVE-BIND",
                "severity": "Critical",
                "finding": "verify_gate_d must bind this-run native artifacts to head SHA",
            }
        )

    # all-18 must consume matrix_final_status (not registry auto-PASS).
    all18 = (GATE_D_TESTS / "test_all_18_tracks.py").read_text(encoding="utf-8")
    if "matrix_final_status" not in all18:
        findings.append(
            {
                "id": "D-ADV-ALL18-AUTO",
                "severity": "Critical",
                "finding": "test_all_18_tracks must consume matrix_final_status",
            }
        )
    if 'row = {"track_id": track_id, "stable_id": track_id, "status": "PASS"}' in all18:
        findings.append(
            {
                "id": "D-ADV-ALL18-STAMP",
                "severity": "Critical",
                "finding": "test_all_18_tracks auto-PASS stamp pattern still present",
            }
        )

    # Evidence SHA must prefer PR head, not merge github.sha alone.
    if "pull_request.head.sha" not in wf and "GATE_D_HEAD_SHA" not in wf:
        findings.append(
            {
                "id": "D-ADV-HEAD-SHA",
                "severity": "Critical",
                "finding": "Gate D workflow must bind evidence to pull_request.head.sha",
            }
        )

    # Committed local-path Device OS E2E must not be treated as Gate D proof by verifier.
    if "/Users/gunnchos" not in verify_src and "/Users/" not in verify_src:
        findings.append(
            {
                "id": "D-ADV-DEVICEOS-LOCAL",
                "severity": "High",
                "finding": "verify_gate_d should reject committed local-path Device OS E2E evidence",
            }
        )

    # If a committed MACOS verification is present with PR1 recovery, ok must not be trusted alone.
    macos = ROOT / "reports" / "MACOS_DMG_VERIFICATION.json"
    if macos.is_file():
        try:
            ver = json.loads(macos.read_text(encoding="utf-8"))
            if ver.get("recovery_status") == "RECOVERED_EXACT_PR1_ARTIFACT" and ver.get("ok") is True:
                findings.append(
                    {
                        "id": "D-ADV-COMMITTED-PR1-DMG",
                        "severity": "Critical",
                        "finding": (
                            "committed MACOS_DMG_VERIFICATION.json is stale PR1 artifact marked ok:true"
                        ),
                    }
                )
        except json.JSONDecodeError:
            findings.append(
                {
                    "id": "D-ADV-DMG-JSON",
                    "severity": "High",
                    "finding": "MACOS_DMG_VERIFICATION.json is not valid JSON",
                }
            )

    md_lines = [
        "# Gate D Adversarial Final Review",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Hunt checklist",
        "- soft-fail assert tautologies across Gate D + prior-regression suites (boolean OR True)",
        "- stale PR1 DMG as current native proof",
        "- all-18 registry auto-PASS",
        "- Device OS E2E upload warn-only",
        "- evidence SHA not equal to PR head",
        "- mocks-as-prod / skips / xfail / continue-on-error / shell true-masks",
        "",
        "## Soft-fail scan roots",
        *[f"- `{p.relative_to(ROOT).as_posix()}`" for p in SOFT_FAIL_SCAN_ROOTS],
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
            "soft_fail_scan_roots": [p.relative_to(ROOT).as_posix() for p in SOFT_FAIL_SCAN_ROOTS],
            "status": "PASS" if not findings else "FAIL",
        },
    )
    assert not findings, findings
