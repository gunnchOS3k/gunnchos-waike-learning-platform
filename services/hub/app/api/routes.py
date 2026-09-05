from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor, require_instructor_side, require_learner, require_site_admin
from app.modules.activity_engine import ActivityEngine
from app.modules.assessment_lifecycle import AssessmentService, ServiceError
from app.modules.gradebook_service import GradebookService
from app.modules.identity import IdentityService
from app.modules.sections import SectionService
from app.modules.sync import SyncService


router = APIRouter(prefix="/api/v1")


def _assessment(request: Request) -> AssessmentService:
    return request.app.state.assessment


def _identity(request: Request) -> IdentityService:
    return request.app.state.identity


def _sections(request: Request) -> SectionService:
    return request.app.state.sections


def _gradebook(request: Request) -> GradebookService:
    return request.app.state.gradebook


def _sync(request: Request) -> SyncService:
    return request.app.state.sync


def _activities(request: Request) -> ActivityEngine:
    return request.app.state.activities


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


# --- auth bodies --------------------------------------------------------------


class LoginBody(BaseModel):
    username: str
    password: str
    # Required: usernames are site-scoped UNIQUE(site_id, username); no ambiguous multi-site login.
    site_id: str = Field(min_length=1)


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


# --- Gate A: offline sync -----------------------------------------------------


class LeaseBody(BaseModel):
    section_id: str
    device_id: str
    ttl_hours: int = 72


class MutationBody(BaseModel):
    client_mutation_id: str = Field(min_length=8)
    site_id: str
    section_id: str
    device_id: str
    entity_type: str
    entity_id: str
    base_revision: int = 0
    operation: str
    payload: dict[str, Any] = Field(default_factory=dict)
    local_sequence: int = 0
    lease_id: str | None = None


class RevokeLeaseBody(BaseModel):
    reason: str = "revoked"


