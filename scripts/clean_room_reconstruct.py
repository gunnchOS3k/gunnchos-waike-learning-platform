#!/usr/bin/env python3
"""Document clean-room reconstruction from pinned dependency SHAs (measured)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

PINS = {
    "device_os": "4f02a48780d300a5d3a7758937b20e3bf9364d0d",
    "waike": "fbf7685bc5686201ccaa0128ee83346d59b3d584",
    "gunnchai": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
}


def _rev(path: Path) -> str | None:
    if not path.is_dir():
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None


def _porcelain(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    try:
        out = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain"], text=True
        )
    except subprocess.CalledProcessError:
        return ["__git_status_failed__"]
    return [ln for ln in out.splitlines() if ln.strip()]


def _measure_uncommitted_deps(waike: Path, device: Path, gunnchai: Path) -> tuple[bool, dict]:
    """True when a pin checkout has uncommitted dirty state (dependency drift)."""
    details = {
        "waike": _porcelain(waike)[:20],
        "device_os": _porcelain(device)[:20],
        "gunnchai": _porcelain(gunnchai)[:20],
    }
    dirty = any(details[k] for k in details)
    return dirty, details


def _measure_stale_db_reuse() -> tuple[bool, dict]:
    """True when hub/test DB appears to reuse a committed or shared stale path."""
    notes: list[str] = []
    stale = False
    committed_dbs = list(ROOT.glob("**/*.sqlite3"))
    # Ignore venv / node_modules / .tmp ephemeral noise; flag tracked-looking paths under repo root.
    suspicious = []
    for p in committed_dbs:
        rel = p.relative_to(ROOT).as_posix()
        if any(x in rel for x in (".venv/", "node_modules/", ".tmp/", "target/", "pack_out")):
            continue
        # Committed sqlite under services/ or reports/ is stale reuse risk.
        if rel.startswith(("services/", "reports/", "apps/")) or "/fixtures/" in rel:
            suspicious.append(rel)
            stale = True
    env_db = os.environ.get("GATE_D_DB_PATH") or os.environ.get("WAIKE_HUB_DB")
    if env_db:
        p = Path(env_db)
        tmp_root = Path(tempfile.gettempdir()).resolve()
        try:
            under_tmp = tmp_root in p.resolve().parents or p.resolve().parent == tmp_root
        except OSError:
            under_tmp = False
        if p.exists() and not under_tmp and "gate" not in p.name.lower():
            notes.append(f"env_db_not_temp:{env_db}")
            # Only flag when clearly a shared durable path outside temp/CI workspace.
            if str(p).startswith(str(ROOT)) and ".tmp" not in str(p):
                stale = True
                suspicious.append(str(p))
    # Fresh CI / pytest uses tmp_path — absence of committed hub.sqlite3 is the positive signal.
    if (ROOT / "hub.sqlite3").exists() or (ROOT / "services/hub/hub.sqlite3").exists():
        stale = True
        suspicious.append("committed_hub.sqlite3")
    return stale, {"suspicious_db_paths": suspicious, "notes": notes}


def _measure_prior_run_artifact_reuse() -> tuple[bool, dict]:
    """True when a prior-run artifact cache dir is being reused in-place."""
    reuse = False
    details: dict = {"checked": []}
    cache = os.environ.get("GATE_D_PRIOR_ARTIFACT_DIR", "").strip()
    prior_dir = Path(cache) if cache else ROOT / ".gate_d_prior_artifacts"
    details["checked"].append(str(prior_dir))
    if prior_dir.is_dir() and any(prior_dir.iterdir()):
        reuse = True
        details["reason"] = "prior_artifact_dir_nonempty"
    # Stale PR1 DMG marked as ok in committed reports is prior-run reuse.
    macos = REPORTS / "MACOS_DMG_VERIFICATION.json"
    if macos.is_file():
        try:
            ver = json.loads(macos.read_text(encoding="utf-8"))
            if ver.get("recovery_status") == "RECOVERED_EXACT_PR1_ARTIFACT" and ver.get("ok") is True:
                reuse = True
                details["reason"] = "recovered_pr1_dmg_ok"
        except json.JSONDecodeError:
            details["macos_json"] = "invalid"
    return reuse, details


def _measure_fixture_only_production_proof() -> tuple[bool, dict]:
    """True when production-proof evidence is fixture-only / fake-AI-as-prod.

    Returns (fixture_only, details). Desired Gate D state: fixture_only=False.
    """
    details: dict = {}
    fixture_only = False
    wf = ROOT / ".github/workflows/gate-d.yml"
    wf_text = wf.read_text(encoding="utf-8") if wf.is_file() else ""
    details["workflow_rejects_deviceos_fixture"] = (
        "fixtures/learning_os" in wf_text and "deviceos-real-tauri" in wf_text
    )
    details["workflow_unsets_learning_os_executable"] = "unset LEARNING_OS_EXECUTABLE" in wf_text
    e2e = REPORTS / "DEVICEOS_REAL_TAURI_E2E.json"
    require_e2e = os.environ.get("GATE_D_REQUIRE_DEVICEOS_E2E", "").strip() in (
        "1",
        "true",
        "TRUE",
    )
    if e2e.is_file():
        try:
            de = json.loads(e2e.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            de = {}
            if require_e2e:
                fixture_only = True
                details["deviceos_json"] = "invalid"
        blob = json.dumps(de)
        if de.get("mock") is True:
            fixture_only = True
            details["deviceos_mock"] = True
        if "fixtures/learning_os" in blob:
            fixture_only = True
            details["deviceos_fixture_path"] = True
        if de.get("launched") or de.get("acknowledged"):
            details["deviceos_real_launch_signal"] = True
        template = de.get("reason") == "COMMITTED_TEMPLATE_NOT_GATE_D_EVIDENCE"
        if template:
            details["deviceos_pending_template"] = True
            # Template is honest non-proof until verify stages this-run E2E.
            # Fail only when this-run Device OS evidence is required.
            if require_e2e:
                fixture_only = True
                details["deviceos_template_under_require"] = True
        elif require_e2e and not (de.get("launched") or de.get("acknowledged")):
            fixture_only = True
            details["deviceos_required_but_not_launched"] = True
    else:
        details["deviceos_report_absent"] = True
        if require_e2e:
            fixture_only = True
            details["deviceos_missing_under_require"] = True

    # Fake AI allowed only for test harness — never as sole production proof claim.
    details["waike_allow_fake_ai_env"] = os.environ.get("WAIKE_ALLOW_FAKE_AI", "")
    if os.environ.get("WAIKE_CLAIM_FAKE_AI_AS_PRODUCTION") == "1":
        fixture_only = True
        details["fake_ai_as_production"] = True

    # If workflow does not reject fixture binary, that is fixture-only production risk.
    if wf_text and not details["workflow_rejects_deviceos_fixture"]:
        fixture_only = True
        details["workflow_missing_fixture_guard"] = True

    return fixture_only, details


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    waike = Path(os.environ.get("WAIKE_ROOT", ROOT.parent / "waike-research-ops"))
    device = Path(os.environ.get("DEVICE_OS_ROOT", ROOT.parent / "gunnchos-device-os"))
    gunnchai = Path(os.environ.get("GUNNCHAI_ROOT", ROOT.parent / "gunnchAI3k"))

    observed = {
        "waike": _rev(waike),
        "device_os": _rev(device),
        "gunnchai": _rev(gunnchai),
        "platform": _rev(ROOT),
    }
    mismatches = {
        k: {"expected": PINS[k], "observed": observed[k]}
        for k in PINS
        if observed.get(k) and observed[k] != PINS[k]
    }

    uncommitted_deps, uncommitted_details = _measure_uncommitted_deps(waike, device, gunnchai)
    stale_db_reuse, stale_details = _measure_stale_db_reuse()
    prior_reuse, prior_details = _measure_prior_run_artifact_reuse()
    fixture_only, fixture_details = _measure_fixture_only_production_proof()

    forbidden = {
        "uncommitted_deps": uncommitted_deps,
        "stale_db_reuse": stale_db_reuse,
        "prior_run_artifact_reuse": prior_reuse,
        # Replaces hardcoded hidden_fixtures:false with measured fixture-only production proof.
        "fixture_only_production_proof": fixture_only,
    }
    measurements = {
        "uncommitted_deps": uncommitted_details,
        "stale_db_reuse": stale_details,
        "prior_run_artifact_reuse": prior_details,
        "fixture_only_production_proof": fixture_details,
    }

    pins_ok = len(mismatches) == 0
    clean_ok = not any(forbidden.values())
    ok = pins_ok and clean_ok

    data = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "fresh_workspace_from_pinned_shas_measured",
        "pins": PINS,
        "observed": observed,
        "mismatches": mismatches,
        "forbidden": forbidden,
        "measurements": measurements,
        "reconstruction_steps": [
            "Checkout platform Gate D head into empty runner workspace",
            f"Checkout waike-research-ops @{PINS['waike']}",
            f"Checkout gunnchos-device-os @{PINS['device_os']}",
            f"Checkout gunnchAI3k @{PINS['gunnchai']}",
            "Align curriculum/registry/PIN.json absolute_path_hint to checkout",
            "Install Python/Node/Rust toolchains without reusing prior pack_out/DBs",
            "Run Gate D acceptance suites; fail closed on skip/xfail masks",
            "Require this-run native + Device OS Tauri E2E (not fixture-only production proof)",
        ],
        "ci_workspace": bool(os.environ.get("GITHUB_ACTIONS")),
        "ok": ok,
    }
    (REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Gate D Clean-Room Reconstruction",
        "",
        f"Generated: {data['generated_utc']}",
        f"OK: **{data['ok']}**",
        "",
        "## Pins",
        *[f"- `{k}`: `{v}`" for k, v in PINS.items()],
        "",
        "## Observed",
        *[f"- `{k}`: `{v}`" for k, v in observed.items()],
        "",
        "## Forbidden (measured)",
        *[f"- `{k}`: `{v}`" for k, v in forbidden.items()],
        "",
        "## Steps",
        *[f"{i}. {s}" for i, s in enumerate(data["reconstruction_steps"], 1)],
    ]
    (REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"ok": data["ok"], "mismatches": mismatches, "forbidden": forbidden}, indent=2))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
