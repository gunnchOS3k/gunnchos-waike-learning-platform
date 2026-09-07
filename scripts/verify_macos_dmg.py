#!/usr/bin/env python3
"""Verify macOS DMG/app artifacts and write MACOS_DMG_VERIFICATION reports."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    dmg_dir = ROOT / "apps/client/src-tauri/target/release/bundle/dmg"
    app_dir = ROOT / "apps/client/src-tauri/target/release/bundle/macos"
    dmgs = sorted(dmg_dir.glob("*.dmg")) if dmg_dir.is_dir() else []
    apps = sorted(app_dir.glob("*.app")) if app_dir.is_dir() else []

    head_sha = (
        os.environ.get("GATE_D_HEAD_SHA")
        or os.environ.get("GITHUB_EVENT_PULL_REQUEST_HEAD_SHA")
        or ""
    ).strip()
    if not head_sha:
        head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    gate_label = os.environ.get("GATE_NATIVE_LABEL", "Gate").strip() or "Gate"
    result: dict = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recovery_status": "THIS_RUN_NATIVE_BUILD",
        "source_commit": head_sha,
        "artifact_head_sha": head_sha,
        "ok": False,
    }

    if not dmgs:
        result["error"] = "no DMG found under release/bundle/dmg"
        (REPORTS / "MACOS_DMG_VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n")
        (REPORTS / "MACOS_DMG_VERIFICATION.md").write_text("# macOS DMG verification\n\nFAIL: no DMG\n")
        return 1

    dmg = dmgs[0]
    result["dmg_path"] = str(dmg)
    result["dmg_bytes"] = dmg.stat().st_size
    result["dmg_sha256"] = sha256(dmg)
    verify = run(["hdiutil", "verify", str(dmg)])
    result["hdiutil_verify_exit"] = verify.returncode
    result["hdiutil_verify_ok"] = verify.returncode == 0

    with tempfile.TemporaryDirectory(prefix="waike-dmg-") as mnt:
        attach = run(["hdiutil", "attach", str(dmg), "-readonly", "-nobrowse", "-mountpoint", mnt])
        result["mount_ok"] = attach.returncode == 0
        app_path = Path(mnt) / "WAIKE Learning OS.app"
        result["app_present"] = app_path.is_dir()
        if app_path.is_dir():
            info_plist = app_path / "Contents/Info.plist"
            if info_plist.is_file():
                with info_plist.open("rb") as f:
                    plist = plistlib.load(f)
                result["bundle_id"] = plist.get("CFBundleIdentifier")
                result["app_version"] = plist.get("CFBundleShortVersionString")
            cs = run(["codesign", "-dv", "--verbose=4", str(app_path)])
            result["codesign_dv"] = (cs.stderr or cs.stdout)[-2000:]
            if "Signature=adhoc" in (cs.stderr or "") or "flags=0x2(adhoc)" in (cs.stderr or "") or "adhoc" in (
                cs.stderr or ""
            ):
                result["signing_posture"] = "adhoc"
            elif "Authority=" in (cs.stderr or ""):
                result["signing_posture"] = "signed"
            else:
                result["signing_posture"] = "unsigned_or_undetermined"
            # Gate C CI builds are unsigned — never claim notarization unless genuine.
            notarized = False
            spctl = run(["spctl", "-a", "-vv", "-t", "install", str(app_path)])
            result["spctl_exit"] = spctl.returncode
            result["spctl_out"] = ((spctl.stderr or "") + (spctl.stdout or ""))[-1500:]
            if "accepted" in result["spctl_out"].lower() and "notarized" in result["spctl_out"].lower():
                notarized = True
            if notarized:
                result["notarization"] = "NOTARIZED"
                result["signing_notarization"] = "NOTARIZED"
            else:
                result["notarization"] = "NOT_NOTARIZED"
                result["signing_notarization"] = "UNSIGNED_CI_BUILD"
            # Inner app tree fingerprint for Gate C artifact provenance
            result["inner_app_sha256"] = None
            try:
                # Hash Info.plist as a stable inner artifact marker
                if info_plist.is_file():
                    result["inner_app_sha256"] = sha256(info_plist)
            except OSError:
                pass
        run(["hdiutil", "detach", mnt])

    sums = REPORTS / "MACOS_SHA256SUMS.txt"
    sums.write_text(
        f"{result['dmg_sha256']}  {dmg.name}\n"
        + (
            f"{result.get('inner_app_sha256')}  Info.plist\n"
            if result.get("inner_app_sha256")
            else ""
        )
    )
    result["gate"] = gate_label
    result["ok"] = bool(
        result.get("hdiutil_verify_ok") and result.get("mount_ok") and result.get("app_present")
    )
    # Reject ZIP-as-DMG confusion: require real .dmg path and never treat .zip as DMG.
    if not str(result.get("dmg_path", "")).lower().endswith(".dmg"):
        result["ok"] = False
        result["error"] = "dmg_path is not a .dmg (ZIP-as-DMG rejected)"

    (REPORTS / "MACOS_DMG_VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n")
    md = [
        f"# macOS DMG verification ({gate_label})",
        "",
        f"- gate: `{gate_label}`",
        f"- recovery_status: `{result['recovery_status']}`",
        f"- source_commit / artifact_head_sha: `{result['source_commit']}`",
        f"- dmg_sha256: `{result['dmg_sha256']}`",
        f"- dmg_bytes: `{result['dmg_bytes']}`",
        f"- inner_app_sha256: `{result.get('inner_app_sha256')}`",
        f"- hdiutil_verify_ok: `{result.get('hdiutil_verify_ok')}`",
        f"- mount_ok: `{result.get('mount_ok')}`",
        f"- app_present: `{result.get('app_present')}`",
        f"- bundle_id: `{result.get('bundle_id')}`",
        f"- app_version: `{result.get('app_version')}`",
        f"- signing_posture: `{result.get('signing_posture')}`",
        f"- notarization: `{result.get('notarization')}`",
        f"- signing_notarization: `{result.get('signing_notarization')}`",
        f"- ok: `{result['ok']}`",
        "",
        "This-run CI artifact — UNSIGNED_CI_BUILD / NOT_NOTARIZED unless genuine notarization is detected.",
        "Stale RECOVERED_EXACT_PR1_ARTIFACT evidence is not accepted as current native proof.",
        "",
    ]
    (REPORTS / "MACOS_DMG_VERIFICATION.md").write_text("\n".join(md))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
