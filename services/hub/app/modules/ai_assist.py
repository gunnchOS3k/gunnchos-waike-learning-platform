"""AI assist orchestration: policy + gunnchAI adapter + audit."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _id, _now
from app.modules.ai_policy import AiPolicyService
from app.modules.gunnchai_adapter import (
    ANSWER_KEY_MARKERS,
    AssistRequest,
    AssistResponse,
    GunnchAIAdapter,
    content_hash,
    discover_courses_from_contract,
    material_path_allowed,
    resolve_waike_root,
)

# Keys that must never appear (raw) in ai_assist_audit.detail_json
_AUDIT_REDACT_KEYS = frozenset(
    {
        "query",
        "raw_query",
        "password",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "credentials",
        "secret",
        "answer_key",
        "instructor_context",
        "body",
        "course_materials",
        "text",
        "snippet",
    }
)

_PREFERRED_GROUNDING_GLOBS = (
    "lessons/**/*.md",
    "gunnchai_tutor_cards/**/*.md",
    "syllabi/**/*.md",
    "programs/*.md",
    "labs/**/lab_instructions.md",
    "labs/**/troubleshooting.md",
    "assignment_bodies/**/*.md",
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
        self._assert_scoped_ids(section_id, assessment_id=assessment_id, activity_id=activity_id)
        return self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )

    def set_policy(self, actor: Actor, **kwargs: Any) -> dict[str, Any]:
        # Policy mutation: instructor/admin only (enforced in AiPolicyService + route).
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        section_id = kwargs.get("section_id")
        if not section_id:
            raise ServiceError("SECTION_ID_REQUIRED", 400)
        self.sections.require_staff_scope(actor, section_id)
        self._assert_scoped_ids(
            section_id,
            assessment_id=kwargs.get("assessment_id"),
            activity_id=kwargs.get("activity_id"),
        )
        return self.policy.set_policy(actor, **kwargs)

    def provider_status(self) -> dict[str, Any]:
        return self.adapter.provider_status()

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
        cloud_consent: bool = False,
        processing_mode: str = "local-only",
    ) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        self.sections.require_learner_enrollment(actor, section_id)
        self._assert_scoped_ids(section_id, assessment_id=assessment_id, activity_id=activity_id)
        effective = self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )
        self.policy.assert_capability_allowed(effective, capability, learner_facing=True)
        # Server-resolved grounding only — never accept client-supplied citation text.
        materials = self.resolve_learner_materials(section_id)
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
            target_learner_id=None,
            cloud_consent=cloud_consent,
            processing_mode=processing_mode,
        )
        return self._run(actor, req, effective, allowed_materials=materials)

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
        self._assert_scoped_ids(section_id, assessment_id=assessment_id, activity_id=activity_id)
        if target_learner_id:
            self._assert_target_learner_in_section(section_id, target_learner_id)
        effective = self.policy.resolve_effective(
            section_id, assessment_id=assessment_id, activity_id=activity_id
        )
        self.policy.assert_capability_allowed(effective, capability, learner_facing=False)
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
        out = self._run(actor, req, effective, allowed_materials=[])
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

    def resolve_learner_materials(self, section_id: str) -> list[dict[str, str]]:
        """Resolve learner-visible pack text for the section's installed module only."""
        module_id = self._section_module_id(section_id)
        if not module_id:
            return []
        pack_root = self._find_learner_pack_root(module_id)
        if pack_root is None:
            return []
        materials: list[dict[str, str]] = []
        seen: set[str] = set()
        # Prefer high-signal learner files; cap volume for assist payloads.
        candidates: list[Path] = []
        for pattern in _PREFERRED_GROUNDING_GLOBS:
            candidates.extend(sorted(pack_root.glob(pattern)))
        if not candidates:
            candidates = sorted(pack_root.rglob("*.md"))[:40]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                rel = str(path.relative_to(pack_root)).replace("\\", "/")
            except ValueError:
                continue
            if not material_path_allowed(rel):
                continue
            if rel in seen:
                continue
            # Never pull instructor pack trees even if somehow nested.
            parts_lower = rel.lower()
            if "instructor" in parts_lower or "answer_key" in parts_lower:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            if ANSWER_KEY_MARKERS.search(text):
                continue
            seen.add(rel)
            clipped = text[:4000]
            materials.append(
                {
                    "id": rel,
                    "path": rel,
                    "text": clipped,
                    "content_hash": content_hash(clipped),
                    "title": path.stem,
                    "module_id": module_id,
                }
            )
            if len(materials) >= 24:
                break
        return materials

    def _section_module_id(self, section_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT p.module_id AS module_id
            FROM sections s
            JOIN packages p ON p.package_id = s.package_id
            WHERE s.section_id=?
            """,
            (section_id,),
        ).fetchone()
        return str(row["module_id"]) if row and row["module_id"] else None

    def _find_learner_pack_root(self, module_id: str) -> Path | None:
        """Locate compiled learner pack body for module_id (never instructor)."""
        env_pack = os.environ.get("WAIKE_PACK_OUT")
        candidates: list[Path] = []
        if env_pack:
            candidates.append(Path(env_pack) / module_id / "learner")
            candidates.append(Path(env_pack) / module_id)
        # Platform pack_out_18 next to hub repo root
        hub_root = Path(__file__).resolve().parents[4]
        candidates.append(hub_root / "pack_out_18" / module_id / "learner")
        candidates.append(hub_root / "pack_out" / module_id / "learner")
        waike = resolve_waike_root()
        if waike is not None:
            # Curriculum source is not a pack, but may hold learner-visible markdown.
            digital = waike / "curriculum" / "digital_rc"
            # module folders may use snake or the module id casing
            for child in digital.iterdir() if digital.is_dir() else []:
                if child.is_dir() and child.name.upper().replace("-", "_") == module_id.upper():
                    candidates.append(child)
        for c in candidates:
            if c.is_dir() and any(c.rglob("*.md")):
                return c
        return None

    def _assert_scoped_ids(
        self,
        section_id: str,
        *,
        assessment_id: str | None,
        activity_id: str | None,
    ) -> None:
        if activity_id:
            self._assert_activity_in_section(section_id, activity_id)
        if assessment_id:
            self._assert_assessment_in_section(section_id, assessment_id)

    def _assert_activity_in_section(self, section_id: str, activity_id: str) -> None:
        quiz = self.conn.execute(
            "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=? AND section_id=?",
            (activity_id, section_id),
        ).fetchone()
        if quiz:
            return
        lab = self.conn.execute(
            "SELECT lab_id FROM lab_definitions WHERE lab_id=? AND section_id=?",
            (activity_id, section_id),
        ).fetchone()
        if lab:
            return
        raise ServiceError("ACTIVITY_NOT_IN_SECTION", 403)

    def _assert_assessment_in_section(self, section_id: str, assessment_id: str) -> None:
        # Assessments / assignments may be module-scoped; require package match via section.
        row = self.conn.execute(
            """
            SELECT a.assignment_id AS assignment_id, p.module_id AS module_id
            FROM assignments a
            JOIN sections s ON s.section_id=?
            JOIN packages p ON p.package_id = s.package_id
            WHERE a.assignment_id=? AND a.module_id = p.module_id
            """,
            (section_id, assessment_id),
        ).fetchone()
        if row:
            return
        # Also accept assessment_id matching quiz in section (legacy naming).
        quiz = self.conn.execute(
            "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=? AND section_id=?",
            (assessment_id, section_id),
        ).fetchone()
        if quiz:
            return
        raise ServiceError("ASSESSMENT_NOT_IN_SECTION", 403)

    def _assert_target_learner_in_section(self, section_id: str, learner_id: str) -> None:
        if not self.sections.is_enrolled(learner_id, section_id):
            raise ServiceError("TARGET_LEARNER_NOT_IN_SECTION", 403)

    def _run(
        self,
        actor: Actor,
        req: AssistRequest,
        effective: dict[str, Any],
        *,
        allowed_materials: list[dict[str, str]],
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
        result.citations = self._validate_citations(result.citations, allowed_materials)
        result.grounded = bool(result.citations)
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
            detail={
                "refused": result.refused,
                "citation_count": len(result.citations),
                "grounded": result.grounded,
            },
        )
        return self._public(result, effective)

    def _validate_citations(
        self,
        citations: list[dict[str, str]],
        allowed: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Keep only citations whose source+hash match server-resolved materials."""
        if not allowed:
            return []
        by_path = {m.get("path") or m.get("id"): m for m in allowed}
        by_hash = {m.get("content_hash"): m for m in allowed if m.get("content_hash")}
        out: list[dict[str, str]] = []
        for c in citations:
            source = c.get("source") or ""
            snippet = c.get("snippet") or ""
            if not material_path_allowed(source):
                continue
            mat = by_path.get(source)
            if mat is None:
                # hash-only match still requires known material
                ch = c.get("content_hash") or content_hash(snippet)
                mat = by_hash.get(ch)
            if mat is None:
                continue
            expected = mat.get("content_hash") or content_hash(mat.get("text") or "")
            got = c.get("content_hash") or content_hash(snippet)
            if got != expected and snippet and content_hash(snippet) != expected:
                # Allow prefix snippet of validated text
                full = mat.get("text") or ""
                if snippet and snippet not in full:
                    continue
                got = expected
            out.append(
                {
                    "source": mat.get("path") or source,
                    "snippet": (snippet or (mat.get("text") or "")[:120])[:200],
                    "content_hash": expected,
                }
            )
        return out

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
        safe = self._redact_audit_detail(detail)
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
                json.dumps(safe),
                _now(),
            ),
        )
        self.conn.commit()

    def _redact_audit_detail(self, detail: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in (detail or {}).items():
            lk = str(key).lower()
            if lk in _AUDIT_REDACT_KEYS or any(
                s in lk for s in ("password", "secret", "token", "credential", "api_key", "query")
            ):
                clean[key] = "[redacted]"
                continue
            if isinstance(value, dict):
                clean[key] = self._redact_audit_detail(value)
            elif isinstance(value, list):
                clean[key] = [
                    self._redact_audit_detail(v) if isinstance(v, dict) else ("[redacted]" if isinstance(v, str) and len(v) > 80 else v)
                    for v in value
                ]
            elif isinstance(value, str) and len(value) > 240:
                clean[key] = f"[redacted:{len(value)}chars]"
            else:
                clean[key] = value
        return clean

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
            "detail": self._scrub_public_detail(result.detail),
        }

    def _scrub_public_detail(self, detail: dict[str, Any]) -> dict[str, Any]:
        """Drop fields that could leak raw query / keys / bodies to clients."""
        if not detail:
            return {}
        out: dict[str, Any] = {}
        for key, value in detail.items():
            lk = str(key).lower()
            if lk in _AUDIT_REDACT_KEYS or "query" in lk:
                continue
            if isinstance(value, dict):
                nested = self._scrub_public_detail(value)
                if nested:
                    out[key] = nested
            else:
                out[key] = value
        return out
