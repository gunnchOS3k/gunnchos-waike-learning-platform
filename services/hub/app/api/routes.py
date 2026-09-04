from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor, require_instructor_side, require_learner, require_site_admin
from app.modules.assessment_lifecycle import AssessmentService, ServiceError
from app.modules.gradebook_service import GradebookService
from app.modules.identity import IdentityService
from app.modules.sections import SectionService


router = APIRouter(prefix="/api/v1")


def _assessment(request: Request) -> AssessmentService:
    return request.app.state.assessment


def _identity(request: Request) -> IdentityService:
    return request.app.state.identity


def _sections(request: Request) -> SectionService:
    return request.app.state.sections


def _gradebook(request: Request) -> GradebookService:
    return request.app.state.gradebook


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


# --- auth bodies --------------------------------------------------------------


class LoginBody(BaseModel):
    username: str
    password: str
    site_id: str | None = None


class CreateUserBody(BaseModel):
    username: str
    display_name: str
    password: str
    roles: list[str] = Field(default_factory=lambda: ["learner"])


class AssignRoleBody(BaseModel):
    role: str


class DisableUserBody(BaseModel):
    disabled: bool = True


class CreateSectionBody(BaseModel):
    code: str
    title: str
    package_id: str
    published: bool = False


class AssignStaffBody(BaseModel):
    user_id: str


class EnrollBody(BaseModel):
    user_id: str


class RuntimeMetaBody(BaseModel):
    due_override: dict[str, Any] | None = None
    publish_notes: str | None = None


class DraftBody(BaseModel):
    text_response: str = ""
    artifact_name: str | None = None
    artifact_base64: str | None = None
    section_id: str | None = None


class SubmitBody(BaseModel):
    text_response: str | None = None
    artifact_name: str | None = None
    artifact_base64: str | None = None
    content_type: str = "application/octet-stream"
    idempotency_key: str = Field(min_length=1)
    section_id: str | None = None


class CriterionScore(BaseModel):
    criterion_id: str
    points: float
    level_id: str | None = None
    comment: str = ""


class GradeBody(BaseModel):
    criterion_scores: list[CriterionScore]
    feedback_body: str = ""
    return_to_learner: bool = True


class GradebookScoreBody(BaseModel):
    learner_id: str
    points_earned: float | None = None
    status: str
    reason: str = ""


# --- auth ---------------------------------------------------------------------


