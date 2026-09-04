"""WAIKE Learning Hub — modular monolith (PR3 identity + assessment + gradebook)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.api.routes import router as api_router
from app.db import connect, migrate
from app.modules.assessment_lifecycle import AssessmentService
from app.modules.gradebook_service import GradebookService
from app.modules.identity import IdentityService
from app.modules.sections import SectionService

APP_VERSION = "0.3.0-pr3"


class DatabaseConfig(BaseModel):
    enabled: bool = True
    url: str | None = Field(default=None, description="sqlite path or postgresql URL")
    note: str = (
        "PR3 uses SQLite hub persistence with forward migrations. "
        "Production auth uses Argon2id sessions; fixture headers only when fixture_auth_enabled=true."
    )


class HubConfig(BaseModel):
    app_name: str = "waike-learning-hub"
    version: str = APP_VERSION
    environment: str = "development"
    # PR3 defaults: real auth on; fixture headers off unless tests opt in.
    fixture_auth_enabled: bool = False
    production_auth_enabled: bool = True
    learner_data_enabled: bool = True
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def _default_db_path() -> Path:
    override = os.environ.get("WAIKE_HUB_DB")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "hub.sqlite3"


def _platform_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_waike_root() -> Path | None:
    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    root = _platform_root()
    nested = root / "waike-research-ops"
    if nested.is_dir():
        return nested
    sibling = root.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    pin_hint = root / "curriculum" / "registry" / "PIN.json"
    if pin_hint.is_file():
        import json

        data = json.loads(pin_hint.read_text())
        hint = data.get("absolute_path_hint") or data.get("source_path")
        if hint and Path(hint).is_dir():
            return Path(hint)
    return None


def _source_commit(waike_root: Path | None) -> str:
    pin = _platform_root() / "curriculum" / "registry" / "PIN.json"
    if pin.is_file():
        import json

        return str(json.loads(pin.read_text()).get("pinned_commit") or "")
    return ""


def create_app(config: HubConfig | None = None, db_path: Path | None = None, seed: bool = True) -> FastAPI:
    if config is None:
        # Allow process env to opt into fixture auth for live HTTP seam / local PR2 tools.
        fixture = os.environ.get("WAIKE_FIXTURE_AUTH", "").lower() in {"1", "true", "yes"}
        config = HubConfig(
            fixture_auth_enabled=fixture,
            production_auth_enabled=not fixture,
        )
    cfg = config
    app = FastAPI(
        title="WAIKE Learning Hub",
        version=cfg.version,
        description=(
            "PR3 multi-user LMS alpha. production_auth_enabled=true by default; "
            "fixture X-Waike-Actor-* headers only when fixture_auth_enabled=true."
        ),
    )
    app.state.config = cfg

    path = db_path or _default_db_path()
    conn = connect(path)
    migrate(conn)
    waike = _resolve_waike_root()
    src = _source_commit(waike)

    identity = IdentityService(conn)
    sections = SectionService(conn)
    gradebook = GradebookService(conn, sections)
    assessment = AssessmentService(
        conn,
        waike_root=waike,
        source_commit=src,
        sections=sections,
        gradebook=gradebook,
    )

    if seed:
        # Always keep PR2 actors table for assessment FK-ish references.
        assessment.seed_synthetic_actors()
        identity.seed_sites_and_users()
        sections.seed_digital_confidence_section(source_commit=src)
        if waike is not None:
            assign = assessment.seed_digital_confidence_assignment()
            gradebook.seed_for_section("sec_alpha_dc_w01", assign.get("assignment_id"))
            gradebook.seed_for_section("sec_beta_dc_w01", assign.get("assignment_id"))

    app.state.db = conn
    app.state.db_path = str(path)
    app.state.assessment = assessment
    app.state.identity = identity
    app.state.sections = sections
    app.state.gradebook = gradebook
    app.state.waike_root = str(waike) if waike else None

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict:
        return {
            "version": cfg.version,
            "fixture_auth_enabled": cfg.fixture_auth_enabled,
            "production_auth_enabled": cfg.production_auth_enabled,
            "learner_data_enabled": cfg.learner_data_enabled,
            "assessment_lifecycle": True,
            "identity": True,
            "gradebook": True,
        }

    @app.get("/config")
    def get_config() -> HubConfig:
        return cfg

    app.include_router(api_router)
    return app


app = create_app()
