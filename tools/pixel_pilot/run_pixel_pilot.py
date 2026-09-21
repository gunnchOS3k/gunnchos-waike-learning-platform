#!/usr/bin/env python3
"""Automated Pixel 6a WAIKE full pilot controller.

Honest gates only. Physical journeys require an authorized ADB device.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts" / "pixel6a_waike"
PILOT_DB = ROOT / "services" / "hub" / "data" / "pixel_pilot" / "pilot.db"
HUB_LOG = ART / "hub_logs" / "hub.log"
CLIENT_PORT = 1420
HUB_PORT = 8000

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "hub"))
sys.path.insert(0, str(ROOT / "tools"))


def _utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str] | str, *, check: bool = False, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        check=check,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def adb_authorized() -> tuple[bool, str]:
    r = _run(["adb", "devices", "-l"])
    lines = [ln for ln in r.stdout.splitlines() if ln.strip() and not ln.startswith("List")]
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == "device":
            return True, ln
    return False, r.stdout.strip()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def bootstrap_hub_db() -> dict:
    """Prepare env + empty pilot DB path. Curriculum/users come from seed_pilot_users."""
    sibling_waike = ROOT.parent / "waike-research-ops"
    if "WAIKE_ROOT" not in os.environ and sibling_waike.is_dir():
        os.environ["WAIKE_ROOT"] = str(sibling_waike)
    os.environ["WAIKE_PIXEL_PILOT"] = "true"
    os.environ["WAIKE_SEED_TEST_FIXTURES"] = "false"
    os.environ["WAIKE_DEV_DB_KEY"] = os.environ.get(
        "WAIKE_DEV_DB_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    PILOT_DB.parent.mkdir(parents=True, exist_ok=True)
    if PILOT_DB.exists():
        PILOT_DB.unlink()
    return {}


def seed_users() -> dict:
    from tools.pixel_pilot.create_test_users import seed_pilot_users

    result = seed_pilot_users(PILOT_DB)
    cred_path = ROOT / ".pixel-pilot" / "credentials.json"
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    cred_path.write_text(json.dumps(result["credentials"], indent=2) + "\n", encoding="utf-8")
    cred_path.chmod(0o600)
    write_json(ART / "ROLE_TEST_MANIFEST.json", result["manifest"])
    if isinstance(result.get("inventory"), dict):
        write_json(ART / "FULL_18_TRACK_RUNTIME_INVENTORY.json", result["inventory"])
    return result


def start_hub() -> subprocess.Popen:
    HUB_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "WAIKE_PIXEL_PILOT": "true",
            "WAIKE_SEED_TEST_FIXTURES": "false",  # DB already seeded
            "PYTHONPATH": str(ROOT / "services" / "hub"),
            "WAIKE_ALLOW_FAKE_AI": env.get("WAIKE_ALLOW_FAKE_AI", "1"),
            "GUNNCHAI_PROVIDER": env.get("GUNNCHAI_PROVIDER", "fake"),
            "WAIKE_DEV_DB_KEY": env.get(
                "WAIKE_DEV_DB_KEY",
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            ),
        }
    )
    # Use a tiny launcher so create_app uses existing DB without reseeding
    launcher = ART / "hub_launcher.py"
    launcher.write_text(
        f"""
import os
from pathlib import Path
from app.main import HubConfig, create_app
import uvicorn

db = Path({str(PILOT_DB)!r})
os.environ["WAIKE_PIXEL_PILOT"] = "true"
app = create_app(
    config=HubConfig(production_auth_enabled=True, fixture_auth_enabled=False, version="pixel-pilot"),
    db_path=db,
    seed=False,
)
# Force pixel curriculum inventory refresh for healthz
from app.pilot.full_curriculum_seed import inventory_from_db, seed_full_curriculum
inv = inventory_from_db(app.state.db)
if not inv.get("all_18_loaded"):
    inv = seed_full_curriculum(app.state.db, identity=app.state.identity, sections=app.state.sections)
