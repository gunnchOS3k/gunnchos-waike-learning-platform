#!/usr/bin/env python3
"""Aggregate PR1 acceptance checks from process exit codes (not optimistic report text)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SOURCE_DATE_EPOCH = os.environ.get("SOURCE_DATE_EPOCH", "1700000000")


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or ROOT, env=e, text=True, capture_output=True)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    results: dict[str, object] = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "AUTOMATED_PIPELINE_BLOCKED_BY_CODE",
        "checks": {},
        "test_counts": {},
        "package_hash": None,
        "blocked": [],
        "exit_codes": {},
    }
    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text())
    results["declared_pinned_commit"] = pin.get("pinned_commit")
    results["taxonomy_pr"] = pin.get("taxonomy_pr")

    # Observed WAIKE HEAD
    waike = Path(pin.get("absolute_path_hint") or (ROOT.parent / "waike-research-ops"))
    obs = run(["git", "-C", str(waike), "rev-parse", "HEAD"])
    results["exit_codes"]["waike_rev_parse"] = obs.returncode
    observed = (obs.stdout or "").strip() if obs.returncode == 0 else ""
    results["observed_source_commit"] = observed
    results["checks"]["provenance_match"] = bool(observed) and observed == pin.get("pinned_commit")
    if not results["checks"]["provenance_match"]:
        results["blocked"].append(
            f"PROVENANCE_MISMATCH declared={pin.get('pinned_commit')} observed={observed}"
        )

    export = json.loads((ROOT / "curriculum/registry/CANONICAL_TRACK_REGISTRY.export.json").read_text())
    track_count = len(export.get("tracks") or [])
    results["checks"]["registry_18"] = track_count == 18
    if track_count != 18:
        results["blocked"].append(f"registry track_count={track_count}")

    py = ROOT / ".venv/bin/python"
    env = {"PYTHONPATH": str(ROOT / "tools/course_compiler"), "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}

    # Deterministic learner pair
    compile_script = (
        "from pathlib import Path; from course_compiler.compiler import compile_module; "
        "import json; "
        "r1=compile_module('DIGITAL_CONFIDENCE', out_dir=Path('pack_out/a')); "
        "r2=compile_module('DIGITAL_CONFIDENCE', out_dir=Path('pack_out/b')); "
        "print(json.dumps({"
        "'learner_a': r1['learner_zip_sha256'], 'learner_b': r2['learner_zip_sha256'], "
        "'plain_a': r1['instructor_plaintext_sha256'], 'plain_b': r2['instructor_plaintext_sha256'], "
        "'ct_a': r1['instructor_blob_sha256'], 'ct_b': r2['instructor_blob_sha256'], "
        "'declared': r1['declared_pinned_commit'], 'observed': r1['observed_source_commit']}))"
    )
    cp = run([str(py), "-c", compile_script], env=env)
    results["exit_codes"]["compile_pair"] = cp.returncode
    results["checks"]["compile"] = cp.returncode == 0
    if cp.returncode == 0:
        pair = json.loads(cp.stdout.strip().splitlines()[-1])
        results["package_hash"] = pair["learner_a"]
        results["learner_hash_pair"] = [pair["learner_a"], pair["learner_b"]]
        results["instructor_plaintext_hash_pair"] = [pair["plain_a"], pair["plain_b"]]
        results["instructor_ciphertext_pair"] = [pair["ct_a"], pair["ct_b"]]
        results["checks"]["learner_deterministic"] = pair["learner_a"] == pair["learner_b"]
        results["checks"]["instructor_plaintext_deterministic"] = pair["plain_a"] == pair["plain_b"]
        results["checks"]["instructor_ciphertext_unique"] = pair["ct_a"] != pair["ct_b"]
        results["checks"]["report_provenance"] = pair["declared"] == pair["observed"]
        for name in (
            "learner_deterministic",
            "instructor_plaintext_deterministic",
            "instructor_ciphertext_unique",
            "report_provenance",
        ):
            if not results["checks"][name]:
                results["blocked"].append(f"{name} failed")
    else:
        results["blocked"].append("compile failed: " + (cp.stderr or cp.stdout)[-800:])

    pytest = ROOT / ".venv/bin/pytest"
    pt = run([str(pytest), "-q", str(ROOT / "tests"), str(ROOT / "services/hub/tests")], env=env)
    results["exit_codes"]["python_tests"] = pt.returncode
    results["checks"]["python_tests"] = pt.returncode == 0
    out = (pt.stdout or "") + (pt.stderr or "")
    results["test_counts"]["python"] = out.strip().splitlines()[-1] if out.strip() else "unknown"
    if pt.returncode != 0:
        results["blocked"].append("python tests failed")

    cargo_env = {
        **env,
        "WAIKE_DEV_DB_KEY": os.environ.get(
            "WAIKE_DEV_DB_KEY",
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ),
    }
    rt = run(
        ["bash", "-lc", 'source "$HOME/.cargo/env" && cargo test'],
        cwd=ROOT / "apps/client/src-tauri",
        env=cargo_env,
    )
    results["exit_codes"]["rust_tests"] = rt.returncode
    results["checks"]["rust_tests"] = rt.returncode == 0
    results["test_counts"]["rust"] = "see cargo output / exit_codes"
    if rt.returncode != 0:
        results["blocked"].append("rust tests failed: " + (rt.stderr or rt.stdout)[-800:])

    ft = run(["bash", "-lc", "pnpm test || npm test"], cwd=ROOT / "apps/client")
    results["exit_codes"]["frontend_tests"] = ft.returncode
    results["checks"]["frontend_tests"] = ft.returncode == 0
    if ft.returncode != 0:
        results["blocked"].append("frontend tests failed")

    required_docs = [
        "docs/architecture/SYSTEM_CONTEXT.md",
        "docs/architecture/REPOSITORY_OWNERSHIP.md",
        "docs/architecture/COMPATIBILITY_CONTRACT.md",
        "docs/adr/ADR-0001-modular-monolith.md",
        "docs/adr/ADR-0002-course-package-supply-chain.md",
        "docs/adr/ADR-0003-encrypted-local-storage.md",
        "docs/security/THREAT_MODEL.md",
        "docs/security/DATA_CLASSIFICATION.md",
        "docs/security/KEY_MANAGEMENT_DEVELOPMENT.md",
        "docs/security/INSTRUCTOR_PACKAGE_CRYPTO.md",
        "docs/product/CLAIM_BOUNDARY.md",
        "docs/product/PR1_ACCEPTANCE_MATRIX.md",
        "docs/product/SEED_BROWSER_BOUNDARY.md",
        "DEVELOPMENT.md",
    ]
    missing = [d for d in required_docs if not (ROOT / d).is_file()]
    results["checks"]["docs"] = not missing
    if missing:
        results["blocked"].append("missing docs: " + ", ".join(missing))

    ok = all(bool(v) for v in results["checks"].values()) and not results["blocked"]
    # Fail closed on any non-zero subordinate exit we recorded as required
    for key, code in results["exit_codes"].items():
        if key in ("waike_rev_parse", "compile_pair", "python_tests", "rust_tests", "frontend_tests") and code != 0:
            ok = False
    results["status"] = "AUTOMATED_PIPELINE_PASS" if ok else "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
    results["claim"] = (
        "DIGITALLY_IMPLEMENTED_AND_AUTOMATICALLY_TESTED_FOR_PR1_SCOPE" if ok else "NOT_EARNED"
    )

    (REPORTS / "pr1_verification.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# PR1 Verification",
        "",
        f"- Status: `{results['status']}`",
        f"- Claim: `{results['claim']}`",
        f"- declared_pinned_commit: `{results.get('declared_pinned_commit')}`",
        f"- observed_source_commit: `{results.get('observed_source_commit')}`",
        f"- Taxonomy PR: {results.get('taxonomy_pr')}",
        f"- Package hash: `{results.get('package_hash')}`",
        f"- Python: {results['test_counts'].get('python')}",
        "",
        "## Checks",
        "",
    ]
    for k, v in results["checks"].items():
        md.append(f"- {'PASS' if v else 'FAIL'} `{k}`")
    md.append("")
    md.append("## Exit codes")
    md.append("")
    for k, v in results["exit_codes"].items():
        md.append(f"- `{k}`: `{v}`")
    if results["blocked"]:
        md.extend(["", "## Blocked", ""])
        for b in results["blocked"]:
            md.append(f"- {b}")
    md.append("")
    (REPORTS / "PR1_VERIFICATION.md").write_text("\n".join(md))
    print(json.dumps({"status": results["status"], "package_hash": results["package_hash"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
