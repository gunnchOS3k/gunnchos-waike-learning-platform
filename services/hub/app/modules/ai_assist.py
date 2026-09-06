"""AI assist orchestration: policy + gunnchAI adapter + audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _id, _now
from app.modules.ai_policy import AiPolicyService
from app.modules.gunnchai_adapter import (
    AssistRequest,
    AssistResponse,
    GunnchAIAdapter,
    discover_courses_from_contract,
    resolve_waike_root,
)


class AiAssistService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        sections: Any,
        policy: AiPolicyService,
        adapter: GunnchAIAdapter | None = None,
    ) -> None:
        self.conn = conn
        self.sections = sections
        self.policy = policy
        self.adapter = adapter or GunnchAIAdapter()

    def get_effective_policy(
        self,
        actor: Actor,
        section_id: str,
        *,
        assessment_id: str | None = None,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        self.sections.require_section_access(actor, section_id)
        return self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )

    def set_policy(self, actor: Actor, **kwargs: Any) -> dict[str, Any]:
        return self.policy.set_policy(actor, **kwargs)

    def provider_status(self) -> dict[str, Any]:
        return self.adapter.contract_meta()

    def discover_courses(self) -> dict[str, Any]:
        root = resolve_waike_root()
        if root is None:
            return {
                "waike_root": None,
                "course_count": 0,
                "hardcoded_course_names": False,
                "courses": [],
            }
        out = discover_courses_from_contract(root)
        out["waike_root"] = str(root)
        return out

    def learner_assist(
        self,
        actor: Actor,
        *,
        section_id: str,
        capability: str,
        query: str,
        assessment_id: str | None = None,
        activity_id: str | None = None,
        course_materials: list[dict[str, str]] | None = None,
        cloud_consent: bool = False,
        processing_mode: str = "local-only",
    ) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        self.sections.require_learner_enrollment(actor, section_id)
        effective = self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )
        self.policy.assert_capability_allowed(effective, capability, learner_facing=True)
        materials = self._sanitize_learner_materials(course_materials or [])
        req = AssistRequest(
            mode="LEARNER_TUTOR",
            capability=capability,
            query=query,
            section_id=section_id,
            actor_id=actor.actor_id,
            site_id=actor.site_id,
            learner_facing=True,
            course_materials=materials,
            instructor_context=None,
            cloud_consent=cloud_consent,
            processing_mode=processing_mode,
        )
        return self._run(actor, req, effective)

    def instructor_assist(
        self,
        actor: Actor,
        *,
        section_id: str,
        capability: str,
        query: str,
        assessment_id: str | None = None,
        activity_id: str | None = None,
        instructor_context: dict[str, Any] | None = None,
        target_learner_id: str | None = None,
        cloud_consent: bool = False,
        processing_mode: str = "local-only",
    ) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        self.sections.require_staff_scope(actor, section_id)
        effective = self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )
        self.policy.assert_capability_allowed(effective, capability, learner_facing=False)
        # Instructor may read keys only in EDUCATOR_COPILOT; still suggestions-only.
        req = AssistRequest(
            mode="EDUCATOR_COPILOT",
            capability=capability,
            query=query,
            section_id=section_id,
            actor_id=actor.actor_id,
            site_id=actor.site_id,
            learner_facing=False,
            course_materials=[],
            instructor_context=instructor_context,
            target_learner_id=target_learner_id,
            cloud_consent=cloud_consent,
            processing_mode=processing_mode,
        )
        out = self._run(actor, req, effective)
        out["suggestion_only"] = True
        out["mutates_grades"] = False
        out["hitl_required"] = True
        out["apply_hint"] = (
            "AI suggestions do not change grades. Use the normal grading endpoints "
            "with an explicit authorized instructor action to apply scores."
        )
        return out

    def refuse_grade_mutation(
        self,
        actor: Actor,
        *,
        section_id: str | None = None,
        submission_id: str | None = None,
        points: float | None = None,
        explicit_confirm: bool = False,
    ) -> dict[str, Any]:
        """Any grade mutation via AI API is refused (even with confirm).

        Grades must go through authorized non-AI grading routes so audit trails
        remain on the gradebook path. Confirm flag still does not auto-apply.
        """
        qh = hashlib.sha256(
            f"{submission_id}:{points}:{explicit_confirm}".encode()
        ).hexdigest()[:16]
        self._write_audit(
            actor,
            section_id=section_id,
            mode="EDUCATOR_COPILOT",
            capability="grade_mutate",
            policy=None,
            allowed=0,
            refusal_code="AI_SILENT_GRADE_FORBIDDEN",
            query_hash=qh,
            provider_id="none",
            detail={
                "submission_id": submission_id,
                "points": points,
                "explicit_confirm": explicit_confirm,
            },
        )
        raise ServiceError("AI_SILENT_GRADE_FORBIDDEN", 403)

    def _run(
        self, actor: Actor, req: AssistRequest, effective: dict[str, Any]
    ) -> dict[str, Any]:
        qh = hashlib.sha256(req.query.encode("utf-8")).hexdigest()
        try:
            result = self.adapter.assist(req)
        except ServiceError as e:
            self._write_audit(
                actor,
                section_id=req.section_id,
                mode=req.mode,
                capability=req.capability,
                policy=effective.get("policy"),
                allowed=0,
                refusal_code=e.code,
                query_hash=qh[:16],
                provider_id=getattr(self.adapter.provider, "provider_id", "none"),
                detail={"error": e.code},
            )
            raise
        self._write_audit(
            actor,
            section_id=req.section_id,
            mode=req.mode,
            capability=req.capability,
            policy=effective.get("policy"),
            allowed=0 if result.refused else 1,
            refusal_code=result.refusal_code,
            query_hash=qh[:16],
            provider_id=result.provider_id,
            detail={"refused": result.refused},
        )
        return self._public(result, effective)

    def _sanitize_learner_materials(
        self, materials: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Drop instructor-only markers from learner-supplied grounding."""
        from app.modules.gunnchai_adapter import ANSWER_KEY_MARKERS

        clean: list[dict[str, str]] = []
        for m in materials:
            text = m.get("text") or m.get("body") or ""
            path = m.get("path") or m.get("id") or ""
            if ANSWER_KEY_MARKERS.search(text) or ANSWER_KEY_MARKERS.search(path):
                continue
            if "instructor" in path.lower() and "key" in path.lower():
                continue
            clean.append({"id": path or "material", "path": path, "text": text[:4000]})
        return clean

    def _write_audit(
        self,
        actor: Actor,
        *,
        section_id: str | None,
        mode: str,
        capability: str,
        policy: str | None,
        allowed: int,
        refusal_code: str | None,
        query_hash: str,
        provider_id: str,
        detail: dict[str, Any],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ai_assist_audit(
              event_id, actor_id, site_id, section_id, mode, capability, policy,
              allowed, refusal_code, query_hash, provider_id, detail_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _id("aiaud"),
                actor.actor_id,
                actor.site_id,
                section_id,
                mode,
                capability,
                policy,
                allowed,
                refusal_code,
                query_hash,
                provider_id,
                json.dumps(detail),
                _now(),
            ),
        )
        self.conn.commit()

    def _public(self, result: AssistResponse, effective: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": result.ok and not result.refused,
            "text": result.text,
            "grounded": result.grounded,
            "citations": result.citations,
            "provider_id": result.provider_id,
            "mode": result.mode,
            "capability": result.capability,
            "disclosure": result.disclosure,
            "refused": result.refused,
            "refusal_code": result.refusal_code,
            "suggestion_only": result.suggestion_only,
            "mutates_grades": False,
            "policy": effective.get("policy"),
            "detail": result.detail,
        }