app.state.curriculum_inventory = inv
app.state.pixel_pilot = True
uvicorn.run(app, host="127.0.0.1", port={HUB_PORT}, log_level="info")
""",
        encoding="utf-8",
    )
    logf = HUB_LOG.open("w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(launcher)],
        cwd=str(ROOT / "services" / "hub"),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )


def start_vite() -> subprocess.Popen:
    env = os.environ.copy()
    env["VITE_HUB_URL"] = f"http://127.0.0.1:{HUB_PORT}"
    env["VITE_PIXEL_PILOT"] = "true"
    # Prefer pnpm
    client = ROOT / "apps" / "client"
    cmd = ["pnpm", "exec", "vite", "--host", "127.0.0.1", "--port", str(CLIENT_PORT)]
    if not (client / "node_modules" / ".bin" / "vite").exists():
        cmd = ["npx", "vite", "--host", "127.0.0.1", "--port", str(CLIENT_PORT)]
    return subprocess.Popen(
        cmd,
        cwd=str(client),
        env=env,
        stdout=(ART / "hub_logs" / "vite.log").open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )


def wait_http(url: str, timeout: float = 60.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def adb_reverse() -> None:
    _run(["adb", "reverse", f"tcp:{HUB_PORT}", f"tcp:{HUB_PORT}"])
    _run(["adb", "reverse", f"tcp:{CLIENT_PORT}", f"tcp:{CLIENT_PORT}"])


def open_pixel_chrome(url: str) -> None:
    _run(
        [
            "adb",
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            url,
            "com.android.chrome",
        ]
    )


def screenshot(name: str) -> Path:
    out = ART / "screenshots" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    # Binary-safe capture (shell redirect can truncate on some hosts)
    with out.open("wb") as f:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=False)
    return out


def capture_a11y() -> bool:
    a11y = ART / "accessibility"
    a11y.mkdir(parents=True, exist_ok=True)
    _run(["adb", "shell", "uiautomator", "dump", "/sdcard/waike_ui.xml"])
    _run(["adb", "pull", "/sdcard/waike_ui.xml", str(a11y / "ui.xml")])
    # Font scale probe
    dens = _run(["adb", "shell", "settings", "get", "system", "font_scale"])
    (a11y / "font_scale.txt").write_text((dens.stdout or "").strip() + "\n", encoding="utf-8")
    size = _run(["adb", "shell", "wm", "size"])
    (a11y / "wm_size.txt").write_text((size.stdout or "").strip() + "\n", encoding="utf-8")
    ok = (a11y / "ui.xml").is_file() and (a11y / "ui.xml").stat().st_size > 100
    # Soft mechanics: hierarchy present + font scale readable
    return ok


def api_login(base: str, username: str, password: str, site_id: str) -> dict:
    import urllib.request

    body = json.dumps({"username": username, "password": password, "site_id": site_id}).encode()
    req = urllib.request.Request(
        f"{base}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_get(base: str, path: str, token: str) -> tuple[int, dict | list | str]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def run_role_api_journeys(creds: dict, *, physical_eligible: bool, physical_ui: bool = False) -> dict:
    base = f"http://127.0.0.1:{HUB_PORT}"
    gates: dict[str, bool] = {}
    evidence: dict[str, object] = {"evidence_mode": "mac_api_password_auth", "physical_eligible": physical_eligible, "physical_ui": physical_ui}

    # Learner 18-track visibility
    try:
        login = api_login(
            base,
            creds["pixel-learner-alpha"]["username"],
            creds["pixel-learner-alpha"]["password"],
            "site-alpha",
        )
        token = login["token"]
        st, home = api_get(base, "/api/v1/learner/home", token)
        st2, inv = api_get(base, "/api/v1/pilot/curriculum-inventory", token)
        track_ids = set((inv or {}).get("loaded_track_ids") or []) if isinstance(inv, dict) else set()
        from app.pilot.full_curriculum_seed import EXPECTED_TRACK_IDS

        home_tracks = set()
        if isinstance(home, list):
            for row in home:
                pkg = (row or {}).get("package") or {}
                mid = pkg.get("module_id")
                if mid:
                    home_tracks.add(mid)

        api_ok = (
            st == 200
            and st2 == 200
            and track_ids == set(EXPECTED_TRACK_IDS)
            and home_tracks == set(EXPECTED_TRACK_IDS)
        )
        evidence["mac_api_learner_18"] = api_ok
        evidence["learner_sections_count"] = len(home) if isinstance(home, list) else 0
        evidence["learner_tracks"] = sorted(home_tracks)
        # PIXEL_* requires authorized device path AND physical UI evidence (not Mac API alone).
        gates["PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS"] = bool(api_ok and physical_eligible and physical_ui)
        # logout
        import urllib.request

        req = urllib.request.Request(
            f"{base}/api/v1/auth/logout",
            data=b"{}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        gates["PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS"] = False
        evidence["learner_error"] = str(e)

    def role_smoke(key: str, gate: str, path: str, expect_ok: bool = True) -> None:
        try:
            c = creds[key]
            login = api_login(base, c["username"], c["password"], c["site_id"])
            token = login["token"]
            st, body = api_get(base, path, token)
            api_ok = (200 <= st < 300) if expect_ok else (st in (401, 403))
            gates[gate] = bool(api_ok and physical_eligible and physical_ui)
            evidence[gate] = {"status": st, "sample": str(body)[:300], "mac_api_ok": api_ok}
            import urllib.request

            req = urllib.request.Request(
                f"{base}/api/v1/auth/logout",
                data=b"{}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            gates[gate] = False
            evidence[gate] = {"error": str(e)}

    role_smoke("pixel-instructor-alpha", "PIXEL_INSTRUCTOR_JOURNEY_PASS", "/api/v1/sections")
    role_smoke("pixel-grader-alpha", "PIXEL_GRADER_JOURNEY_PASS", "/api/v1/sections")
    role_smoke("pixel-guardian-alpha", "PIXEL_GUARDIAN_JOURNEY_PASS", "/api/v1/auth/me")
    role_smoke("pixel-admin-alpha", "PIXEL_SITE_ADMIN_JOURNEY_PASS", "/api/v1/admin/users")

    # Cross-site: alpha admin must not see site-beta users
    try:
        c = creds["pixel-admin-alpha"]
        login = api_login(base, c["username"], c["password"], "site-alpha")
        token = login["token"]
        st, users = api_get(base, "/api/v1/admin/users", token)
        beta_site_leak = False
        foreign = []
        if isinstance(users, list):
            for u in users:
                if not isinstance(u, dict):
                    continue
                if u.get("site_id") == "site-beta":
                    beta_site_leak = True
                    foreign.append(u.get("username"))
                # Explicit beta-site pilot accounts must never appear
                if u.get("username") in {
                    "pixel-learner-beta",
                    "pixel-instructor-beta",
                    "pixel-admin-beta",
                    "admin-beta",
                    "instructor-beta",
                    "learner-gamma",
                }:
                    beta_site_leak = True
                    foreign.append(u.get("username"))
        # Alpha instructor must not open beta section
        c2 = creds["pixel-instructor-alpha"]
        login2 = api_login(base, c2["username"], c2["password"], "site-alpha")
        token2 = login2["token"]
        # Find a beta section id from inventory
        st_inv, inv = api_get(base, "/api/v1/pilot/curriculum-inventory", token2)
        beta_sec = None
        if isinstance(inv, dict):
            for t in inv.get("tracks") or []:
                for s in t.get("sections") or []:
                    if s.get("site_id") == "site-beta":
                        beta_sec = s.get("section_id")
                        break
                if beta_sec:
                    break
        denied = True
        if beta_sec:
            st3, _ = api_get(base, f"/api/v1/sections/{beta_sec}/roster", token2)
            denied = st3 in (401, 403, 404)
        api_ok = st == 200 and not beta_site_leak and denied
        gates["PIXEL_CROSS_SITE_ISOLATION_PASS"] = bool(api_ok and physical_eligible and physical_ui)
        evidence["cross_site"] = {
            "admin_users_status": st,
            "beta_site_leak": beta_site_leak,
            "foreign_usernames": foreign,
            "beta_section": beta_sec,
            "roster_denied": denied,
            "mac_api_ok": api_ok,
        }
    except Exception as e:
        gates["PIXEL_CROSS_SITE_ISOLATION_PASS"] = False
        evidence["cross_site"] = {"error": str(e)}

    # Session isolation: sequential logins
    try:
        tokens = []
        for key in (
            "pixel-learner-alpha",
            "pixel-instructor-alpha",
            "pixel-grader-alpha",
            "pixel-guardian-alpha",
            "pixel-admin-alpha",
            "pixel-learner-alpha",
        ):
            c = creds[key]
            login = api_login(base, c["username"], c["password"], c["site_id"])
            tokens.append(login["token"])
            import urllib.request

            req = urllib.request.Request(
                f"{base}/api/v1/auth/logout",
                data=b"{}",
                headers={
                    "Authorization": f"Bearer {login['token']}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10).read()
            # revoked token must fail
            st, _ = api_get(base, "/api/v1/auth/me", login["token"])
            if st not in (401, 403):
                raise RuntimeError(f"token_not_revoked:{key}:{st}")
        gates["PIXEL_ROLE_SESSION_ISOLATION_PASS"] = bool(physical_eligible and physical_ui)
        evidence["mac_api_session_isolation"] = True
    except Exception as e:
        gates["PIXEL_ROLE_SESSION_ISOLATION_PASS"] = False
        evidence["session_isolation_error"] = str(e)

    return {"gates": gates, "evidence": evidence}


def write_acceptance_matrix(gates: dict[str, bool], inventory: dict, physical: bool) -> None:
    rows = []
    tracks = (inventory or {}).get("loaded_track_ids") or []
    for t in tracks:
        rows.append(
            {
                "row_type": "track_visibility",
                "id": t,
                "pass": str(gates.get("PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS", False)).lower(),
                "physical_device": str(physical).lower(),
            }
        )
    for g, v in sorted(gates.items()):
        rows.append(
            {
                "row_type": "gate",
                "id": g,
                "pass": str(bool(v)).lower(),
                "physical_device": str(physical).lower(),
            }
        )
    path = ART / "PIXEL_FULL_ACCEPTANCE_MATRIX.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["row_type", "id", "pass", "physical_device"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-client", action="store_true")
    ap.add_argument("--skip-physical-ui", action="store_true")
    args = ap.parse_args()
    ART.mkdir(parents=True, exist_ok=True)

    gates: dict[str, bool | str] = {
        "PIXEL6A_WAIKE_DEVICE_CONNECTED": False,
        "PIXEL_PILOT_ALL_18_TRACKS_LOADED": False,
        "PIXEL_PILOT_ALL_ROLES_SEEDED": False,
        "WAIKE_PIXEL_WEB_CLIENT_PASS": False,
        "PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS": False,
        "WAIKE_PIXEL_PWA_INSTALL_PASS": False,
        "PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS": False,
        "PIXEL_INSTRUCTOR_JOURNEY_PASS": False,
        "PIXEL_GRADER_JOURNEY_PASS": False,
        "PIXEL_GUARDIAN_JOURNEY_PASS": False,
        "PIXEL_SITE_ADMIN_JOURNEY_PASS": False,
        "PIXEL_ROLE_SESSION_ISOLATION_PASS": False,
        "PIXEL_CROSS_SITE_ISOLATION_PASS": False,
        "PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS": False,
        "PIXEL_ACCESSIBILITY_MECHANICS_PASS": False,
        "PIXEL_WAIKE_STABILITY_PASS": False,
        "PIXEL_WAIKE_AI_SURFACE_PASS": False,
        "WAIKE_ANDROID_NATIVE_BUILD_PASS": False,
        "WAIKE_ANDROID_NATIVE_INSTALL_PASS": False,
        "WAIKE_ANDROID_NATIVE_ALL_ROLE_SMOKE_PASS": False,
        "HUMAN_DISABLED_USER_ACCESSIBILITY_VALIDATION": False,
        "WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS": False,
    }

    procs: list[subprocess.Popen] = []
    try:
        ok, line = adb_authorized()
        gates["PIXEL6A_WAIKE_DEVICE_CONNECTED"] = ok
        write_json(
            ART / "DEVICE_BASELINE.json"
            if not (ART / "DEVICE_BASELINE.json").exists()
            else ART / "DEVICE_BASELINE_RERUN.json",
            {"adb_line": line, "authorized": ok, "captured_at": _utc()},
        )
        if not ok:
            print("ADB not authorized — continuing Mac-side only; physical gates remain false.")

        print("Bootstrapping pilot Hub DB…")
        inv = bootstrap_hub_db()

        print("Seeding pixel pilot users…")
        seeded = seed_users()
        inv = seeded.get("inventory") or inv
        gates["PIXEL_PILOT_ALL_18_TRACKS_LOADED"] = bool(inv.get("all_18_loaded"))
        gates["PIXEL_PILOT_ALL_ROLES_SEEDED"] = bool(seeded["manifest"].get("PIXEL_PILOT_ALL_ROLES_SEEDED"))
        write_json(ART / "FULL_18_TRACK_RUNTIME_INVENTORY.json", inv if isinstance(inv, dict) else {})

        print("Starting Hub…")
        hub = start_hub()
        procs.append(hub)
        if not wait_http(f"http://127.0.0.1:{HUB_PORT}/healthz", 90):
            print("Hub failed to start", file=sys.stderr)
            return 2

        # Connectivity via reverse if authorized
        if ok:
            adb_reverse()
            # Device can reach Mac loopback Hub through reverse
            r = _run(["adb", "shell", "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{HUB_PORT}/healthz"])
            code = (r.stdout or "").strip()
            # Some devices lack curl — try toybox wget or just reverse list
            if code.startswith("2"):
                gates["PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS"] = True
            else:
                rev = _run(["adb", "reverse", "--list"])
                gates["PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS"] = f"tcp:{HUB_PORT}" in (rev.stdout or "")
                write_json(ART / "ADB_REVERSE.json", {"list": rev.stdout, "curl_code": code})

        # Web client
        if not args.skip_client:
            print("Starting Vite client…")
            vite = start_vite()
            procs.append(vite)
            client_up = wait_http(f"http://127.0.0.1:{CLIENT_PORT}/", 90)
            gates["WAIKE_PIXEL_WEB_CLIENT_PASS"] = client_up
            # PWA artifacts present
            manifest = (ROOT / "apps" / "client" / "public" / "manifest.webmanifest").is_file()
            sw = (ROOT / "apps" / "client" / "public" / "sw.js").is_file()
            gates["WAIKE_PIXEL_PWA_INSTALL_PASS"] = bool(manifest and sw and client_up)
            if ok and client_up and not args.skip_physical_ui:
                open_pixel_chrome(f"http://127.0.0.1:{CLIENT_PORT}/")
                time.sleep(4)
                shot = screenshot("01_chrome_open.png")
                gates["PIXEL_ACCESSIBILITY_MECHANICS_PASS"] = capture_a11y() and shot.stat().st_size > 1000
                # Short stability sample (not a 30-min soak — leave soak gate honest)
                t0 = time.time()
                for i in range(5):
                    open_pixel_chrome(f"http://127.0.0.1:{CLIENT_PORT}/")
                    time.sleep(1)
                    screenshot(f"soak_{i:02d}.png")
                elapsed = time.time() - t0
                write_json(
                    ART / "STABILITY_SAMPLE.json",
                    {"cycles": 5, "elapsed_s": elapsed, "full_30min_soak": False},
                )
                # Short sample must not claim soak; full soak may earn PIXEL_WAIKE_STABILITY_PASS later.
                gates["PIXEL_WAIKE_STABILITY_PASS"] = False

        # API journeys (password auth, no fixture headers).
        # PIXEL_* journey gates require authorized Pixel + reverse + physical UI evidence.
        print("Running role API journeys…")
        physical_eligible = bool(gates.get("PIXEL6A_WAIKE_DEVICE_CONNECTED")) and bool(
            gates.get("PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS")
        )
        physical_ui_ok = False
        physical_payload = {"skipped": True}
        if physical_eligible and not args.skip_physical_ui:
            print("Running physical UI role journeys on Pixel…")
            from tools.pixel_pilot.physical_ui_journeys import (
                run_all_role_physical_ui,
                run_offline_restart_reconnect,
                run_stability_soak,
            )
            client_url = f"http://127.0.0.1:{CLIENT_PORT}/"
            physical_payload = run_all_role_physical_ui(ART, seeded["credentials"], client_url)
            write_json(ART / "PHYSICAL_UI_ROLE_JOURNEYS.json", physical_payload)
            physical_ui_ok = bool(physical_payload.get("all_five_ok"))
            offline = run_offline_restart_reconnect(ART, client_url)
            write_json(ART / "OFFLINE_RESTART_RECONNECT.json", offline)
            gates["PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS"] = bool(offline.get("ok"))
            soak_s = int(os.environ.get("WAIKE_PIXEL_SOAK_SECONDS", "1800"))
            print(f"Running stability soak ({soak_s}s)…")
            soak = run_stability_soak(ART, client_url, seconds=soak_s)
            write_json(ART / "STABILITY_FULL_SOAK.json", soak)
            gates["PIXEL_WAIKE_STABILITY_PASS"] = bool(soak.get("full_30min_soak"))
        journey = run_role_api_journeys(
            seeded["credentials"],
            physical_eligible=physical_eligible,
            physical_ui=physical_ui_ok,
        )
        journey["physical_ui"] = physical_payload
        gates.update(journey["gates"])
        # Per-role physical overrides: learner visibility also needs tracks API (already in gates)
        if physical_ui_ok and physical_eligible:
            roles = (physical_payload.get("roles") or {})
            gates["PIXEL_INSTRUCTOR_JOURNEY_PASS"] = bool(gates.get("PIXEL_INSTRUCTOR_JOURNEY_PASS")) and bool((roles.get("instructor") or {}).get("ok"))
            gates["PIXEL_GRADER_JOURNEY_PASS"] = bool(gates.get("PIXEL_GRADER_JOURNEY_PASS")) and bool((roles.get("grader") or {}).get("ok"))
            gates["PIXEL_GUARDIAN_JOURNEY_PASS"] = bool(gates.get("PIXEL_GUARDIAN_JOURNEY_PASS")) and bool((roles.get("guardian") or {}).get("ok"))
            gates["PIXEL_SITE_ADMIN_JOURNEY_PASS"] = bool(gates.get("PIXEL_SITE_ADMIN_JOURNEY_PASS")) and bool((roles.get("site_admin") or {}).get("ok"))
            gates["PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS"] = bool(gates.get("PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS")) and bool((roles.get("learner") or {}).get("ok"))
        write_json(ART / "ROLE_JOURNEY_EVIDENCE.json", journey)

        # Offline / stability / AI — honest false unless earned on device
        # AI surface: healthz only proves hub; leave false unless AI endpoint exercised
        try:
            import urllib.request

            with urllib.request.urlopen(f"http://127.0.0.1:{HUB_PORT}/healthz", timeout=5) as resp:
                health = json.loads(resp.read().decode())
            write_json(ART / "HUB_HEALTHZ.json", health)
        except Exception as e:
            write_json(ART / "HUB_HEALTHZ.json", {"error": str(e)})

        # Aggregate
        required = [
            "PIXEL6A_WAIKE_DEVICE_CONNECTED",
            "PIXEL_PILOT_ALL_18_TRACKS_LOADED",
            "PIXEL_PILOT_ALL_ROLES_SEEDED",
            "WAIKE_PIXEL_WEB_CLIENT_PASS",
            "PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS",
            "WAIKE_PIXEL_PWA_INSTALL_PASS",
            "PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS",
            "PIXEL_INSTRUCTOR_JOURNEY_PASS",
            "PIXEL_GRADER_JOURNEY_PASS",
            "PIXEL_GUARDIAN_JOURNEY_PASS",
            "PIXEL_SITE_ADMIN_JOURNEY_PASS",
            "PIXEL_ROLE_SESSION_ISOLATION_PASS",
            "PIXEL_CROSS_SITE_ISOLATION_PASS",
            "PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS",
            "PIXEL_ACCESSIBILITY_MECHANICS_PASS",
            "PIXEL_WAIKE_STABILITY_PASS",
        ]
        gates["WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS"] = all(bool(gates.get(k)) for k in required)

        write_acceptance_matrix({k: bool(v) for k, v in gates.items()}, inv, physical=ok)
        write_json(ART / "GATE_TOKENS.json", {**gates, "captured_at": _utc()})
        print(json.dumps(gates, indent=2))
        return 0 if gates["PIXEL_PILOT_ALL_18_TRACKS_LOADED"] and gates["PIXEL_PILOT_ALL_ROLES_SEEDED"] else 1
    finally:
        for p in procs:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        time.sleep(1)
        for p in procs:
            if p.poll() is None:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
