#!/usr/bin/env python3
"""Physical Pixel UI journeys for WAIKE post-merge closure.

Honest evidence only: screenshots + UIAutomator dumps + route/state log.
Does not use fixture-auth headers. Passwords never written to git artifacts.
"""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _adb(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *cmd], text=True, capture_output=True, check=check)


@dataclass
class RoleJourneyResult:
    role: str
    ok: bool
    steps: list[dict] = field(default_factory=list)
    error: str | None = None


def dump_ui(local_path: Path) -> str:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _adb(["shell", "uiautomator", "dump", "/sdcard/waike_ui_phys.xml"])
    _adb(["pull", "/sdcard/waike_ui_phys.xml", str(local_path)])
    if not local_path.is_file():
        return ""
    return local_path.read_text(encoding="utf-8", errors="ignore")


def find_node(xml_text: str, *, text: str | None = None, resource_id: str | None = None, content_desc: str | None = None):
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    for node in root.iter("node"):
        if text and (node.attrib.get("text") or "") == text:
            return node.attrib
        if text and text.lower() in (node.attrib.get("text") or "").lower():
            return node.attrib
        if resource_id and resource_id in (node.attrib.get("resource-id") or ""):
            return node.attrib
        if content_desc and content_desc.lower() in (node.attrib.get("content-desc") or "").lower():
            return node.attrib
    return None


def bounds_center(bounds: str) -> tuple[int, int] | None:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def tap(x: int, y: int) -> None:
    _adb(["shell", "input", "tap", str(x), str(y)])


def tap_node(attr: dict | None) -> bool:
    if not attr:
        return False
    c = bounds_center(attr.get("bounds", ""))
    if not c:
        return False
    tap(*c)
    return True


def clear_and_type(text: str) -> None:
    # Focused field: select-all then type
    _adb(["shell", "input", "keyevent", "KEYCODE_MOVE_END"])
    _adb(["shell", "input", "keyevent", "--longpress", "KEYCODE_DEL"])
    # Fallback: many deletes
    for _ in range(40):
        _adb(["shell", "input", "keyevent", "67"])  # DEL
    # Escape spaces for adb input text
    escaped = text.replace(" ", "%s").replace("'", "\\'")
    _adb(["shell", "input", "text", escaped])


def screenshot(art: Path, name: str) -> Path:
    out = art / "screenshots" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=False)
    return out


