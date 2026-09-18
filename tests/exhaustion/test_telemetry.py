"""Telemetry module unit tests (SYNTHETIC fixtures only)."""

from __future__ import annotations

import sqlite3

import pytest

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError
from app.modules.hardening import Observability
from app.modules.telemetry import TelemetryService


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE observability_events(
          event_id TEXT PRIMARY KEY,
          level TEXT,
          category TEXT,
          message TEXT,
          redacted_detail_json TEXT,
          created_at TEXT
        );
        """
    )
    return conn


def _admin() -> Actor:
    return Actor(
        actor_id="admin-alpha",
        role=Role.SITE_ADMIN,
        site_id="site-alpha",
        roles=(Role.SITE_ADMIN,),
        display_name="Admin",
        username="admin-alpha",
    )


def test_telemetry_emit_and_counters_synthetic():
    conn = _conn()
    obs = Observability(conn)
    tel = TelemetryService(conn, obs)
    admin = _admin()
    seeded = tel.seed_synthetic_smoke(admin)
    assert seeded["label"] == "SYNTHETIC"
    assert len(seeded["event_ids"]) == 3
    counters = tel.counters(admin)
    assert counters["schema"] == "waike.telemetry.counters.v1"
    assert any(k.startswith("telemetry.") for k in counters["counters"])


def test_telemetry_rejects_bad_category_and_learner():
    conn = _conn()
    tel = TelemetryService(conn, Observability(conn))
    with pytest.raises(ServiceError):
        tel.emit(category="not_a_category", message="x")
    learner = Actor(
        actor_id="learner-alpha",
        role=Role.LEARNER,
        site_id="site-alpha",
        roles=(Role.LEARNER,),
        display_name="Learner",
        username="learner-alpha",
    )
    with pytest.raises(ServiceError):
        tel.counters(learner)