@router.post("/auth/login")
def login(body: LoginBody, request: Request) -> dict[str, Any]:
    try:
        return _identity(request).login(body.username, body.password, body.site_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/auth/logout")
def logout(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _identity(request).logout(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/auth/me")
def me(actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return {
        "user_id": actor.actor_id,
        "username": actor.username,
        "display_name": actor.display_name,
        "site_id": actor.site_id,
        "roles": [r.value for r in actor.roles] or [actor.role.value],
        "session_id": actor.session_id,
    }


# --- admin --------------------------------------------------------------------


@router.get("/admin/users")
def admin_list_users(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_site_admin(actor)
    try:
        return _identity(request).list_users(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/users")
def admin_create_user(
    body: CreateUserBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _identity(request).create_user(
            actor, body.username, body.display_name, body.password, body.roles
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/users/{user_id}/disable")
def admin_disable_user(
    user_id: str, body: DisableUserBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _identity(request).disable_user(actor, user_id, body.disabled)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/users/{user_id}/roles")
def admin_assign_role(
    user_id: str, body: AssignRoleBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _identity(request).assign_role(actor, user_id, body.role)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/sections")
def admin_create_section(
    body: CreateSectionBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _sections(request).create_section(
            actor, body.code, body.title, body.package_id, body.published
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/sections/{section_id}/instructors")
def admin_assign_instructor(
    section_id: str, body: AssignStaffBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _sections(request).assign_instructor(actor, section_id, body.user_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/sections/{section_id}/graders")
def admin_assign_grader(
    section_id: str, body: AssignStaffBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _sections(request).assign_grader(actor, section_id, body.user_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/sections/{section_id}/enrollments")
def admin_enroll(
    section_id: str, body: EnrollBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _sections(request).enroll(actor, section_id, body.user_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/enrollments/{enrollment_id}/deactivate")
def admin_deactivate_enrollment(
    enrollment_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _sections(request).deactivate_enrollment(actor, enrollment_id)
    except ServiceError as e:
        raise _http(e) from e


# --- sections / home ----------------------------------------------------------


@router.get("/sections")
def list_sections(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    return _sections(request).list_sections_for_actor(actor)


@router.get("/sections/{section_id}")
def get_section(section_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _sections(request).get_section(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sections/{section_id}/roster")
def roster(section_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_instructor_side(actor)
    try:
        return _sections(request).roster(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.patch("/sections/{section_id}/runtime")
def patch_runtime(
    section_id: str, body: RuntimeMetaBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _sections(request).update_runtime_metadata(
            actor, section_id, body.due_override, body.publish_notes
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/learner/home")
def learner_home(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_learner(actor)
    try:
        return _sections(request).learner_home(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/sections/{section_id}/dashboard")
def instructor_dashboard(
    section_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _sections(request).instructor_dashboard(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


# --- gradebook ----------------------------------------------------------------


@router.get("/sections/{section_id}/gradebook")
def section_gradebook(
    section_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        if actor.role.value == "learner":
            return _gradebook(request).learner_view(actor, section_id)
        require_instructor_side(actor)
        return _gradebook(request).matrix(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/gradebook/items/{item_id}/scores")
def set_gradebook_score(
    item_id: str, body: GradebookScoreBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _gradebook(request).set_score(
            actor, item_id, body.learner_id, body.points_earned, body.status, body.reason
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/gradebook/entries/{entry_id}/overrides")
def gradebook_overrides(
    entry_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> list[dict[str, Any]]:
    require_instructor_side(actor)
    try:
        return _gradebook(request).override_audits(actor, entry_id)
    except ServiceError as e:
        raise _http(e) from e


# --- assessment (PR2 preserved) -----------------------------------------------


@router.get("/assignments")
def list_assignments(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    return _assessment(request).list_assignments(actor)


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _assessment(request).get_assignment(assignment_id)
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
        return _assessment(request).save_draft(
            actor, assignment_id, body.text_response, body.artifact_name, art, body.section_id
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/assignments/{assignment_id}/draft")
def get_draft(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    require_learner(actor)
    try:
        return _assessment(request).get_draft(actor, assignment_id)
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
        return _assessment(request).submit(
            actor,
            assignment_id,
            idempotency_key=body.idempotency_key,
            text_response=body.text_response,
            artifact_name=body.artifact_name,
            artifact_bytes=art,
            content_type=body.content_type,
            section_id=body.section_id,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/assignments/{assignment_id}/history")
def history(assignment_id: str, request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    require_learner(actor)
    try:
        return _assessment(request).submission_history(actor, assignment_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _assessment(request).get_submission(actor, submission_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/submissions/{submission_id}/receipt")
def get_receipt(submission_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        sub = _assessment(request).get_submission(actor, submission_id)
    except ServiceError as e:
        raise _http(e) from e
    if not sub.get("receipt"):
        raise HTTPException(status_code=404, detail="RECEIPT_NOT_FOUND")
    return sub["receipt"]


@router.get("/remediation")
def remediation(request: Request, actor: Actor = Depends(require_actor)) -> list[dict[str, Any]]:
    try:
        return _assessment(request).list_remediation(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/portfolio")
def portfolio(
    request: Request,
    learner_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    try:
        return _assessment(request).list_portfolio(actor, learner_id=learner_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/gradebook")
def gradebook_legacy(
    request: Request,
    learner_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    try:
        return _assessment(request).gradebook(actor, learner_id=learner_id)
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
        row = _assessment(request).latest_mastery(actor, assignment_id, learner_id=learner_id)
    except ServiceError as e:
        raise _http(e) from e
    return row or {}


@router.get("/instructor/assignments/{assignment_id}/queue")
def instructor_queue(
    assignment_id: str,
    request: Request,
    section_id: str | None = None,
    actor: Actor = Depends(require_actor),
) -> list[dict[str, Any]]:
    require_instructor_side(actor)
    try:
        return _assessment(request).instructor_queue(actor, assignment_id, section_id=section_id)
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
        return _assessment(request).grade_submission(
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
        return _assessment(request).grade_audit_trail(actor, grade_id)
    except ServiceError as e:
        raise _http(e) from e