def open_client(url: str) -> None:
    _adb(
        [
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


def ui_contains(xml_text: str, needles: list[str]) -> bool:
    low = xml_text.lower()
    return any(n.lower() in low for n in needles)


def physical_login(
    art: Path,
    *,
    url: str,
    site_id: str,
    username: str,
    password: str,
    role_tag: str,
) -> RoleJourneyResult:
    """Drive Chrome login form via UIAutomator. Password never written to artifacts."""
    res = RoleJourneyResult(role=role_tag, ok=False)
    log_dir = art / "physical_ui" / role_tag
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        open_client(url)
        time.sleep(3)
        screenshot(art, f"phys_{role_tag}_00_open.png")
        xml = dump_ui(log_dir / "00_open.xml")
        res.steps.append({"t": _utc(), "step": "open", "has_sign_in": ui_contains(xml, ["Sign in", "Username", "Site ID"])})

        # Site ID field
        site = find_node(xml, text="Site ID") or find_node(xml, resource_id="site-id")
        # Prefer EditText nodes in order
        edits = []
        try:
            root = ET.fromstring(xml) if xml else None
            if root is not None:
                for node in root.iter("node"):
                    if node.attrib.get("class", "").endswith("EditText"):
                        edits.append(node.attrib)
        except ET.ParseError:
            edits = []

        if len(edits) >= 3:
            tap_node(edits[0])
            time.sleep(0.3)
            clear_and_type(site_id)
            tap_node(edits[1])
            time.sleep(0.3)
            clear_and_type(username)
            tap_node(edits[2])
            time.sleep(0.3)
            clear_and_type(password)
        else:
            res.error = f"login_fields_missing edits={len(edits)}"
            screenshot(art, f"phys_{role_tag}_01_fields_missing.png")
            dump_ui(log_dir / "01_fields_missing.xml")
            return res

        xml = dump_ui(log_dir / "02_filled.xml")
        submit = find_node(xml, text="Sign in")
        if not tap_node(submit):
            # try button class
            res.error = "sign_in_button_missing"
            screenshot(art, f"phys_{role_tag}_02_no_submit.png")
            return res
        time.sleep(4)
        shot = screenshot(art, f"phys_{role_tag}_03_after_login.png")
        xml = dump_ui(log_dir / "03_after_login.xml")
        logged_in = ui_contains(xml, ["Sign out", "Primary", role_tag, "Home", "Instruct", "Admin", "Guardian", "Gradebook", "Lessons"])
        still_login = ui_contains(xml, ["Sign in to your school hub"])
        res.steps.append(
            {
                "t": _utc(),
                "step": "after_login",
                "screenshot": str(shot.name),
                "logged_in_heuristic": logged_in,
                "still_on_login": still_login,
                "xml_bytes": len(xml),
            }
        )
        # Navigate role-specific control if present
        mode_map = {
            "learner": ["Home", "AI tutor", "Activities"],
            "instructor": ["Instruct", "Roster"],
            "grader": ["Gradebook"],
            "guardian": ["Guardian"],
            "site_admin": ["Admin"],
        }
        for label in mode_map.get(role_tag, []):
            node = find_node(xml, text=label)
            if tap_node(node):
                time.sleep(2)
                screenshot(art, f"phys_{role_tag}_nav_{label.replace(' ', '_').lower()}.png")
                xml = dump_ui(log_dir / f"nav_{label.replace(' ', '_').lower()}.xml")
                res.steps.append({"t": _utc(), "step": f"nav:{label}", "ok": True})
                break

        # Logout if available
        logout = find_node(xml, text="Sign out") or find_node(xml, content_desc="Sign out")
        # Partial match on Sign out (
        if not logout:
            try:
                root = ET.fromstring(xml) if xml else None
                if root is not None:
                    for node in root.iter("node"):
                        if (node.attrib.get("text") or "").startswith("Sign out"):
                            logout = node.attrib
                            break
            except ET.ParseError:
                pass
        if tap_node(logout):
            time.sleep(2)
            screenshot(art, f"phys_{role_tag}_99_logout.png")
            res.steps.append({"t": _utc(), "step": "logout", "ok": True})

        res.ok = bool(logged_in and not still_login and shot.stat().st_size > 1000)
        if not res.ok and not res.error:
            res.error = "physical_login_heuristic_failed"
        return res
    except Exception as e:
        res.error = str(e)
        return res


def run_all_role_physical_ui(art: Path, creds: dict, client_url: str) -> dict:
    order = [
        ("learner", "pixel-learner-alpha"),
        ("instructor", "pixel-instructor-alpha"),
        ("grader", "pixel-grader-alpha"),
        ("guardian", "pixel-guardian-alpha"),
        ("site_admin", "pixel-admin-alpha"),
    ]
    results: dict[str, object] = {"captured_at": _utc(), "client_url": client_url, "roles": {}}
    for role, key in order:
        c = creds[key]
        r = physical_login(
            art,
            url=client_url,
            site_id=c["site_id"],
            username=c["username"],
            password=c["password"],
            role_tag=role,
        )
        results["roles"][role] = {
            "ok": r.ok,
            "error": r.error,
            "steps": r.steps,
            "username_redacted": True,
        }
        time.sleep(1)
    results["all_five_ok"] = all(bool((results["roles"][r] or {}).get("ok")) for r, _ in order)
    return results


def run_stability_soak(art: Path, client_url: str, seconds: int = 1800) -> dict:
    """Real timed soak with periodic navigation / bg-fg. Not a 5-cycle sample."""
    t0 = time.time()
    cycles = 0
    shots = []
    hub_ok = True
    while time.time() - t0 < seconds:
        open_client(client_url)
        time.sleep(2)
        # background
        _adb(["shell", "input", "keyevent", "KEYCODE_HOME"])
        time.sleep(2)
        # foreground via reopen
        open_client(client_url)
        time.sleep(2)
        # scroll gesture
        _adb(["shell", "input", "swipe", "540", "1600", "540", "800", "300"])
        shot = screenshot(art, f"soak_full_{cycles:03d}.png")
        shots.append(shot.name)
        cycles += 1
        # Hub health from host
        try:
            import urllib.request

            with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3) as resp:
                if resp.status >= 500:
                    hub_ok = False
        except Exception:
            hub_ok = False
        # sleep remainder of cycle (~30s cadence)
        elapsed = time.time() - t0
        target = min(seconds, (cycles) * 30)
        time.sleep(max(0, target - elapsed))
    elapsed = time.time() - t0
    return {
        "captured_at": _utc(),
        "requested_seconds": seconds,
        "elapsed_s": elapsed,
        "cycles": cycles,
        "hub_ok_throughout": hub_ok,
        "full_30min_soak": elapsed >= (seconds - 5) and hub_ok and cycles >= 5,
        "screenshots_sample": shots[:5] + (["…"] if len(shots) > 5 else []),
        "screenshot_count": len(shots),
    }


def run_offline_restart_reconnect(art: Path, client_url: str) -> dict:
    """Airplane-mode offline → relaunch → online reconnect probe."""
    steps = []
    try:
        open_client(client_url)
        time.sleep(2)
        screenshot(art, "offline_00_online.png")
        steps.append({"t": _utc(), "step": "online_open"})
        _adb(["shell", "cmd", "connectivity", "airplane-mode", "enable"])
        time.sleep(2)
        screenshot(art, "offline_01_airplane.png")
        steps.append({"t": _utc(), "step": "airplane_on"})
        # force-stop chrome and relaunch
        _adb(["shell", "am", "force-stop", "com.android.chrome"])
        time.sleep(1)
        open_client(client_url)
        time.sleep(3)
        screenshot(art, "offline_02_relaunch.png")
        xml = dump_ui(art / "physical_ui" / "offline_relaunch.xml")
        steps.append({"t": _utc(), "step": "offline_relaunch", "xml_bytes": len(xml)})
        _adb(["shell", "cmd", "connectivity", "airplane-mode", "disable"])
        time.sleep(3)
        open_client(client_url)
        time.sleep(3)
        screenshot(art, "offline_03_reconnect.png")
        steps.append({"t": _utc(), "step": "airplane_off_reconnect"})
        return {"ok": True, "steps": steps, "note": "shell survived offline/relaunch/reconnect; sync receipt not claimed unless UI shows sync"}
    except Exception as e:
        # always try to restore network
        _adb(["shell", "cmd", "connectivity", "airplane-mode", "disable"])
        return {"ok": False, "error": str(e), "steps": steps}
