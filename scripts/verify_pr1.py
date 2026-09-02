#!/usr/bin/env python3
"""Aggregate PR1 acceptance checks and write evidence reports."""

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
    }
    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text())
    results["pinned_waike_commit"] = pin.get("pinned_commit")
    results["taxonomy_pr"] = pin.get("taxonomy_pr")

    # registry count
    export = json.loads((ROOT / "curriculum/registry/CANONICAL_TRACK_REGISTRY.export.json").read_text())
    track_count = len(export.get("tracks") or [])
    results["checks"]["registry_18"] = track_count == 18
    if track_count != 18:
        results["blocked"].append(f"registry track_count={track_count}")

    # compile
    py = ROOT / ".venv/bin/python"
    compile_cmd = [
        str(py),
        "-c",
        "from pathlib import Path; from course_compiler.compiler import compile_module; "
        "import json; r=compile_module('DIGITAL_CONFIDENCE', out_dir=Path('pack_out')); print(r['learner_zip_sha256'])",
    ]
    env = {"PYTHONPATH": str(ROOT / "tools/course_compiler"), "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}
    cp = run(compile_cmd, env=env)
    results["checks"]["compile"] = cp.returncode == 0
    if cp.returncode == 0:
        results["package_hash"] = cp.stdout.strip().splitlines()[-1]
    else:
        results["blocked"].append("compile failed: " + cp.stderr[-500:])

    # python tests
    pytest = ROOT / ".venv/bin/pytest"
    pt = run([str(pytest), "-q", str(ROOT / "tests"), str(ROOT / "services/hub/tests")], env=env)
    results["checks"]["python_tests"] = pt.returncode == 0
    out = (pt.stdout or "") + (pt.stderr or "")
    results["test_counts"]["python"] = out.strip().splitlines()[-1] if out.strip() else "unknown"
    if pt.returncode != 0:
        results["blocked"].append("python tests failed")

    # rust tests
    cargo_env = {**env, "WAIKE_DEV_DB_KEY": os.environ.get(
        "WAIKE_DEV_DB_KEY",
        "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
    )}
    rt = run(
        ["bash", "-lc", 'source "$HOME/.cargo/env" && cargo test'],
        cwd=ROOT / "apps/client/src-tauri",
        env=cargo_env,
    )
    results["checks"]["rust_tests"] = rt.returncode == 0
    results["test_counts"]["rust"] = "see cargo output"
    if rt.returncode != 0:
        results["blocked"].append("rust tests failed: " + (rt.stderr or rt.stdout)[-800:])

    # frontend
    ft = run(["bash", "-lc", "pnpm test || npm test"], cwd=ROOT / "apps/client")
    results["checks"]["frontend_tests"] = ft.returncode == 0
    if ft.returncode != 0:
        results["blocked"].append("frontend tests failed")

    # docs present
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
    results["status"] = "AUTOMATED_PIPELINE_PASS" if ok else "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"

    # write reports
    (REPORTS / "pr1_verification.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# PR1 Verification",
        "",
        f"- Status: `{results['status']}`",
        f"- Pinned WAIKE commit: `{results.get('pinned_waike_commit')}`",
        f"- Taxonomy PR: {results.get('taxonomy_pr')}",
        f"- Package hash: `{results.get('package_hash')}`",
        f"- Python: {results['test_counts'].get('python')}",
        "",
        "## Checks",
        "",
    ]
    for k, v in results["checks"].items():
        md.append(f"- {'PASS' if v else 'FAIL'} `{k}`")
    if results["blocked"]:
        md.extend(["", "## Blocked", ""])
        for b in results["blocked"]:
            md.append(f"- {b}")
    md.extend(
        [
            "",
            "## Claim language",
            "",
            "digitally implemented and automatically tested for PR 1 scope"
            if ok
            else "PR 1 automated pipeline not fully green — see blocked items.",
            "",
        ]
    )
    (REPORTS / "PR1_VERIFICATION.md").write_text("\n".join(md))
    print(json.dumps({"status": results["status"], "package_hash": results["package_hash"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
