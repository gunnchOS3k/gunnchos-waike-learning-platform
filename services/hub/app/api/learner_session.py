"""Authenticated lesson open and formative practice.

Opening a lesson records learner progress only. Practice stays stateless and
does not write a grade. Grades remain on the instructor routes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import Actor, require_actor, require_learner
from app.api.public_practice import Responses, evaluate as evaluate_practice, evaluate_installed_module
from app.modules.assessment_lifecycle import ServiceError
from app.modules.gunnchai_adapter import resolve_waike_root

router = APIRouter(prefix="/api/v1", tags=["learner session"])


def _module_id(request: Request, section_id: str) -> str:
    row = request.app.state.db.execute(
        """
        SELECT p.module_id AS module_id
        FROM sections s
        JOIN packages p ON p.package_id = s.package_id
        WHERE s.section_id=?
        """,
        (section_id,),
    ).fetchone()
    if not row or not row["module_id"]:
        raise HTTPException(404, "Section has no lesson pack")
    return str(row["module_id"])


def _lesson_path(request: Request, section_id: str, week: int) -> tuple[str, Path]:
    if not 1 <= week <= 10:
        raise HTTPException(404, "Unknown lesson")
    root = resolve_waike_root()
    if root is None:
        raise HTTPException(503, "Canonical curriculum is not configured")
    module_id = _module_id(request, section_id)
    base = (root / "curriculum" / "digital_rc").resolve()
    folder = base / module_id
    if not folder.resolve().is_relative_to(base):
        raise HTTPException(503, "Invalid lesson pack")
    path = (folder / "weeks" / f"w{week:02d}" / "lesson.md").resolve()
    if not path.is_file() or not path.is_relative_to(base):
        raise HTTPException(404, "Lesson is not installed")
    return module_id, path


def _enrolled_learner(request: Request, section_id: str, actor: Actor) -> None:
    require_learner(actor)
    try:
        request.app.state.sections.require_learner_enrollment(actor, section_id)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc


@router.get("/sections/{section_id}/lessons/{week}")
def open_lesson(
    section_id: str,
    week: int,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict:
    _enrolled_learner(request, section_id, actor)
    module_id, path = _lesson_path(request, section_id, week)
    text = path.read_text(encoding="utf-8")
    lesson_id = f"w{week:02d}"
    mutation_id = (
        f"open-{actor.actor_id}-{lesson_id}"
        if module_id == "DIGITAL_CONFIDENCE"
        else f"open-{actor.actor_id}-{section_id}-{lesson_id}"
    )
    try:
        request.app.state.sync.apply_mutation(
            actor,
            client_mutation_id=mutation_id,
            site_id=actor.site_id,
            section_id=section_id,
            device_id="lesson-session",
            entity_type="lesson_progress",
            entity_id=lesson_id,
            base_revision=0,
            operation="upsert",
            payload={
                "pack_id": module_id,
                "lesson_id": lesson_id,
                "percent_complete": 1,
            },
        )
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return {
        "section_id": section_id,
        "module_id": module_id,
        "lesson_id": lesson_id,
        "path": f"weeks/{lesson_id}/lesson.md",
        "text": text,
        "progress_store": "lesson_progress",
        "grade_written": False,
    }


@router.post("/sections/{section_id}/lessons/{week}/practice")
def practice_lesson(
    section_id: str,
    week: int,
    body: Responses,
    request: Request,
    actor: Actor = Depends(require_actor),
) -> dict:
    _enrolled_learner(request, section_id, actor)
    module_id, _path = _lesson_path(request, section_id, week)
    try:
        result = evaluate_practice(module_id, week, body, request)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        result = evaluate_installed_module(getattr(request.app.state, "waike_root", None), module_id, week, body)
    result["persisted"] = False
    result["grade_written"] = False
    result["section_id"] = section_id
    return result