@router.post("/sync/leases")
def issue_lease(body: LeaseBody, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _sync(request).issue_lease(actor, body.section_id, body.device_id, body.ttl_hours)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sync/leases/{lease_id}")
def get_lease(lease_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    lease = _sync(request).get_lease(lease_id)
    if not lease:
        raise HTTPException(status_code=404, detail="LEASE_NOT_FOUND")
    if lease["user_id"] != actor.actor_id and not actor.is_instructor_side:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return lease


@router.post("/sync/leases/{lease_id}/revoke")
def revoke_lease(
    lease_id: str, body: RevokeLeaseBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _sync(request).revoke_lease(actor, lease_id, body.reason)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/sync/mutations")
def apply_mutation(
    body: MutationBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _sync(request).apply_mutation(
            actor,
            client_mutation_id=body.client_mutation_id,
            site_id=body.site_id,
            section_id=body.section_id,
            device_id=body.device_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            base_revision=body.base_revision,
            operation=body.operation,
            payload=body.payload,
            local_sequence=body.local_sequence,
            lease_id=body.lease_id,
            activity_handler=_activities(request),
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sync/receipts/{client_mutation_id}")
def sync_receipt(
    client_mutation_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _sync(request).get_receipt(actor, client_mutation_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/sync/pull")
def sync_pull(
    section_id: str,
    request: Request,
    since_revision: int = 0,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    try:
        return _sync(request).pull_changes(actor, section_id, since_revision)
    except ServiceError as e:
        raise _http(e) from e


# --- Gate A: activity engine --------------------------------------------------


class QuizSubmitBody(BaseModel):
    responses: dict[str, Any] = Field(default_factory=dict)
    client_mutation_id: str | None = None
    client_elapsed_minutes: float | None = None


class ManualQuizGradeBody(BaseModel):
    item_id: str
    points: float
    comment: str = ""


class LabCompleteBody(BaseModel):
    evidence: dict[str, Any] = Field(default_factory=dict)
    artifact_hashes: list[str] = Field(default_factory=list)
    client_mutation_id: str = Field(min_length=8)
    fabricate_hardware: bool = False


class ThreadBody(BaseModel):
    section_id: str
    title: str


class PostBody(BaseModel):
    body: str
    parent_post_id: str | None = None
    as_draft: bool = False
    client_mutation_id: str | None = None


class ModerateBody(BaseModel):
    note: str
    delete: bool = False


class GroupBody(BaseModel):
    section_id: str
    name: str
    member_ids: list[str] = Field(default_factory=list)


class GroupSubmitBody(BaseModel):
    activity_id: str
    activity_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    contributions: list[dict[str, Any]] = Field(default_factory=list)


class AccommodationBody(BaseModel):
    learner_id: str
    section_id: str
    time_multiplier: float | None = None
    availability_extension_minutes: int | None = None
    attempt_override: int | None = None
    due_extension_minutes: int | None = None
    alternate_modality: str | None = None
    notes_private: str | None = None


class ReusableCommentBody(BaseModel):
    body: str
    section_id: str | None = None
    criterion_id: str | None = None


class BatchGradeBody(BaseModel):
    section_id: str
    criterion_id: str
    points: float
    attempt_ids: list[str]
    comment: str = ""


class RegradeBody(BaseModel):
    submission_id: str
    reason: str


@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _activities(request).learner_quiz_view(actor, quiz_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/quizzes/{quiz_id}/answer-key")
def quiz_answer_key(
    quiz_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).instructor_answer_key(actor, quiz_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/quizzes/{quiz_id}/attempts")
def start_quiz(
    quiz_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_learner(actor)
    try:
        return _activities(request).start_quiz_attempt(actor, quiz_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/quiz-attempts/{attempt_id}/submit")
def submit_quiz(
    attempt_id: str,
    body: QuizSubmitBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_learner(actor)
    try:
        return _activities(request).submit_quiz_attempt(
            actor,
            attempt_id,
            body.responses,
            client_mutation_id=body.client_mutation_id,
            client_elapsed_minutes=body.client_elapsed_minutes,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/quiz-attempts/{attempt_id}/manual-grade")
def manual_quiz_grade(
    attempt_id: str,
    body: ManualQuizGradeBody,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).grade_manual_quiz_item(
            actor, attempt_id, body.item_id, body.points, body.comment
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/labs/{lab_id}")
def get_lab(lab_id: str, request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _activities(request).get_lab(actor, lab_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/labs/{lab_id}/runs")
def complete_lab(
    lab_id: str, body: LabCompleteBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_learner(actor)
    try:
        return _activities(request).complete_lab_run(
            actor,
            lab_id,
            evidence=body.evidence,
            artifact_hashes=body.artifact_hashes,
            client_mutation_id=body.client_mutation_id,
            fabricate_hardware=body.fabricate_hardware,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/discussions/threads")
def create_thread(
    body: ThreadBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _activities(request).create_thread(actor, body.section_id, body.title)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/discussions/threads/{thread_id}/posts")
def post_discussion(
    thread_id: str, body: PostBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _activities(request).post_or_draft(
            actor,
            thread_id,
            body.body,
            parent_post_id=body.parent_post_id,
            as_draft=body.as_draft,
            client_mutation_id=body.client_mutation_id,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/discussions/posts/{post_id}/moderate")
def moderate_discussion(
    post_id: str, body: ModerateBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).moderate_post(actor, post_id, body.note, body.delete)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/groups")
def create_group(
    body: GroupBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).create_group(actor, body.section_id, body.name, body.member_ids)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/groups/{group_id}/submissions")
def group_submit(
    group_id: str, body: GroupSubmitBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _activities(request).group_submit(
            actor,
            group_id,
            body.activity_id,
            body.activity_type,
            body.payload,
            body.contributions,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/groups/{group_id}/submissions")
def list_group_subs(
    group_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> list[dict[str, Any]]:
    try:
        return _activities(request).list_group_submissions(actor, group_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/accommodations")
def upsert_accommodation(
    body: AccommodationBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).upsert_accommodation(
            actor,
            learner_id=body.learner_id,
            section_id=body.section_id,
            time_multiplier=body.time_multiplier,
            availability_extension_minutes=body.availability_extension_minutes,
            attempt_override=body.attempt_override,
            due_extension_minutes=body.due_extension_minutes,
            alternate_modality=body.alternate_modality,
            notes_private=body.notes_private,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/accommodations/{learner_id}")
def get_accommodation(
    learner_id: str,
    section_id: str,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    try:
        return _activities(request).get_accommodation(actor, learner_id, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/sections/{section_id}/next-ungraded")
def next_ungraded(
    section_id: str,
    request: Request,
    anonymous: bool = False,
    actor: Actor = Depends(require_actor),
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).next_ungraded(actor, section_id, anonymous=anonymous)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/instructor/sections/{section_id}/grading-progress")
def grading_progress(
    section_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).grading_progress(actor, section_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/reusable-comments")
def reusable_comment(
    body: ReusableCommentBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).add_reusable_comment(
            actor, body.body, body.section_id, body.criterion_id
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/batch-criterion")
def batch_criterion(
    body: BatchGradeBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _activities(request).batch_apply_criterion(
            actor, body.section_id, body.criterion_id, body.points, body.attempt_ids, body.comment
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/instructor/regrade-queue")
def regrade_queue(
    body: RegradeBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _activities(request).enqueue_regrade(actor, body.submission_id, body.reason)
    except ServiceError as e:
        raise _http(e) from e
