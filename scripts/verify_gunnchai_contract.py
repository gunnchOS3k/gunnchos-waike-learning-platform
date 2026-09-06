#!/usr/bin/env python3
"""Verify hub gunnchAI adapter against a pinned gunnchAI3k checkout (Gate B B2).

Requires GUNNCHAI_ROOT. Emits reports/GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.{md,json}.
Exits non-zero with GUNNCHAI_CONTRACT_DRIFT on mismatch.

Also records provider-status honesty flags (B9-adjacent) without claiming local
inference unless a real assist was executed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EXPECTED_SHA = "4b4f411710e8cdb8102a7e11502f8497f68156b1"
EXPECTED_PACKAGE = "gunnchai3k"
EXPECTED_REPO = "https://github.com/gunnchOS3k/gunnchAI3k"

KEY_REL_PATHS = [
    "src/waike-mastery/modes.ts",
    "src/tutor/academicIntegrityPolicy.ts",
    "src/system-layer/privacy_policy.ts",
    "src/local-runtime/providers/cloudProvider.ts",
    "src/system-layer/product_service/cli.ts",
    "src/waike-mastery/contract.ts",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def parse_mode_permissions(ts: str) -> dict[str, dict[str, object]]:
    block = re.search(
        r"export const MODE_PERMISSIONS[^=]*=\s*\{(?P<body>.*?)\n\};",
        ts,
        re.S,
    )
    if not block:
        raise ValueError("MODE_PERMISSIONS block not found in modes.ts")
    body = block.group("body")
    modes: dict[str, dict[str, object]] = {}
    for mode_m in re.finditer(
        r"(MASTERY_BENCHMARK|LEARNER_TUTOR|EDUCATOR_COPILOT)\s*:\s*\{([^}]+)\}",
        body,
    ):
        mode = mode_m.group(1)
        fields: dict[str, object] = {}
        for fm in re.finditer(r"(\w+)\s*:\s*(true|false|'[^']+'|\"[^\"]+\")", mode_m.group(2)):
            key, raw = fm.group(1), fm.group(2)
            if raw in {"true", "false"}:
                fields[key] = raw == "true"
            else:
                fields[key] = raw.strip("'\"")
        modes[mode] = fields
    return modes


def parse_cheat_patterns(ts: str) -> list[str]:
    block = re.search(r"const CHEAT_PATTERNS\s*=\s*\[(.*?)\];", ts, re.S)
    if not block:
        return []
    return re.findall(r"/(.*?)/[a-z]*", block.group(1))


def load_adapter_module():
    sys.path.insert(0, str(ROOT / "services" / "hub"))
    # Never honor fake while verifying production-default contract.
    os.environ.pop("GUNNCHAI_PROVIDER", None)
    os.environ.pop("WAIKE_ALLOW_FAKE_AI", None)
    from app.modules import gunnchai_adapter as mod  # noqa: WPS433

    return mod


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    drift: list[str] = []
    root_env = os.environ.get("GUNNCHAI_ROOT", "").strip()
    if not root_env:
        print("GUNNCHAI_CONTRACT_DRIFT: GUNNCHAI_ROOT is required", file=sys.stderr)
        return 2
    gunnchai = Path(root_env).resolve()
    if not gunnchai.is_dir():
        print(f"GUNNCHAI_CONTRACT_DRIFT: GUNNCHAI_ROOT missing: {gunnchai}", file=sys.stderr)
        return 2

    try:
        observed_sha = git_head(gunnchai)
    except subprocess.CalledProcessError as exc:
        print(f"GUNNCHAI_CONTRACT_DRIFT: cannot rev-parse: {exc}", file=sys.stderr)
        return 2

    if observed_sha != EXPECTED_SHA:
        drift.append(f"pin_sha expected={EXPECTED_SHA} observed={observed_sha}")

    file_hashes: dict[str, str] = {}
    missing_files: list[str] = []
    for rel in KEY_REL_PATHS:
        path = gunnchai / rel
        if not path.is_file():
            missing_files.append(rel)
            continue
        file_hashes[rel] = sha256_file(path)
    if missing_files:
        drift.append(f"missing_source_files:{missing_files}")

    mod = load_adapter_module()
    adapter_sha = getattr(mod, "GUNNCHAI_SHA", None)
    adapter_package = getattr(mod, "GUNNCHAI_PACKAGE", None)
    adapter_repo = getattr(mod, "GUNNCHAI_REPO", None)
    adapter_modes = getattr(mod, "MODE_PERMISSIONS", {})
    cheat_res = getattr(mod, "CHEAT_PATTERNS", [])

    if adapter_sha != EXPECTED_SHA:
        drift.append(f"adapter_sha expected={EXPECTED_SHA} adapter={adapter_sha}")
    if adapter_package != EXPECTED_PACKAGE:
        drift.append(f"adapter_package expected={EXPECTED_PACKAGE} adapter={adapter_package}")
    if adapter_repo != EXPECTED_REPO:
        drift.append(f"adapter_repo expected={EXPECTED_REPO} adapter={adapter_repo}")

    modes_ts = (
        (gunnchai / "src/waike-mastery/modes.ts").read_text(encoding="utf-8")
        if (gunnchai / "src/waike-mastery/modes.ts").is_file()
        else ""
    )
    source_modes = parse_mode_permissions(modes_ts) if modes_ts else {}
    if set(source_modes) != set(adapter_modes):
        drift.append(
            f"mode_keys source={sorted(source_modes)} adapter={sorted(adapter_modes)}"
        )
    for mode, src_fields in source_modes.items():
        ad_fields = adapter_modes.get(mode) or {}
        for key, src_val in src_fields.items():
            if key not in ad_fields:
                drift.append(f"mode_field_missing mode={mode} field={key}")
            elif ad_fields[key] != src_val:
                drift.append(
                    f"mode_field_mismatch mode={mode} field={key} "
                    f"source={src_val!r} adapter={ad_fields[key]!r}"
                )

    integrity_ts = (
        (gunnchai / "src/tutor/academicIntegrityPolicy.ts").read_text(encoding="utf-8")
        if (gunnchai / "src/tutor/academicIntegrityPolicy.ts").is_file()
        else ""
    )
    source_cheats = parse_cheat_patterns(integrity_ts)
    adapter_cheats = [getattr(p, "pattern", str(p)) for p in cheat_res]
    for pat in source_cheats:
        if not any(pat == a or pat in a or a in pat for a in adapter_cheats):
            drift.append(f"cheat_pattern_missing_in_adapter:{pat}")

    privacy_ts = (
        (gunnchai / "src/system-layer/privacy_policy.ts").read_text(encoding="utf-8")
        if (gunnchai / "src/system-layer/privacy_policy.ts").is_file()
        else ""
    )
    if privacy_ts and "local-only" not in privacy_ts and "localOnly" not in privacy_ts:
        drift.append("privacy_policy_missing_local_only_default_marker")

    cloud_ts = (
        (gunnchai / "src/local-runtime/providers/cloudProvider.ts").read_text(encoding="utf-8")
        if (gunnchai / "src/local-runtime/providers/cloudProvider.ts").is_file()
        else ""
    )
    if cloud_ts and not re.search(
        r"CLOUD_NOT_IMPLEMENTED|not\s+implemented|fail.?closed", cloud_ts, re.I
    ):
        drift.append("cloudProvider_missing_fail_closed_marker")

    cli_path = gunnchai / "src/system-layer/product_service/cli.ts"
    contract_path = gunnchai / "src/waike-mastery/contract.ts"
    if cli_path.is_file() and "assist" not in cli_path.read_text(encoding="utf-8"):
        drift.append("product_service_cli_missing_assist")
    if contract_path.is_file():
        ctext = contract_path.read_text(encoding="utf-8")
        if "discoverCourses" not in ctext and "discoverCoursesFromContract" not in ctext:
            drift.append("contract_ts_missing_course_discovery")

    # Provider honesty snapshot (does not claim inference ran).
    adapter = mod.GunnchAIAdapter()
    status = (
        adapter.provider_status()
        if hasattr(adapter, "provider_status")
        else adapter.contract_meta()
    )
    active = (status.get("provider") or {}).get("active") or status.get("active_provider")
    if isinstance(adapter.provider, mod.FakeGunnchAIProvider):
        drift.append("default_adapter_selected_fake_provider")
    if active == "fake-gunnchai":
        drift.append("default_active_provider_is_fake")

    ok = len(drift) == 0
    snapshot = {
        "schema": "gate_b_gunnchai_contract_snapshot_v1",
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "GUNNCHAI_CONTRACT_DRIFT",
        "expected_sha": EXPECTED_SHA,
        "observed_sha": observed_sha,
        "gunnchai_root": str(gunnchai),
        "repo": EXPECTED_REPO,
        "package": EXPECTED_PACKAGE,
        "key_file_sha256": file_hashes,
        "source_mode_permissions": source_modes,
        "adapter_mode_permissions": adapter_modes,
        "source_cheat_patterns": source_cheats,
        "adapter_cheat_pattern_count": len(adapter_cheats),
        "provider_status": status,
        "DEFAULT_RUNTIME_HAS_NO_FAKE_AI": bool(
            getattr(mod, "DEFAULT_RUNTIME_HAS_NO_FAKE_AI", False)
        ),
        "drift": drift,
    }
    (REPORTS / "GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.json").write_text(
        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Gate B — gunnchAI canonical contract snapshot",
        "",
        f"- Status: `{snapshot['status']}`",
        f"- Expected SHA: `{EXPECTED_SHA}`",
        f"- Observed SHA: `{observed_sha}`",
        f"- GUNNCHAI_ROOT: `{gunnchai}`",
        f"- DEFAULT_RUNTIME_HAS_NO_FAKE_AI: `{snapshot['DEFAULT_RUNTIME_HAS_NO_FAKE_AI']}`",
        "",
        "## Key file SHA-256",
        "",
    ]
    for rel, digest in file_hashes.items():
        md.append(f"- `{rel}` → `{digest}`")
    md.extend(["", "## Drift", ""])
    if drift:
        for item in drift:
            md.append(f"- {item}")
    else:
        md.append("- none")
    md.append("")
    (REPORTS / "GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.md").write_text(
        "\n".join(md), encoding="utf-8"
    )

    if not ok:
        print("GUNNCHAI_CONTRACT_DRIFT", file=sys.stderr)
        for item in drift:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "observed_sha": observed_sha}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
