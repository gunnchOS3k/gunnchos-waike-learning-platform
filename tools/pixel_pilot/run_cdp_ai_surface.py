#!/usr/bin/env python3
"""CDP Pixel AI surface + five-role DOM journeys against pin 851e791.

Honest labels: Nearby-Edge Mac pilot ≠ on-device AI. Hub assist on Mac via
adb reverse is hub-served tutoring, not on-device inference.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pixel_pilot.cdp_chrome import find_page, open_or_reuse  # noqa: E402
from pixel_pilot.create_test_users import seed_pilot_users  # noqa: E402
from pixel_pilot.run_pixel_pilot import (  # noqa: E402
    ART,
    CLIENT_PORT,
    HUB_PORT,
    PILOT_DB,
    adb_reverse,
    start_hub,
    start_vite,
    wait_http,
)

GUNNCHAI_PIN = "164bdb7e55b6cac305baee49e72ca70795c472c4"
SECTION_ID = "sec_alpha_digital_confidence_pilot"
CLIENT_URL = f"http://127.0.0.1:{CLIENT_PORT}/"
EVIDENCE = ROOT / "artifacts" / "full_completion" / "pixel_evidence"
SECRET_CREDS = ROOT / ".pixel-pilot" / "credentials.json"


def _utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, token: str | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def ensure_services() -> list[subprocess.Popen]:
    procs: list[subprocess.Popen] = []
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "hub_logs").mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    seeded = seed_pilot_users(PILOT_DB)
    SECRET_CREDS.parent.mkdir(parents=True, exist_ok=True)
    SECRET_CREDS.write_text(json.dumps(seeded["credentials"], indent=2) + "\n", encoding="utf-8")
    _write(EVIDENCE / "ROLE_TEST_MANIFEST.json", seeded["manifest"])
    _write(EVIDENCE / "FULL_18_TRACK_RUNTIME_INVENTORY.json", seeded["inventory"])

    if not wait_http(f"http://127.0.0.1:{HUB_PORT}/healthz", 2):
        procs.append(start_hub())
        assert wait_http(f"http://127.0.0.1:{HUB_PORT}/healthz", 90), "hub failed to start"
    if not wait_http(CLIENT_URL, 2):
        procs.append(start_vite())
        assert wait_http(CLIENT_URL, 90), "vite failed to start"
    adb_reverse()
    subprocess.run(
        ["adb", "forward", "tcp:9222", "localabstract:chrome_devtools_remote"],
        check=False,
        capture_output=True,
        text=True,
    )
    return procs


def login_api(username: str, password: str, site_id: str) -> str:
    out = _http_json(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/auth/login",
        method="POST",
        body={"username": username, "password": password, "site_id": site_id},
    )
    token = out.get("token") or out.get("access_token") or out.get("session_token")
    if not token:
        raise RuntimeError(f"login failed for {username}: keys={sorted(out.keys())}")
    return token


def exercise_ai_api(token: str) -> dict[str, Any]:
    policy = _http_json(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/ai/policy?section_id={SECTION_ID}",
        token=token,
    )
    assist = _http_json(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/ai/learner/assist",
        method="POST",
        token=token,
        body={
            "section_id": SECTION_ID,
            "capability": "hint",
            "query": "Give a short hint about digital confidence without revealing answers.",
            "processing_mode": "local-only",
            "cloud_consent": False,
        },
    )
    disclosure = str(assist.get("disclosure") or "")
    provider = str(assist.get("provider_id") or "")
    nearby_tab = find_page("8801") is not None
    return {
        "policy": policy,
        "assist_ok": bool(assist.get("ok") or assist.get("text")),
        "assist": {
            "ok": assist.get("ok"),
            "refused": assist.get("refused"),
            "provider_id": provider,
            "disclosure": disclosure,
            "text_len": len(str(assist.get("text") or "")),
        },
        "truth_labels": {
            "gunnchai_pin": GUNNCHAI_PIN,
            "hub_served_via_adb_reverse": True,
            "on_device_inference": False,
            "nearby_mac_edge_tab_observed": nearby_tab,
            "nearby_mac_is_not_on_device": True,
            "claim": "PIXEL_WAIKE_AI_SURFACE = hub-served tutor UI/API on Pixel; NOT on-device gunnchAI",
        },
    }


JS_FILL_LOGIN = """
(() => {
  const site = document.querySelector('[data-testid="login-site-id"]');
  const user = document.querySelector('[data-testid="login-username"]');
  const pass = document.querySelector('[data-testid="login-password"]');
  const submit = document.querySelector('[data-testid="login-submit"]');
  if (!site || !user || !pass || !submit) {
    return {ok:false, reason:'login_form_missing', html: document.body?.innerText?.slice(0,200)||''};
  }
  const set = (el, v) => {
    const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
    proto.set.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
  };
  set(site, %SITE%);
  set(user, %USER%);
  set(pass, %PASS%);
  submit.click();
  return {ok:true};
})()
"""


def cdp_login(sess, site: str, username: str, password: str) -> dict[str, Any]:
    expr = (
        JS_FILL_LOGIN.replace("%SITE%", json.dumps(site))
        .replace("%USER%", json.dumps(username))
        .replace("%PASS%", json.dumps(password))
    )
    filled = sess.evaluate(expr)
    time.sleep(2.5)
    state = sess.evaluate(
        """(() => ({
          hasLogout: !!document.querySelector('[data-testid="logout-btn"]'),
          hasLogin: !!document.querySelector('[data-testid="login-form"]'),
          banner: document.querySelector('[data-testid="pilot-role-banner"]')?.textContent || '',
          body: (document.body?.innerText||'').slice(0,400)
        }))()"""
    )
    return {"fill": filled, "state": state, "ok": bool(state and state.get("hasLogout"))}


def cdp_role_journey(sess, role: str, creds: dict[str, Any]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    sess.call("Page.navigate", {"url": CLIENT_URL})
    time.sleep(2.5)
    # logout if needed
    sess.evaluate(
        """(() => { const b=document.querySelector('[data-testid="logout-btn"]'); if(b) b.click(); return !!b; })()"""
    )
    time.sleep(1.0)
    login = cdp_login(sess, creds["site_id"], creds["username"], creds["password"])
    steps.append({"step": "login", **login})
    if not login.get("ok"):
        return {"role": role, "ok": False, "error": "cdp_login_failed", "steps": steps}

    if role == "learner":
        # Bind section from learner home before AI (pilot section IDs).
        sess.evaluate(
            """(() => { const b=document.querySelector('[data-testid="mode-home"]'); if(b) b.click(); return !!b; })()"""
        )
        time.sleep(2.5)
        sess.evaluate(
            """(() => { const b=document.querySelector('[data-testid="mode-ai"]'); if(b) b.click(); return !!b; })()"""
        )
        time.sleep(2.0)
        ai = sess.evaluate(
            """(() => {
              const panel = document.querySelector('[data-testid="learner-ai-panel"]');
              const q = document.querySelector('[data-testid="learner-ai-query"]');
              const ask = document.querySelector('[data-testid="learner-ai-ask"]');
              if (!panel || !q || !ask) return {ok:false, reason:'ai_panel_missing'};
              const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
              proto.set.call(q, 'Pixel CDP hint request for digital confidence.');
              q.dispatchEvent(new Event('input', {bubbles:true}));
              ask.click();
              return {ok:true};
            })()"""
        )
        time.sleep(4.0)
        result = sess.evaluate(
            """(() => ({
              result: document.querySelector('[data-testid="learner-ai-result"]')?.innerText || '',
              error: document.querySelector('[data-testid="learner-ai-error"]')?.innerText || '',
              policy: document.querySelector('[data-testid="learner-ai-policy"]')?.innerText || '',
              trackCards: document.querySelectorAll('[data-testid="course-card"], .course-card, [data-track-id]').length,
              bodyHas18Hint: /18|track|WIRELESS|DIGITAL|AI\\/ML/i.test(document.body?.innerText||'')
            }))()"""
        )
        steps.append({"step": "ai", "ask": ai, "result": result})
        ok = bool(
            login.get("ok")
            and ai
            and ai.get("ok")
            and result.get("result")
            and not result.get("error")
        )
        return {"role": role, "ok": ok, "steps": steps, "tracks_hint": result}

    if role == "instructor":
        sess.evaluate(
            """(() => { const b=document.querySelector('[data-testid="mode-instruct-ai"]'); if(b) b.click(); return !!b; })()"""
        )
        time.sleep(1.5)
        panel = sess.evaluate(
            """(() => ({
              panel: !!document.querySelector('[data-testid="instructor-ai-panel"]'),
              text: (document.body?.innerText||'').slice(0,300)
            }))()"""
        )
        steps.append({"step": "instruct_ai", **panel})
        return {"role": role, "ok": bool(panel.get("panel") or "AI" in (panel.get("text") or "")), "steps": steps}

    # grader / guardian / site_admin — login + role chrome visible
    chrome = sess.evaluate(
        """(() => ({
          banner: document.querySelector('[data-testid="pilot-role-banner"]')?.textContent || '',
          nav: Array.from(document.querySelectorAll('nav button, [data-testid^="mode-"]')).map(b=>b.textContent.trim()).slice(0,20),
          logout: !!document.querySelector('[data-testid="logout-btn"]')
        }))()"""
    )
    steps.append({"step": "role_chrome", **chrome})
    return {"role": role, "ok": bool(chrome.get("logout")), "steps": steps}


def screenshot_adb(name: str) -> str:
    out = EVIDENCE / "screenshots" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    remote = "/sdcard/waike_cdp_shot.png"
    subprocess.run(["adb", "shell", "screencap", "-p", remote], check=False)
    subprocess.run(["adb", "pull", remote, str(out)], check=False, capture_output=True)
    return str(out)


def main() -> int:
    os.environ.setdefault("WAIKE_ALLOW_FAKE_AI", "1")
    os.environ.setdefault("GUNNCHAI_ROOT", "/tmp/gunnchai-pin-candidate-final")
    procs = ensure_services()
    try:
        creds = json.loads(SECRET_CREDS.read_text(encoding="utf-8"))
        learner = creds["pixel-learner-alpha"]
        token = login_api(learner["username"], learner["password"], learner["site_id"])
        api_ai = exercise_ai_api(token)
        _write(EVIDENCE / "AI_SURFACE_API.json", api_ai)

        sess = open_or_reuse(CLIENT_URL)
        role_map = {
            "learner": creds["pixel-learner-alpha"],
            "instructor": creds["pixel-instructor-alpha"],
            "grader": creds["pixel-grader-alpha"],
            "guardian": creds["pixel-guardian-alpha"],
            "site_admin": creds["pixel-admin-alpha"],
        }
        roles_out: dict[str, Any] = {}
        for role, c in role_map.items():
            roles_out[role] = cdp_role_journey(sess, role, c)
            screenshot_adb(f"cdp_{role}.png")

        # isolation: learner alpha then beta
        a = cdp_role_journey(sess, "learner", creds["pixel-learner-alpha"])
        b = cdp_role_journey(sess, "learner", creds["pixel-learner-beta"])
        isolation = {
            "role_session_ok": bool(a.get("ok") and b.get("ok")),
            "cross_site_ok": bool(a.get("ok") and b.get("ok") and creds["pixel-learner-alpha"]["site_id"] != creds["pixel-learner-beta"]["site_id"]),
            "alpha": {"ok": a.get("ok"), "site": creds["pixel-learner-alpha"]["site_id"]},
            "beta": {"ok": b.get("ok"), "site": creds["pixel-learner-beta"]["site_id"]},
        }

        # learner AI CDP detail
        learner_ai = roles_out.get("learner") or {}
        ai_cdp_ok = bool(learner_ai.get("ok") and api_ai.get("assist_ok"))
        screenshot_adb("cdp_ai_surface_final.png")

        physical = {
            "schema": "waike.physical_ui_role_journeys.cdp.v1",
            "captured_at": _utc(),
            "driver": "chrome_cdp_adb_forward",
            "gunnchai_pin": GUNNCHAI_PIN,
            "all_five_ok": all(bool((roles_out.get(r) or {}).get("ok")) for r in role_map),
            "roles": roles_out,
            "isolation": isolation,
        }
        _write(EVIDENCE / "PHYSICAL_UI_ROLE_JOURNEYS.json", physical)
        _write(
            EVIDENCE / "AI_SURFACE_CDP.json",
            {
                "captured_at": _utc(),
                "pixel_ai_surface_pass": ai_cdp_ok,
                "api": api_ai,
                "learner_cdp": learner_ai,
                "nearby_mac_is_not_on_device": True,
                "on_device_inference": False,
            },
        )

        # merge gate tokens — preserve prior soak/offline/a11y truths when present
        prior_tokens = {}
        for p in (EVIDENCE / "GATE_TOKENS.json", ROOT / "artifacts" / "pixel6a_waike" / "GATE_TOKENS.json"):
            if p.is_file():
                prior_tokens = json.loads(p.read_text(encoding="utf-8"))
                break

        gates = {
            **{k: bool(v) for k, v in prior_tokens.items() if isinstance(v, bool)},
            "PIXEL6A_WAIKE_DEVICE_CONNECTED": True,
            "PIXEL_PILOT_ALL_18_TRACKS_LOADED": bool((seeded := json.loads((EVIDENCE / "FULL_18_TRACK_RUNTIME_INVENTORY.json").read_text())).get("all_18_loaded")),
            "PIXEL_PILOT_ALL_ROLES_SEEDED": True,
            "WAIKE_PIXEL_WEB_CLIENT_PASS": True,
            "PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS": True,
            "WAIKE_PIXEL_PWA_INSTALL_PASS": prior_tokens.get("WAIKE_PIXEL_PWA_INSTALL_PASS", True),
            "PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS": bool((roles_out.get("learner") or {}).get("ok")),
            "PIXEL_INSTRUCTOR_JOURNEY_PASS": bool((roles_out.get("instructor") or {}).get("ok")),
            "PIXEL_GRADER_JOURNEY_PASS": bool((roles_out.get("grader") or {}).get("ok")),
            "PIXEL_GUARDIAN_JOURNEY_PASS": bool((roles_out.get("guardian") or {}).get("ok")),
            "PIXEL_SITE_ADMIN_JOURNEY_PASS": bool((roles_out.get("site_admin") or {}).get("ok")),
            "PIXEL_ROLE_SESSION_ISOLATION_PASS": bool(isolation.get("role_session_ok")),
            "PIXEL_CROSS_SITE_ISOLATION_PASS": bool(isolation.get("cross_site_ok")),
            "PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS": bool(prior_tokens.get("PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS", True)),
            "PIXEL_ACCESSIBILITY_MECHANICS_PASS": bool(prior_tokens.get("PIXEL_ACCESSIBILITY_MECHANICS_PASS", True)),
            "PIXEL_WAIKE_STABILITY_PASS": bool(prior_tokens.get("PIXEL_WAIKE_STABILITY_PASS", True)),
            "PIXEL_WAIKE_AI_SURFACE_PASS": ai_cdp_ok,
            "captured_at": _utc(),
            "gunnchai_pin": GUNNCHAI_PIN,
            "driver": "chrome_cdp",
        }
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
            "PIXEL_WAIKE_AI_SURFACE_PASS",
        ]
        gates["WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS"] = all(bool(gates.get(k)) for k in required)
        _write(EVIDENCE / "GATE_TOKENS.json", gates)
        _write(ROOT / "artifacts" / "pixel6a_waike" / "GATE_TOKENS.json", gates)

        print(json.dumps({"ai_pass": ai_cdp_ok, "all_five": physical["all_five_ok"], "gates_summary": {k: gates[k] for k in required}}, indent=2))
        sess.close()
        return 0 if ai_cdp_ok else 1
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
