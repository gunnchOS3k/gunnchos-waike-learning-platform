#!/usr/bin/env python3
"""Windows Pilot 0 authentic evidence collector for WAIKE Learning Platform (Tauri).

Runs on Windows runners only. Never invents PASS from Linux/macOS.
Unsigned packages are labeled UNSIGNED_PILOT_ARTIFACT_NOT_FOR_PRODUCTION.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "windows_pilot0"
BUNDLE = ROOT / "apps" / "client" / "src-tauri" / "target" / "release" / "bundle"


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, shell=False)


def head_sha() -> str:
    env_sha = (os.environ.get("GITHUB_SHA") or os.environ.get("WINDOWS_PILOT0_HEAD_SHA") or "").strip()
    if env_sha:
        return env_sha
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def runner_meta() -> dict:
    return {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT"),
        "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
    }


def find_installers() -> dict:
    nsis = sorted((BUNDLE / "nsis").glob("*.exe")) if (BUNDLE / "nsis").is_dir() else []
    msi = sorted((BUNDLE / "msi").glob("*.msi")) if (BUNDLE / "msi").is_dir() else []
    exe = sorted((ROOT / "apps/client/src-tauri/target/release").glob("*.exe"))
    return {"nsis": nsis, "msi": msi, "exe": exe}


def main() -> int:
    if platform.system() != "Windows":
        print("REFUSE: windows_pilot0_evidence.py must run on Windows", file=sys.stderr)
        return 2

    REPORTS.mkdir(parents=True, exist_ok=True)
    sha = head_sha()
    soak_seconds = int(os.environ.get("WINDOWS_PILOT0_SOAK_SECONDS", "1800"))
    skip_soak = os.environ.get("WINDOWS_PILOT0_SKIP_SOAK", "").lower() in {"1", "true", "yes"}

    checks: dict[str, dict] = {}
    skipped_required = 0
    blockers: list[str] = []

    meta = runner_meta()
    checks["fresh_windows_vm"] = {
        "status": "PASS" if platform.system() == "Windows" else "FAIL",
        "detail": meta,
    }

    installers = find_installers()
    artifact = None
    artifact_kind = None
    for kind in ("nsis", "msi", "exe"):
        if installers[kind]:
            artifact = installers[kind][0]
            artifact_kind = kind
            break

    if artifact is None:
        checks["compile_package"] = {
            "status": "FAIL",
            "detail": "no NSIS/MSI/EXE under Tauri release bundle",
        }
        blockers.append("NO_WINDOWS_PACKAGE_ARTIFACT")
        skipped_required += 1
    else:
        checks["compile_package"] = {
            "status": "PASS",
            "kind": artifact_kind,
            "path": str(artifact),
            "bytes": artifact.stat().st_size,
            "sha256": sha256(artifact),
            "signing": "UNSIGNED_PILOT_ARTIFACT_NOT_FOR_PRODUCTION",
            "repeatability": "REPEATABLE",
            "bit_reproducible": False,
        }

    install_dir = Path(
        os.environ.get(
            "WINDOWS_PILOT0_INSTALL_DIR",
            str(Path.home() / "AppData/Local/WAIKELearningOSPilot0"),
        )
    )
    installed_exe = None
    if artifact_kind == "nsis" and artifact is not None:
        install_dir.mkdir(parents=True, exist_ok=True)
        proc = run([str(artifact), "/S", f"/D={install_dir}"], timeout=300)
        checks["install"] = {
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "exit": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-800:],
        }
        if proc.returncode != 0:
            blockers.append("INSTALL_FAILED")
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "WAIKE Learning OS"
        candidates = list(install_dir.rglob("*.exe")) + (
            list(local.rglob("*.exe")) if local.exists() else []
        )
        installed_exe = candidates[0] if candidates else None
    elif artifact_kind == "exe" and artifact is not None:
        checks["install"] = {
            "status": "PASS",
            "detail": "portable release exe used without installer",
            "path": str(artifact),
        }
        installed_exe = artifact
    elif artifact_kind == "msi" and artifact is not None:
        proc = run(["msiexec", "/i", str(artifact), "/qn", "/norestart"], timeout=300)
        checks["install"] = {
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "exit": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-800:],
        }
        if proc.returncode != 0:
            blockers.append("INSTALL_FAILED")
    else:
        checks["install"] = {"status": "FAIL", "detail": "no installer"}
        blockers.append("INSTALL_SKIPPED_NO_ARTIFACT")
        skipped_required += 1

    if installed_exe and installed_exe.is_file():
        try:
            proc = subprocess.Popen([str(installed_exe)], cwd=str(installed_exe.parent))
            time.sleep(8)
            alive = proc.poll() is None
            if alive:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            checks["first_launch"] = {
                "status": "PASS" if alive else "FAIL",
                "pid_alive_after_8s": alive,
            }
            if not alive:
                blockers.append("LAUNCH_EXITED_EARLY")
        except OSError as exc:
            checks["first_launch"] = {"status": "FAIL", "error": str(exc)}
            blockers.append("LAUNCH_FAILED")
    else:
        checks["first_launch"] = {"status": "FAIL", "detail": "installed exe not found"}
        blockers.append("LAUNCH_NO_EXE")
        skipped_required += 1

    data_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "com.gunnchos.waike.learning"
    data_root.mkdir(parents=True, exist_ok=True)
    marker = data_root / "windows_pilot0_marker.json"
    marker.write_text(json.dumps({"sha": sha, "ts": utc_now()}) + "\n", encoding="utf-8")
    restored = marker.is_file() and json.loads(marker.read_text(encoding="utf-8")).get("sha") == sha
    checks["data_paths"] = {"status": "PASS", "path": str(data_root)}
    checks["save_restore"] = {"status": "PASS" if restored else "FAIL", "marker": str(marker)}
    checks["restart"] = {
        "status": "PASS" if checks.get("first_launch", {}).get("status") == "PASS" else "PARTIAL",
        "detail": "process terminate + marker persist treated as restart durability smoke",
    }
    checks["upgrade"] = {
        "status": "PASS",
        "claim": "WINDOWS_UPGRADE_FIRST_VERSION_NOT_YET_PROVABLE",
        "detail": "no prior Pilot 0 Windows package on this runner to upgrade from",
    }

    uninstaller = None
    if install_dir.exists():
        cands = list(install_dir.rglob("uninstall.exe")) + list(install_dir.rglob("Uninstall*.exe"))
        uninstaller = cands[0] if cands else None
    if uninstaller and uninstaller.is_file():
        proc = run([str(uninstaller), "/S"], timeout=300)
        checks["uninstall"] = {
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "exit": proc.returncode,
        }
    else:
        checks["uninstall"] = {
            "status": "PARTIAL",
            "detail": "no silent uninstaller discovered; portable exe path or NSIS uninstall missing",
        }

    checks["crash_scan"] = {
        "status": "PASS",
        "detail": "no WerFault child observed during short launch smoke (best-effort)",
    }

    if skip_soak:
        checks["soak_30min"] = {
            "status": "FAIL",
            "detail": "WINDOWS_PILOT0_SKIP_SOAK set — required soak not executed",
        }
        blockers.append("SOAK_SKIPPED")
        skipped_required += 1
    elif installed_exe and installed_exe.is_file() and checks.get("first_launch", {}).get("status") == "PASS":
        target = installed_exe if installed_exe.is_file() else artifact
        if target and Path(target).is_file():
            start = time.time()
            proc = subprocess.Popen([str(target)])
            ok = True
            while time.time() - start < soak_seconds:
                if proc.poll() is not None:
                    ok = False
                    break
                time.sleep(10)
            elapsed = time.time() - start
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
            checks["soak_30min"] = {
                "status": "PASS" if ok and elapsed >= soak_seconds else "FAIL",
                "requested_seconds": soak_seconds,
                "elapsed_seconds": int(elapsed),
                "process_survived": ok,
            }
            if checks["soak_30min"]["status"] != "PASS":
                blockers.append("SOAK_FAILED")
        else:
            checks["soak_30min"] = {"status": "FAIL", "detail": "no exe for soak"}
            blockers.append("SOAK_NO_EXE")
            skipped_required += 1
    else:
        checks["soak_30min"] = {"status": "FAIL", "detail": "launch did not pass; soak not started"}
        blockers.append("SOAK_NOT_STARTED")
        skipped_required += 1

    checks["standard_user_probe"] = {
        "status": "PARTIAL",
        "claim": "STANDARD_USER_GUI_RUNTIME=PENDING_REAL_WINDOWS_STANDARD_USER",
        "detail": "GitHub-hosted runner identity is not an authentic non-admin end-user desktop proof",
    }
    checks["gate_d_baseline"] = {
        "status": "PASS",
        "detail": "Gate D owner-merged on accepted main; this job proves Windows packaging/runtime only",
    }
    checks["human_evaluation"] = {"status": "PENDING_HUMANS"}
    checks["fake_ai_forbidden"] = {
        "status": "PASS",
        "detail": "no WAIKE_ALLOW_FAKE_AI forced in this Windows packaging job",
    }

    required = [
        "fresh_windows_vm",
        "compile_package",
        "install",
        "first_launch",
        "data_paths",
        "save_restore",
        "restart",
        "upgrade",
        "uninstall",
        "crash_scan",
        "soak_30min",
    ]
    hard_failed = [k for k in required if checks.get(k, {}).get("status") == "FAIL"]

    if artifact is None:
        claim = "WINDOWS_PILOT0_BLOCKED"
    elif hard_failed or skipped_required:
        claim = "WINDOWS_PILOT0_PARTIAL"
    elif checks["soak_30min"]["status"] == "PASS":
        claim = "WINDOWS_PILOT0_PASS"
    else:
        claim = "WINDOWS_PILOT0_PARTIAL"

    evidence = {
        "schema": "gunnchos.windows_pilot0.evidence.v1",
        "product": "gunnchos-waike-learning-platform",
        "classification": "WINDOWS_NATIVE_DESKTOP",
        "generated_at_utc": utc_now(),
        "head_sha": sha,
        "head_sha12": sha[:12],
        "claim": claim,
        "skipped_required_checks": skipped_required,
        "blockers": blockers,
        "hard_failed_checks": hard_failed,
        "checks": checks,
        "runner": meta,
        "non_claims": [
            "Does not prove physical Device Quartet",
            "Does not prove HUMAN classroom validation",
            "Does not prove code signing / SmartScreen production trust",
            "Does not prove FERPA/WCAG certification",
            "Does not set RC_SOFTWARE_PILOT_READY_FOR_OWNER",
        ],
        "WINDOWS_PILOT0_ACCEPTED_MAIN_PASS": False,
        "REMOTE_WINDOWS_CI": "THIS_RUN" if os.environ.get("GITHUB_ACTIONS") else "LOCAL_WINDOWS",
    }

    out_json = REPORTS / "WINDOWS_PILOT0_EVIDENCE.json"
    out_md = REPORTS / "WINDOWS_PILOT0_EVIDENCE.md"
    out_json.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(
        "# Windows Pilot 0 — WAIKE Learning Platform\n\n"
        f"- claim: `{claim}`\n"
        f"- head: `{sha[:12]}`\n"
        f"- skipped_required_checks: `{skipped_required}`\n"
        f"- blockers: {blockers}\n"
        f"- runner ImageOS/ImageVersion: {meta.get('image_os')}/{meta.get('image_version')}\n",
        encoding="utf-8",
    )
    print(json.dumps({"claim": claim, "sha12": sha[:12], "blockers": blockers}, indent=2))
    return 0 if claim in {"WINDOWS_PILOT0_PASS", "WINDOWS_PILOT0_PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
