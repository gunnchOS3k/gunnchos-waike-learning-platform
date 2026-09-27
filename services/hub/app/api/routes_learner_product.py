from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor
from app.modules.assessment_lifecycle import ServiceError
from app.modules.learner_product import LearnerProductService


router = APIRouter(prefix="/api/v1")


def _svc(request: Request) -> LearnerProductService:
    return request.app.state.learner_product


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


class CopyBody(BaseModel):
    source_section_id: str
    code: str
    title: str
    term: str | None = None
    instructor_id: str | None = None


class ShiftBody(BaseModel):
    delta_hours: int = Field(..., ge=-24 * 90, le=24 * 90)


class CommentBody(BaseModel):
    title: str
    body: str


class PinBody(BaseModel):
    pinned: bool


@router.get("/learner/search")
def search(q: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).search(actor, q)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/learner/notifications")
def notifications(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).notifications(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/learner/notifications/{notice_id}/read")
def mark_read(notice_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, str]:
    try:
        _svc(request).mark_read(actor, notice_id)
        return {"status": "ok"}
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sections/{section_id}/announcements")
def announcements(section_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).announcements(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sections/{section_id}/modules")
def modules(section_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).modules(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/sections/copy")
def copy_section(body: CopyBody, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).copy_section(actor, body.model_dump())
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/sections/{section_id}/due-shift/preview")
def preview_shift(
    section_id: str, hours: int, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _svc(request).preview_due_shift(actor, section_id, hours)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/sections/{section_id}/due-shift")
def apply_shift(
    section_id: str, body: ShiftBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _svc(request).apply_due_shift(actor, section_id, body.delta_hours)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/comment-bank")
def list_comments(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).list_comments(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/comment-bank")
def upsert_comment(body: CommentBody, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).upsert_comment(actor, body.title, body.body)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/sections/{section_id}/intervention")
def intervention(section_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).intervention(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/mlv/consumer-summary")
def mlv_summary(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).mlv_summary(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/school-apps")
def school_apps(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).list_school_apps(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/school-apps/{app_id}/pin")
def pin_app(app_id: str, body: PinBody, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, str]:
    try:
        _svc(request).pin_school_app(actor, app_id, body.pinned)
        return {"status": "ok"}
    except ServiceError as e:
        raise _http(e) from e
