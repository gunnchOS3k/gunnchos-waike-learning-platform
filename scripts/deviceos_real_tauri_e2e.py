#!/usr/bin/env python3
"""Cross-repo Device OS → actual Platform Tauri binary launch E2E + sabotage.

Uses the real `waike-learning-client` / installed `waike-learning-os` binary — never the
Device OS protocol fixture — as the Learning OS executable.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVICE_OS_ROOT = Path(
    os.environ.get("DEVICE_OS_ROOT", ROOT.parent / "gunnchos-device-os")
).resolve()
BUNDLE_ID = "com.gunnchos.waike.learning"
PROTOCOL = "gunnchos.learning_os.ipc.v1"
APP_VERSION = os.environ.get("LEARNING_OS_APP_VERSION", "0.1.0")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_binary() -> Path:
    env = os.environ.get("LEARNING_OS_REAL_BINARY")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise SystemExit(f"LEARNING_OS_REAL_BINARY not found: {p}")
    candidates = [
        ROOT
        / "apps/client/src-tauri/target/release/waike-learning-client",
        ROOT
        / "apps/client/src-tauri/target/debug/waike-learning-client",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise SystemExit(
        "Actual Platform Tauri binary not found. Build apps/client/src-tauri first."
    )


def install_binary(bin_src: Path, install_root: Path) -> Path:
    bin_dir = install_root / "bin"
    bin_dir.mkdir(parents=True)
    dest = bin_dir / "waike-learning-os"
    shutil.copy2(bin_src, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (bin_dir / "VERSION").write_text(APP_VERSION + "\n", encoding="utf-8")
    meta = {
        "bundle_id": BUNDLE_ID,
        "version": APP_VERSION,
        "artifact_sha256": _sha256(dest),
        "source_binary": str(bin_src),
        "platform_sha": os.environ.get("LEARNING_OS_PLATFORM_SHA")
        or os.environ.get("GITHUB_SHA")
        or "local",
        "device_os_sha": os.environ.get("DEVICE_OS_PIN_REF")
        or "local",
    }
    (bin_dir / "INSTALLED.json").write_text(json.dumps(meta, indent=2) + "\n")
    return dest


def _ensure_device_os_path() -> None:
    if not DEVICE_OS_ROOT.is_dir():
        raise SystemExit(f"DEVICE_OS_ROOT missing: {DEVICE_OS_ROOT}")
    sys.path.insert(0, str(DEVICE_OS_ROOT))


def run_happy_path(install_root: Path, reports: Path) -> dict:
    from gunnchos_device_os.learning_os.native_launch import NativeLaunchAdapter

    os.environ["WAIKE_CI_HEADLESS_UI"] = "1"
    os.environ["CI_HEADLESS_UI"] = "1"
    os.environ["LEARNING_OS_CLEANUP_AFTER_ACK"] = "1"
    os.environ["LEARNING_OS_APP_VERSION"] = APP_VERSION
    os.environ["WAIKE_DEV_DB_KEY"] = os.environ.get(
        "WAIKE_DEV_DB_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )

    adapter = NativeLaunchAdapter(install_root=install_root, timeout_s=20.0)
    result = adapter.launch(deep_link="waike://learn/home", profile="student", mode="School")
    evidence = result.to_dict()
    evidence["executable_sha256"] = result.artifact_hash
    evidence["install_root"] = str(install_root)

    # Deep link surfaced via Platform launch-context evidence file.
    req_id = None
    ipc = evidence.get("ipc") or {}
    req = (ipc.get("request") or {})
    req_id = req.get("request_id")
    launch_ctx = None
    if req_id and result.ipc:
        # NativeLaunchAdapter ipc_dir
        ipc_dirs = list(Path(tempfile.gettempdir()).glob("waike-los-ipc-*"))
        # Prefer adapter.ipc_dir
        cand = Path(adapter.ipc_dir) / f"launch-context-{req_id}.json"
        if cand.is_file():
            launch_ctx = json.loads(cand.read_text(encoding="utf-8"))
        else:
            ack_path = Path(adapter.ipc_dir) / f"ack-{req_id}.json"
            if ack_path.is_file():
                ack = json.loads(ack_path.read_text(encoding="utf-8"))
                launch_ctx = {
                    "deep_link": {"canonical": ack.get("deep_link")},
                    "from_ack": True,
                }
    evidence["launch_context"] = launch_ctx
    evidence["adapter_ipc_dir"] = str(adapter.ipc_dir)

    reports.mkdir(parents=True, exist_ok=True)
    (reports / "DEVICEOS_REAL_TAURI_E2E.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Device OS ↔ Actual Tauri Runtime E2E",
        "",
        f"- launched: `{evidence.get('launched')}`",
        f"- process_started: `{evidence.get('process_started')}`",
        f"- acknowledged: `{evidence.get('acknowledged')}`",
        f"- deep_link_delivered: `{evidence.get('deep_link_delivered')}`",
        f"- executable: `{evidence.get('executable')}`",
        f"- executable_sha256: `{evidence.get('executable_sha256')}`",
        f"- version: `{evidence.get('version')}`",
        f"- reason: `{evidence.get('reason')}`",
        f"- launch_context: `{json.dumps(launch_ctx)}`",
        "",
    ]
    (reports / "DEVICEOS_REAL_TAURI_E2E.md").write_text("\n".join(md), encoding="utf-8")

    assert result.process_started is True, evidence
    assert result.deep_link_delivered is True, evidence
    assert result.acknowledged is True, evidence
    assert result.launched is True, evidence
    ack = ((evidence.get("ipc") or {}).get("result") or {}).get("ack") or {}
    assert ack.get("bundle_id") == BUNDLE_ID, ack
    assert ack.get("app_version") == APP_VERSION, ack
    assert ack.get("protocol") == PROTOCOL, ack
    assert launch_ctx is not None, "missing launch-context evidence"
    dl = launch_ctx.get("deep_link") or {}
    canonical = dl.get("canonical") if isinstance(dl, dict) else dl
    assert canonical == "waike://learn/home" or (
        isinstance(dl, dict) and dl.get("kind") == "learn"
    ), launch_ctx
    # Guard: fixture must not be the executable under test.
    assert "fixtures/learning_os" not in str(result.executable), result.executable
    return evidence


def _run_sabotage_case(name: str, install_root: Path, mutate) -> dict:
    """Launch with a mutated request / env; expect launched=false and clear reason."""
    from gunnchos_device_os.learning_os.native_launch import NativeLaunchAdapter
    from gunnchos_device_os.learning_os.ipc_protocol import build_launch_request
    from gunnchos_device_os.app_registry import LEARNING_OS_BUNDLE_ID
    import uuid

    os.environ["WAIKE_CI_HEADLESS_UI"] = "1"
    os.environ["LEARNING_OS_CLEANUP_AFTER_ACK"] = "1"
    os.environ["LEARNING_OS_APP_VERSION"] = APP_VERSION
    os.environ.setdefault(
        "WAIKE_DEV_DB_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )

    adapter = NativeLaunchAdapter(install_root=install_root, timeout_s=8.0)
    # Custom launch that lets us mutate the request on disk / CLI.
    discovery = adapter.discover()
    assert discovery["available"], discovery
    exe = Path(discovery["executable"])
    request_id = str(uuid.uuid4())
    ipc_dir = Path(tempfile.mkdtemp(prefix="waike-los-sab-"))
    deep = "waike://learn/home"
    request = build_launch_request(
        request_id=request_id,
        deep_link={
            "uri": deep,
            "canonical": deep,
            "valid": True,
            "kind": "learn",
            "path": "home",
        },
        context={"profile": "student", "mode": "School", "bundle_id": LEARNING_OS_BUNDLE_ID},
        bundle_id=LEARNING_OS_BUNDLE_ID,
    )
    cli_deep = deep
    bundle = LEARNING_OS_BUNDLE_ID
    skip_request = False
    request, cli_deep, bundle, skip_request, expect_reason = mutate(
        request, cli_deep, bundle, skip_request
    )

    if not skip_request:
        (ipc_dir / f"request-{request_id}.json").write_text(
            json.dumps(request, indent=2) + "\n", encoding="utf-8"
        )

    env = os.environ.copy()
    env["LEARNING_OS_IPC_DIR"] = str(ipc_dir)
    env["LEARNING_OS_REQUEST_ID"] = request_id
    env["WAIKE_CI_HEADLESS_UI"] = "1"
    proc = subprocess.Popen(
        [
            str(exe),
            "--bundle-id",
            bundle,
            "--deep-link",
            cli_deep,
            "--ipc-dir",
            str(ipc_dir),
            "--request-id",
            request_id,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # For missing request: do not write; process should NACK/timeout.
    deadline = time.monotonic() + 12.0
    ack = None
    ack_path = ipc_dir / f"ack-{request_id}.json"
    while time.monotonic() < deadline:
        if ack_path.is_file():
            try:
                ack = json.loads(ack_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                ack = {"bad": True}
            break
        if proc.poll() is not None:
            time.sleep(0.1)
            if ack_path.is_file():
                try:
                    ack = json.loads(ack_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    ack = {"bad": True}
            break
        time.sleep(0.02)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    launched = bool(ack and ack.get("message_type") == "ack" and ack.get("status") == "ok")
    reason = None
    if ack and ack.get("message_type") == "nack":
        reason = ack.get("reason")
    elif not ack:
        reason = "timeout_or_no_ack"
    # Secret leakage check
    blob = json.dumps(ack or {})
    assert "password" not in blob.lower() or "secret_context" in (reason or "")
    assert not launched, (name, ack)
    assert reason, (name, ack)
    if expect_reason:
        assert expect_reason in str(reason), (name, reason, expect_reason)
    return {"name": name, "launched": False, "reason": reason, "ack": ack}


def run_sabotage(install_root: Path, reports: Path) -> list[dict]:
    cases = []

    def missing(req, cli, bundle, skip):
        # Process waits then NACKs; timing may surface as timeout_or_no_ack.
        return req, cli, bundle, True, None

    def malformed(req, cli, bundle, skip):
        # overwrite with garbage after mutate returns — handled below
        return req, cli, bundle, False, "bad_payload"

    def wrong_protocol(req, cli, bundle, skip):
        req = {**req, "protocol": "evil.v0"}
        return req, cli, bundle, False, "wrong_protocol"

    def wrong_bundle(req, cli, bundle, skip):
        req = {**req, "bundle_id": "com.evil.app"}
        return req, cli, bundle, False, "wrong_bundle"

    def wrong_request_id(req, cli, bundle, skip):
        req = {**req, "request_id": "other-id"}
        return req, cli, bundle, False, "request_id_mismatch"

    def traversal(req, cli, bundle, skip):
        bad = "waike://learn/../etc"
        req = {
            **req,
            "deep_link": {"uri": bad, "canonical": bad, "valid": True, "kind": "learn", "path": "../etc"},
        }
        return req, bad, bundle, False, None

    def encoded_traversal(req, cli, bundle, skip):
        bad = "waike://learn/%2e%2e/secret"
        req = {
            **req,
            "deep_link": {
                "uri": bad,
                "canonical": bad,
                "valid": True,
                "kind": "learn",
                "path": "%2e%2e/secret",
            },
        }
        return req, bad, bundle, False, None

    def unknown_ctx(req, cli, bundle, skip):
        req = {**req, "context": {**req["context"], "evil_field": "x"}}
        return req, cli, bundle, False, "unknown_context_field"

    def secret_ctx(req, cli, bundle, skip):
        req = {**req, "context": {**req["context"], "password": "secret"}}
        return req, cli, bundle, False, "secret_context_field"

    def mismatch(req, cli, bundle, skip):
        return req, "waike://section/other", bundle, False, "deep_link_mismatch"

    mutators = [
        ("missing_request_file", missing),
        ("malformed_json", malformed),
        ("wrong_protocol", wrong_protocol),
        ("wrong_bundle_id", wrong_bundle),
        ("wrong_request_id", wrong_request_id),
        ("deep_link_traversal", traversal),
        ("encoded_traversal", encoded_traversal),
        ("unknown_context_field", unknown_ctx),
        ("secret_field", secret_ctx),
        ("cli_request_deep_link_mismatch", mismatch),
    ]

    for name, mut in mutators:
        if name == "malformed_json":
            # special: write garbage
            from gunnchos_device_os.learning_os.native_launch import NativeLaunchAdapter
            import uuid

            os.environ["WAIKE_CI_HEADLESS_UI"] = "1"
            adapter = NativeLaunchAdapter(install_root=install_root, timeout_s=8.0)
            exe = Path(adapter.discover()["executable"])
            rid = str(uuid.uuid4())
            ipc = Path(tempfile.mkdtemp(prefix="waike-los-sab-"))
            (ipc / f"request-{rid}.json").write_text("{not-json", encoding="utf-8")
            env = os.environ.copy()
            env["WAIKE_CI_HEADLESS_UI"] = "1"
            env["WAIKE_DEV_DB_KEY"] = os.environ["WAIKE_DEV_DB_KEY"]
            proc = subprocess.Popen(
                [
                    str(exe),
                    "--bundle-id",
                    BUNDLE_ID,
                    "--deep-link",
                    "waike://learn/home",
                    "--ipc-dir",
                    str(ipc),
                    "--request-id",
                    rid,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ack_path = ipc / f"ack-{rid}.json"
            deadline = time.monotonic() + 8.0
            ack = None
            while time.monotonic() < deadline:
                if ack_path.is_file():
                    ack = json.loads(ack_path.read_text(encoding="utf-8"))
                    break
                time.sleep(0.02)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            assert ack and ack.get("message_type") == "nack", ack
            cases.append(
                {"name": name, "launched": False, "reason": ack.get("reason"), "ack": ack}
            )
            continue
        cases.append(_run_sabotage_case(name, install_root, mut))

    # Device OS adapter-level timeout (no receiver ack)
    from gunnchos_device_os.learning_os.native_launch import NativeLaunchAdapter
    from gunnchos_device_os.learning_os.ipc_transport import DeterministicTestTransport

    adapter = NativeLaunchAdapter(
        install_root=install_root,
        transport=DeterministicTestTransport(fail_reason="timeout"),
        timeout_s=0.2,
    )
    os.environ["LEARNING_OS_CLEANUP_AFTER_ACK"] = "1"
    r = adapter.launch(deep_link="waike://learn/home")
    assert r.launched is False
    assert r.reason == "timeout"
    cases.append({"name": "device_os_timeout", "launched": False, "reason": r.reason})

    reports.mkdir(parents=True, exist_ok=True)
    (reports / "DEVICEOS_REAL_TAURI_SABOTAGE.json").write_text(
        json.dumps({"cases": cases}, indent=2) + "\n", encoding="utf-8"
    )
    return cases


def main() -> int:
    _ensure_device_os_path()
    reports = ROOT / "reports"
    bin_src = resolve_binary()
    # Never allow the Device OS fixture path.
    if "fixtures/learning_os" in str(bin_src):
        raise SystemExit("Refusing Device OS fixture as real Tauri binary")
    with tempfile.TemporaryDirectory(prefix="los-real-install-") as tmp:
        install_root = Path(tmp)
        installed = install_binary(bin_src, install_root)
        print(f"installed_real_binary={installed}", flush=True)
        print(f"sha256={_sha256(installed)}", flush=True)
        mode = os.environ.get("E2E_MODE", "all")
        if mode in ("all", "happy"):
            run_happy_path(install_root, reports)
            print("HAPPY_PATH_PASS", flush=True)
        if mode in ("all", "sabotage"):
            cases = run_sabotage(install_root, reports)
            print(f"SABOTAGE_PASS cases={len(cases)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
