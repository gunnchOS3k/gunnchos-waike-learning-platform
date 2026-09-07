"""Gate D API routes: guardian oversight + role journey surfaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor, require_guardian, require_site_admin
from app.modules.assessment_lifecycle import ServiceError
from app.modules.guardian import GuardianService

router = APIRouter(prefix="/api/v1")


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


def _guardian(request: Request) -> GuardianService:
    return request.app.state.guardian


class GuardianLinkBody(BaseModel):
    guardian_user_id: str = Field(min_length=1)
    learner_user_id: str = Field(min_length=1)


@router.get("/guardian/learners")
def guardian_list_learners(
    request: Request,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    require_guardian(actor)
    try:
        return _guardian(request).list_linked_learners(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/guardian/learners/{learner_user_id}/overview")
def guardian_learner_overview(
    learner_user_id: str,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_guardian(actor)
    try:
        return _guardian(request).learner_overview(actor, learner_user_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/guardian-links")
def admin_create_guardian_link(
    body: GuardianLinkBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _guardian(request).link(
            actor,
            guardian_user_id=body.guardian_user_id,
            learner_user_id=body.learner_user_id,
        )
    except ServiceError as e:
        raise _http(e) from e
