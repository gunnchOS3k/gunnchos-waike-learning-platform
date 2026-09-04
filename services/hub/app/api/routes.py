from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor, require_instructor_side, require_learner
from app.modules.assessment_lifecycle import AssessmentService, ServiceError


router = APIRouter(prefix="/api/v1")


def _svc(request: Request) -> AssessmentService:
    return request.app.state.assessment


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


class DraftBody(BaseModel):
    text_response: str = ""
    artifact_name: str | None = None
    artifact_base64: str | None = None


class SubmitBody(BaseModel):
    text_response: str | None = None
    artifact_name: str | None = None
    artifact_base64: str | None = None
    content_type: str = "application/octet-stream"
    idempotency_key: str = Field(min_length=1)


class CriterionScore(BaseModel):
    criterion_id: str
    points: float
    level_id: str | None = None
    comment: str = ""


class GradeBody(BaseModel):
    criterion_scores: list[CriterionScore]
    feedback_body: str = ""
    return_to_learner: bool = True


@router.get("/assignments")
def list_assignments(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    return _svc(request).list_assignments(actor)


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).get_assignment(assignment_id)
    except ServiceError as e:
        raise _http(e) from e


@router.put("/assignments/{assignment_id}/draft")
def save_draft(
    assignment_id: str,
    body: DraftBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_learner(actor)
    art = base64.b64decode(body.artifact_base64) if body.artifact_base64 else None
    try:
        return _svc(request).save_draft(actor, assignment_id, body.text_response, body.artifact_name, art)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/assignments/{assignment_id}/draft")
def get_draft(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    require_learner(actor)
    try:
        return _svc(request).get_draft(actor, assignment_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/assignments/{assignment_id}/submit")
def submit(
    assignment_id: str,
    body: SubmitBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_learner(actor)
    art = base64.b64decode(body.artifact_base64) if body.artifact_base64 else None
    try:
        return _svc(request).submit(
            actor,
            assignment_id,
            idempotency_key=body.idempotency_key,
            text_response=body.text_response,
            artifact_name=body.artifact_name,
            artifact_bytes=art,
            content_type=body.content_type,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/assignments/{assignment_id}/history")
def history(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_learner(actor)
    try:
        return _svc(request).submission_history(actor, assignment_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _svc(request).get_submission(actor, submission_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/submissions/{submission_id}/receipt")
def get_receipt(submission_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        sub = _svc(request).get_submission(actor, submission_id)
    except ServiceError as e:
        raise _http(e) from e
    if not sub.get("receipt"):
        raise HTTPException(status_code=404, detail="RECEIPT_NOT_FOUND")
    return sub["receipt"]


@router.get("/remediation")
def remediation(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _svc(request).list_remediation(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/portfolio")
def portfolio(
    request: Request,
    learner_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    try:
        return _svc(request).list_portfolio(actor, learner_id=learner_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/gradebook")
def gradebook(
    request: Request,
    learner_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    try:
        return _svc(request).gradebook(actor, learner_id=learner_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/assignments/{assignment_id}/mastery")
def mastery(
    assignment_id: str,
    request: Request,
    learner_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    try:
        row = _svc(request).latest_mastery(actor, assignment_id, learner_id=learner_id)
    except ServiceError as e:
        raise _http(e) from e
    return row or {}


@router.get("/instructor/assignments/{assignment_id}/queue")
def instructor_queue(
    assignment_id: str,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    require_instructor_side(actor)
    try:
        return _svc(request).instructor_queue(actor, assignment_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/submissions/{submission_id}/grade")
def grade(
    submission_id: str,
    body: GradeBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _svc(request).grade_submission(
            actor,
            submission_id,
            criterion_scores=[c.model_dump() for c in body.criterion_scores],
            feedback_body=body.feedback_body,
            return_to_learner=body.return_to_learner,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/grades/{grade_id}/audit")
def grade_audit(grade_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_instructor_side(actor)
    try:
        return _svc(request).grade_audit_trail(actor, grade_id)
    except ServiceError as e:
        raise _http(e) from e
