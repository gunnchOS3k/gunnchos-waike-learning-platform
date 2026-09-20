#!/usr/bin/env python3
"""Minimal Chrome DevTools Protocol client for Pixel Chrome via adb forward."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import websocket


class CdpSession:
    def __init__(self, ws_url: str, *, timeout: float = 20.0) -> None:
        # Android Chrome rejects WS with an Origin header via adb forward; omit it.
        self._ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._id = 0
        self._timeout = timeout

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        msg_id = self._id
        self._ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            raw = self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP {method}: {data['error']}")
                return data.get("result")
        raise TimeoutError(f"CDP timeout waiting for {method}")

    def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return (result.get("result") or {}).get("value")


def list_targets(host: str = "127.0.0.1", port: int = 9222) -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=5) as resp:
        return json.loads(resp.read().decode())


def find_page(url_substr: str, *, host: str = "127.0.0.1", port: int = 9222) -> dict[str, Any] | None:
    for t in list_targets(host, port):
        if t.get("type") != "page":
            continue
        if url_substr in (t.get("url") or ""):
            return t
    return None


def open_or_reuse(url: str, *, host: str = "127.0.0.1", port: int = 9222) -> CdpSession:
    page = find_page(url.split("?")[0].rstrip("/"), host=host, port=port)
    if page is None:
        # Prefer any blank page, else first page
        targets = [t for t in list_targets(host, port) if t.get("type") == "page"]
        page = next((t for t in targets if (t.get("url") or "").startswith("about:")), None)
        if page is None and targets:
            page = targets[0]
    if page is None or not page.get("webSocketDebuggerUrl"):
        raise RuntimeError("No Chrome page target available for CDP")
    sess = CdpSession(page["webSocketDebuggerUrl"])
    sess.call("Page.enable")
    sess.call("Runtime.enable")
    sess.call("DOM.enable")
    cur = sess.evaluate("location.href")
    if not str(cur).startswith(url.rstrip("/")):
        sess.call("Page.navigate", {"url": url})
        time.sleep(2.5)
    return sess
