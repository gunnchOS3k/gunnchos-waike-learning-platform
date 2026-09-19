"""CORS exact-origin policy for Pixel pilot — never wildcard."""

from __future__ import annotations

import os

import pytest

from app.cors_origins import hub_allow_origins


def test_default_origins_exclude_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAIKE_PIXEL_PILOT", raising=False)
    monkeypatch.delenv("WAIKE_PIXEL_WEB_CLIENT", raising=False)
    monkeypatch.delenv("WAIKE_PIXEL_PILOT_ORIGINS", raising=False)
    origins = hub_allow_origins()
    assert "*" not in origins
    assert "http://ipc.localhost" in origins


def test_pixel_pilot_adds_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    monkeypatch.delenv("WAIKE_PIXEL_PILOT_ORIGINS", raising=False)
    origins = hub_allow_origins()
    assert "http://127.0.0.1:1420" in origins
    assert "*" not in origins


def test_extra_origins_reject_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAIKE_PIXEL_PILOT", "true")
    monkeypatch.setenv("WAIKE_PIXEL_PILOT_ORIGINS", "http://192.168.1.10:1420,*")
    with pytest.raises(ValueError, match="CORS_WILDCARD_FORBIDDEN"):
        hub_allow_origins()
