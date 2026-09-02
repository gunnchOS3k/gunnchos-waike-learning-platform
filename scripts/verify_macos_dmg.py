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

    result: dict = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recovery_status": "REGENERATED_FROM_PR1_SOURCE",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
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
            result["notarization"] = "not_claimed_for_pr1"
        run(["hdiutil", "detach", mnt])

    sums = REPORTS / "MACOS_SHA256SUMS.txt"
    sums.write_text(f"{result['dmg_sha256']}  {dmg.name}\n")
    result["ok"] = bool(
        result.get("hdiutil_verify_ok") and result.get("mount_ok") and result.get("app_present")
    )

    (REPORTS / "MACOS_DMG_VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n")
    md = [
        "# macOS DMG verification",
        "",
        f"- recovery_status: `{result['recovery_status']}`",
        f"- source_commit: `{result['source_commit']}`",
        f"- dmg_sha256: `{result['dmg_sha256']}`",
        f"- dmg_bytes: `{result['dmg_bytes']}`",
        f"- hdiutil_verify_ok: `{result.get('hdiutil_verify_ok')}`",
        f"- mount_ok: `{result.get('mount_ok')}`",
        f"- app_present: `{result.get('app_present')}`",
        f"- bundle_id: `{result.get('bundle_id')}`",
        f"- app_version: `{result.get('app_version')}`",
        f"- signing_posture: `{result.get('signing_posture')}`",
        f"- notarization: `{result.get('notarization')}`",
        f"- ok: `{result['ok']}`",
        "",
        "PR1 development artifact only — not production signing/notarization.",
        "",
    ]
    (REPORTS / "MACOS_DMG_VERIFICATION.md").write_text("\n".join(md))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
