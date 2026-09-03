"""WAIKE Learning Hub — modular monolith (PR2 assessment lifecycle)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.api.routes import router as api_router
from app.db import connect, migrate
from app.modules.assessment_lifecycle import AssessmentService

APP_VERSION = "0.2.0-pr2"


class DatabaseConfig(BaseModel):
    enabled: bool = True
    url: str | None = Field(default=None, description="sqlite path or postgresql URL")
    note: str = "PR2 uses SQLite hub persistence with migrations. Auth is synthetic fixture headers."


class HubConfig(BaseModel):
    app_name: str = "waike-learning-hub"
    version: str = APP_VERSION
    environment: str = "development"
    auth_enabled: bool = True
    learner_data_enabled: bool = True
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def _default_db_path() -> Path:
    override = os.environ.get("WAIKE_HUB_DB")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "hub.sqlite3"


def _resolve_waike_root() -> Path | None:
    env = os.environ.get("WAIKE_ROOT")
    if env:
        return Path(env)
    # Prefer sibling checkout in the learning-os workspace
    sibling = Path(__file__).resolve().parents[4] / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    pin_hint = Path(__file__).resolve().parents[3] / "curriculum" / "registry" / "PIN.json"
    if pin_hint.is_file():
        import json

        data = json.loads(pin_hint.read_text())
        hint = data.get("absolute_path_hint") or data.get("source_path")
        if hint and Path(hint).is_dir():
            return Path(hint)
    return None


def _source_commit(waike_root: Path | None) -> str:
    pin = Path(__file__).resolve().parents[3] / "curriculum" / "registry" / "PIN.json"
    if pin.is_file():
        import json

        return str(json.loads(pin.read_text()).get("pinned_commit") or "")
    return ""


def create_app(config: HubConfig | None = None, db_path: Path | None = None, seed: bool = True) -> FastAPI:
    cfg = config or HubConfig()
    app = FastAPI(
        title="WAIKE Learning Hub",
        version=cfg.version,
        description="PR2 assessment lifecycle hub. Synthetic fixture auth via X-Waike-Actor-* headers.",
    )
    app.state.config = cfg

    path = db_path or _default_db_path()
    conn = connect(path)
    migrate(conn)
    waike = _resolve_waike_root()
    svc = AssessmentService(conn, waike_root=waike, source_commit=_source_commit(waike))
    if seed:
        svc.seed_synthetic_actors()
        if waike is not None:
            svc.seed_digital_confidence_assignment()
    app.state.db = conn
    app.state.db_path = str(path)
    app.state.assessment = svc
    app.state.waike_root = str(waike) if waike else None

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict:
        return {
            "version": cfg.version,
            "auth_enabled": cfg.auth_enabled,
            "learner_data_enabled": cfg.learner_data_enabled,
            "assessment_lifecycle": True,
        }

    @app.get("/config")
    def get_config() -> HubConfig:
        return cfg

    app.include_router(api_router)
    return app


app = create_app()
