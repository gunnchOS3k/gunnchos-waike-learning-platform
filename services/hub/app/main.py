"""FastAPI hub scaffold — no live learner data or auth in PR1."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

APP_VERSION = "0.1.0-pr1"


class DatabaseConfig(BaseModel):
    """Placeholder for future PostgreSQL — not connected in PR1."""

    enabled: bool = False
    url: str | None = Field(default=None, description="postgresql+psycopg://... (unused in PR1)")
    note: str = "Live learner data and auth are NOT enabled in PR1."


class HubConfig(BaseModel):
    app_name: str = "waike-learning-hub"
    version: str = APP_VERSION
    environment: str = "development"
    auth_enabled: bool = False
    learner_data_enabled: bool = False
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def create_app(config: HubConfig | None = None) -> FastAPI:
    cfg = config or HubConfig()
    app = FastAPI(
        title="WAIKE Learning Hub",
        version=cfg.version,
        description="PR1 scaffold only. Auth and live learner data are disabled.",
    )
    app.state.config = cfg

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict:
        return {
            "version": cfg.version,
            "auth_enabled": cfg.auth_enabled,
            "learner_data_enabled": cfg.learner_data_enabled,
        }

    @app.get("/config")
    def get_config() -> HubConfig:
        return cfg

    return app


app = create_app()
