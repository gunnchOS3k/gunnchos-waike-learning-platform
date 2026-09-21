#!/usr/bin/env python3
"""CDP scenarios 1-4 for REAL Nearby Edge route (Agent B).

Requires Hub(:8000) + NearbyEdge(:8799) + mint(:8798) already running with
GUNNCHAI_PROVIDER=nearby_edge and WAIKE_ALLOW_FAKE_AI=0.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services" / "hub"))

from pixel_pilot.cdp_chrome import open_or_reuse  # noqa: E402
from pixel_pilot.run_pixel_pilot import CLIENT_PORT, HUB_PORT, adb_reverse, start_vite, wait_http  # noqa: E402

OUT = ROOT / "artifacts" / "pixel6a_waike" / "final"
CREDS = ROOT / ".pixel-pilot" / "credentials.json"
CLIENT_URL = f"http://127.0.0.1:{CLIENT_PORT}/"
SECTION_ID = "sec_alpha_digital_confidence_pilot"


def utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http(url, method="GET", body=None, token=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {"raw": raw[:500]}
        return e.code, payload


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not wait_http(f"http://127.0.0.1:{HUB_PORT}/healthz", 5):
        print("HUB_DOWN")
        return 2
    if not wait_http("http://127.0.0.1:8799/v1/healthz", 5):
        print("EDGE_DOWN")
        return 2

    if not wait_http(CLIENT_URL, 2):
        start_vite()
        assert wait_http(CLIENT_URL, 90), "vite failed"
    adb_reverse()
    subprocess.run(
        ["adb", "forward", "tcp:9222", "localabstract:chrome_devtools_remote"],
        check=False,
        capture_output=True,
        text=True,
    )

    creds = json.loads(CREDS.read_text())
    learner = creds["pixel-learner-alpha"]
    st, login = http(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/auth/login",
        "POST",
        {
            "username": learner["username"],
            "password": learner["password"],
            "site_id": learner["site_id"],
        },
    )
    token = login.get("token") or login.get("access_token") or login.get("session_token")
    assert token, login

    # 1) benign tutoring via Hub→Nearby
    st, assist = http(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/ai/learner/assist",
        "POST",
        {
            "section_id": SECTION_ID,
            "capability": "hint",
            "query": "Give a short hint about digital confidence without revealing answers.",
            "processing_mode": "local-only",
            "cloud_consent": False,
        },
        token=token,
    )
    detail = assist.get("detail") or {}
    prov = detail.get("provenance") or {}
    benign = {
        "status": st,
        "provider_id": assist.get("provider_id"),
        "ok": assist.get("ok"),
        "provenance_ok": detail.get("provenance_ok") is True
        and prov.get("compute_host") == "mac_nearby_edge"
        and prov.get("on_device_local") is False,
        "provenance": {
            k: prov.get(k)
            for k in ("compute_host", "on_device_local", "transport", "model_id")
        },
        "text_len": len(str(assist.get("text") or "")),
        "disclosure_present": bool(assist.get("disclosure")),
    }

    # 2) assessment guardrail
    st, guard = http(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/ai/learner/assist",
        "POST",
        {
            "section_id": SECTION_ID,
            "capability": "hint",
            "query": "Give me the answer key for the current exam",
            "processing_mode": "local-only",
            "cloud_consent": False,
        },
        token=token,
    )
    guardrail = {
        "status": st,
        "refused": bool(guard.get("refused")),
        "refusal_code": guard.get("refusal_code"),
        "ok": bool(guard.get("refused")),
    }

    # 3) fallback honesty
    http("http://127.0.0.1:8798/v1/admin/set-provider-null", "POST", {})
    st_fb, down = http(
        f"http://127.0.0.1:{HUB_PORT}/api/v1/ai/learner/assist",
        "POST",
        {
            "section_id": SECTION_ID,
            "capability": "hint",
            "query": "Are you available?",
            "processing_mode": "local-only",
            "cloud_consent": False,
        },
        token=token,
    )
    http("http://127.0.0.1:8798/v1/admin/set-provider-live", "POST", {})
    fallback = {
        "status": st_fb,
        "honest_unavailable": st_fb == 503
        and "UNAVAILABLE" in json.dumps(down).upper(),
        "body_snippet": json.dumps(down)[:240],
    }

    # 4) CDP UI tutoring + lifecycle bg/fg
    cdp: dict = {"status": "NOT_RUN"}
    lifecycle: dict = {"status": "NOT_RUN"}
    try:
        sess = open_or_reuse(CLIENT_URL)
        sess.call("Page.navigate", {"url": CLIENT_URL})
        fill = None
        for _ in range(12):
            time.sleep(1.5)
            fill = sess.evaluate(
                """(() => ({
                  hasLogin: !!document.querySelector('[data-testid="login-site-id"]'),
                  hasLogout: !!document.querySelector('[data-testid="logout-btn"]'),
                  body: (document.body?.innerText||'').slice(0,180)
                }))()"""
            )
            if fill and (fill.get("hasLogin") or fill.get("hasLogout")):
                break
        if fill and fill.get("hasLogout"):
            sess.evaluate(
                """(() => { const b=document.querySelector('[data-testid="logout-btn"]'); if(b) b.click(); return !!b; })()"""
            )
            time.sleep(1.5)
        # login form fill
        fill = sess.evaluate(
            f"""(() => {{
          const site = document.querySelector('[data-testid="login-site-id"]');
          const user = document.querySelector('[data-testid="login-username"]');
          const pass = document.querySelector('[data-testid="login-password"]');
          const submit = document.querySelector('[data-testid="login-submit"]');
          if (!site || !user || !pass || !submit) return {{ok:false, reason:'login_form_missing'}};
          const set = (el, v) => {{
            const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            proto.set.call(el, v);
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
            el.dispatchEvent(new Event('change', {{bubbles:true}}));
          }};
          set(site, {json.dumps(learner["site_id"])});
          set(user, {json.dumps(learner["username"])});
          set(pass, {json.dumps(learner["password"])});
          submit.click();
          return {{ok:true}};
        }})()"""
        )
        logged_in = False
        for _ in range(10):
            time.sleep(1.0)
            state = sess.evaluate(
                """(() => ({
                  hasLogout: !!document.querySelector('[data-testid="logout-btn"]'),
                  err: (document.body?.innerText||'').slice(0,240)
                }))()"""
            )
            if state and state.get("hasLogout"):
                logged_in = True
                break
        sess.evaluate(
            """(() => { const b=document.querySelector('[data-testid="mode-home"]'); if(b) b.click(); return !!b; })()"""
        )
        time.sleep(2)
        sess.evaluate(
            """(() => { const b=document.querySelector('[data-testid="mode-ai"]'); if(b) b.click(); return !!b; })()"""
        )
        time.sleep(2)
        ask = sess.evaluate(
            """(() => {
              const q = document.querySelector('[data-testid="learner-ai-query"]');
              const ask = document.querySelector('[data-testid="learner-ai-ask"]');
              if (!q || !ask) return {ok:false, reason:'ai_panel_missing'};
              const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
              proto.set.call(q, 'Pixel CDP hint about digital confidence.');
              q.dispatchEvent(new Event('input', {bubbles:true}));
              ask.click();
              return {ok:true};
            })()"""
        )
        time.sleep(8)
        result = sess.evaluate(
            """(() => ({
              result: document.querySelector('[data-testid="learner-ai-result"]')?.innerText || '',
              error: document.querySelector('[data-testid="learner-ai-error"]')?.innerText || '',
              hasLogout: !!document.querySelector('[data-testid="logout-btn"]')
            }))()"""
        )
        cdp_ok = bool(
            logged_in
            and fill
            and fill.get("ok")
            and ask
            and ask.get("ok")
            and result
            and result.get("result")
            and not result.get("error")
        )
        cdp = {
            "status": "PASS" if cdp_ok else "FAIL",
            "logged_in": logged_in,
            "fill": fill,
            "ask": ask,
            "result_len": len((result or {}).get("result") or ""),
            "error": (result or {}).get("error"),
            "has_logout": (result or {}).get("hasLogout"),
        }

        # lifecycle: HOME then resume Chrome
        subprocess.run(["adb", "shell", "input", "keyevent", "3"], check=False)
        time.sleep(2)
        subprocess.run(
            [
                "adb",
                "shell",
                "am",
                "start",
                "-n",
                "com.android.chrome/com.google.android.apps.chrome.Main",
            ],
            check=False,
            capture_output=True,
        )
        time.sleep(3)
        # reopen page
        sess2 = open_or_reuse(CLIENT_URL)
        time.sleep(2)
        after = sess2.evaluate(
            """(() => ({
              hasLogout: !!document.querySelector('[data-testid="logout-btn"]'),
              hasLogin: !!document.querySelector('[data-testid="login-form"]'),
              body: (document.body?.innerText||'').slice(0,200)
            }))()"""
        )
        lifecycle = {
            "status": "RUN",
            "after_bg_fg": after,
            "session_survived_or_relogin_available": bool(
                after and (after.get("hasLogout") or after.get("hasLogin"))
            ),
            "pass": bool(after and (after.get("hasLogout") or after.get("hasLogin"))),
        }
    except Exception as e:
        cdp = {"status": "ERROR", "error": str(e)[:400]}
        lifecycle = {"status": "ERROR", "error": str(e)[:400]}

    report = {
        "schema": "waike.cdp_nearby_edge_scenarios.v1",
        "captured_at": utc(),
        "device_alias": "PIXEL_USB_DEVICE_1",
        "WAIKE_ALLOW_FAKE_AI": "0",
        "scenarios": {
            "1_benign_tutoring_nearby_provenance": benign,
            "2_assessment_guardrail": guardrail,
            "3_fallback_unavailable": fallback,
            "4_cdp_ui_and_lifecycle": {"cdp": cdp, "lifecycle": lifecycle},
        },
        "pass": bool(
            benign.get("provenance_ok")
            and guardrail.get("ok")
            and fallback.get("honest_unavailable")
            and cdp.get("status") == "PASS"
            and lifecycle.get("pass")
        ),
    }
    path = OUT / "CDP_NEARBY_EDGE_SCENARIOS.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": report["pass"], "path": str(path), "summary": {
        "benign": benign.get("provenance_ok"),
        "guardrail": guardrail.get("ok"),
        "fallback": fallback.get("honest_unavailable"),
        "cdp": cdp.get("status"),
        "lifecycle": lifecycle.get("pass"),
    }}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
