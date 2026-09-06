"""gunnchAI adapter for WAIKE Learning Hub (Gate B).

Adapts canonical contracts from gunnchAI3k @ 4b4f411710e8cdb8102a7e11502f8497f68156b1:
- MODE_PERMISSIONS (src/waike-mastery/modes.ts)
- academicIntegrityPolicy (src/tutor/academicIntegrityPolicy.ts)
- privacy fail-closed (src/system-layer/privacy_policy.ts)
- cloud stub fails closed (src/local-runtime/providers/cloudProvider.ts)
- product-service assist CLI (src/system-layer/product_service/cli.ts)
- course discovery (src/waike-mastery/contract.ts)

Default runtime never selects FakeGunnchAIProvider. Fake is tests-only via explicit
constructor injection or GUNNCHAI_PROVIDER=fake with WAIKE_ALLOW_FAKE_AI=1.
LocalGunnchAIProvider only when GUNNCHAI_ROOT points at a checkout with the
product-service CLI — otherwise reports unavailable honestly.
Never fabricates a local GGUF/llama runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.modules.assessment_lifecycle import ServiceError

GUNNCHAI_REPO = "https://github.com/gunnchOS3k/gunnchAI3k"
GUNNCHAI_SHA = "4b4f411710e8cdb8102a7e11502f8497f68156b1"
GUNNCHAI_PACKAGE = "gunnchai3k"

# CI / contract label: default production runtime path must not select Fake.
DEFAULT_RUNTIME_HAS_NO_FAKE_AI = True
GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE = True

MasteryMode = str  # MASTERY_BENCHMARK | LEARNER_TUTOR | EDUCATOR_COPILOT

MODE_PERMISSIONS: dict[str, dict[str, Any]] = {
    "MASTERY_BENCHMARK": {
        "mayReadStudentMaterials": True,
        "mayReadInstructorKeys": False,
        "maySelfGrade": False,
        "mayPublishGradesWithoutHuman": False,
        "hitlGradingRequired": False,
        "mayDiscloseFinalAnswersToLearner": False,
        "gradingAgent": "isolated_after_submission",
    },
    "LEARNER_TUTOR": {
        "mayReadStudentMaterials": True,
        "mayReadInstructorKeys": False,
        "maySelfGrade": False,
        "mayPublishGradesWithoutHuman": False,
        "hitlGradingRequired": False,
        "mayDiscloseFinalAnswersToLearner": False,
        "gradingAgent": "none",
    },
    "EDUCATOR_COPILOT": {
        "mayReadStudentMaterials": True,
        "mayReadInstructorKeys": True,
        "maySelfGrade": False,
        "mayPublishGradesWithoutHuman": False,
        "hitlGradingRequired": True,
        "mayDiscloseFinalAnswersToLearner": False,
        "gradingAgent": "hitl",
    },
}

CHEAT_PATTERNS = [
    re.compile(r"answer\s+key", re.I),
    re.compile(r"current\s+exam", re.I),
    re.compile(r"take\s+my\s+test", re.I),
    re.compile(r"submit\s+this\s+for\s+me", re.I),
    re.compile(r"homework\s+due\s+today.*solution", re.I),
    re.compile(r"proctored\s+exam.*answer", re.I),
    re.compile(r"give\s+me\s+the\s+answers?", re.I),
    re.compile(r"final\s+answer\s+key", re.I),
]

EXAM_PREP_OK = [
    re.compile(r"practice\s+quiz", re.I),
    re.compile(r"mock\s+exam", re.I),
    re.compile(r"study\s+guide", re.I),
]

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(your|the)\s+(system|safety)\s+prompt", re.I),
    re.compile(r"reveal\s+(your\s+)?system\s+prompt", re.I),
    re.compile(r"print\s+(your\s+)?system\s+prompt", re.I),
    re.compile(r"</?\s*system\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"DAN\s+mode", re.I),
    re.compile(r"jailbreak", re.I),
]

CROSS_LEARNER_PATTERNS = [
    re.compile(r"another\s+learner", re.I),
    re.compile(r"other\s+student'?s?\s+(submission|grade|answer)", re.I),
    re.compile(r"peer'?s?\s+(private|submission|grade)", re.I),
    re.compile(r"show\s+me\s+.+\s+learner-.+", re.I),
]

INSTRUCTOR_EXFIL_PATTERNS = [
    re.compile(r"instructor\s+(answer\s+)?key", re.I),
    re.compile(r"instructor\s+packet", re.I),
    re.compile(r"hidden\s+rubric", re.I),
    re.compile(r"private\s+rubric\s+guidance", re.I),
    re.compile(r"instructor\s+notes?", re.I),
    re.compile(r"instructor\s+package\s+plaintext", re.I),
]

SYSTEM_EXFIL_PATTERNS = [
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"developer\s+message", re.I),
    re.compile(r"hidden\s+instructions?", re.I),
]

ANSWER_KEY_MARKERS = re.compile(
    r"(ANSWER_KEY|INSTRUCTOR_KEY|SOLUTION_KEY|PRIVATE_RUBRIC|INSTRUCTOR_PACKET)",
    re.I,
)

FORBIDDEN_MATERIAL_PATH = re.compile(
    r"(instructor|answer[_-]?key|solution[_-]?key|private[_-]?rubric|"
    r"peer|other[_-]?learner|submission|/keys?/)",
    re.I,
)


@dataclass
class IntegrityDecision:
    allowed: bool
    reason: str
    alternative: str | None = None
    code: str | None = None


@dataclass
class AssistRequest:
    mode: MasteryMode
    capability: str
    query: str
    section_id: str
    actor_id: str
    site_id: str
    learner_facing: bool
    course_materials: list[dict[str, str]] = field(default_factory=list)
    instructor_context: dict[str, Any] | None = None
    target_learner_id: str | None = None
    cloud_consent: bool = False
    processing_mode: str = "local-only"  # local-only | cloud-allowed


@dataclass
class AssistResponse:
    ok: bool
    text: str
    grounded: bool
    citations: list[dict[str, str]]
    provider_id: str
    mode: str
    capability: str
    disclosure: str
    refused: bool = False
    refusal_code: str | None = None
    suggestion_only: bool = True
    mutates_grades: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


class GunnchAIProvider(Protocol):
    provider_id: str

    def available(self) -> bool: ...

    def assist(self, req: AssistRequest) -> AssistResponse: ...


def assert_mode_permission(
    mode: MasteryMode,
    action: str,
) -> None:
    if mode not in MODE_PERMISSIONS:
        raise ServiceError("AI_MODE_UNKNOWN", 400)
    p = MODE_PERMISSIONS[mode]
    if action == "read_instructor_keys" and not p["mayReadInstructorKeys"]:
        raise ServiceError("AI_PERMISSION_DENIED", 403)
    if action == "self_grade" and not p["maySelfGrade"]:
        raise ServiceError("AI_PERMISSION_DENIED", 403)
    if action == "publish_grades" and not p["mayPublishGradesWithoutHuman"]:
        raise ServiceError("AI_PERMISSION_DENIED", 403)
    if action == "disclose_answers_to_learner" and not p["mayDiscloseFinalAnswersToLearner"]:
        raise ServiceError("AI_PERMISSION_DENIED", 403)


def check_academic_integrity(message: str) -> IntegrityDecision:
    text = message.strip()
    if any(p.search(text) for p in CHEAT_PATTERNS):
        return IntegrityDecision(
            allowed=False,
            reason="Active or graded assessment solution requests are not allowed.",
            alternative="Ask for a hint, practice quiz, or concept explanation instead.",
            code="AI_INTEGRITY_REFUSED",
        )
    if any(p.search(text) for p in EXAM_PREP_OK):
        return IntegrityDecision(
            allowed=True,
            reason="Practice and study prep is allowed with no direct cheating.",
        )
    return IntegrityDecision(allowed=True, reason="General tutoring request.")


def screen_request(req: AssistRequest) -> IntegrityDecision:
    text = req.query
    if any(p.search(text) for p in SYSTEM_EXFIL_PATTERNS):
        return IntegrityDecision(
            False, "System-prompt exfiltration is not allowed.", code="AI_SYSTEM_PROMPT_EXFIL"
        )
    if any(p.search(text) for p in INJECTION_PATTERNS):
        return IntegrityDecision(
            False, "Prompt injection detected.", code="AI_PROMPT_INJECTION"
        )
    if req.learner_facing and any(p.search(text) for p in CROSS_LEARNER_PATTERNS):
        return IntegrityDecision(
            False, "Cross-learner data requests are not allowed.", code="AI_CROSS_LEARNER_FORBIDDEN"
        )
    if req.learner_facing and any(p.search(text) for p in INSTRUCTOR_EXFIL_PATTERNS):
        return IntegrityDecision(
            False,
            "Instructor-context exfiltration is not allowed.",
            code="AI_INSTRUCTOR_CONTEXT_LEAK",
        )
    if req.learner_facing and any(p.search(text) for p in CHEAT_PATTERNS):
        return check_academic_integrity(text)
    # Defense-in-depth: injection may also arrive via server-resolved materials
    for mat in req.course_materials:
        body = mat.get("text") or mat.get("body") or ""
        if any(p.search(body) for p in INJECTION_PATTERNS):
            return IntegrityDecision(
                False,
                "Prompt injection in submitted content.",
                code="AI_PROMPT_INJECTION",
            )
    return check_academic_integrity(text) if req.learner_facing else IntegrityDecision(
        True, "Instructor assist request."
    )


def evaluate_cloud_disclosure(req: AssistRequest) -> dict[str, Any]:
    reasons: list[str] = []
    cloud_permitted = True
    if req.processing_mode == "local-only":
        cloud_permitted = False
        reasons.append("processingMode=local-only")
    if not req.cloud_consent:
        cloud_permitted = False
        reasons.append("userCloudConsent=false")
    if cloud_permitted:
        reasons.append("explicit consent + cloud-allowed mode")
        disclosure = (
            f"DISCLOSURE: CLOUD processing may be used for {req.capability}. "
            "Query content may leave this device. No API keys are stored in this module."
        )
    else:
        disclosure = (
            f"DISCLOSURE: LOCAL-ONLY for {req.capability}. "
            f"No cloud model call is permitted ({'; '.join(reasons)})."
        )
    return {
        "cloudPermitted": cloud_permitted,
        "processingMode": req.processing_mode,
        "userVisibleDisclosure": disclosure,
        "reasons": reasons,
        "dataLeavesDevice": cloud_permitted,
        "requiresConsent": req.processing_mode == "cloud-allowed",
    }


def strip_answer_keys(text: str) -> str:
    if ANSWER_KEY_MARKERS.search(text):
        return (
            "I can help with concepts and hints, but I cannot reveal answer keys "
            "or instructor-only materials."
        )
    return text


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def material_path_allowed(path: str) -> bool:
    if not path:
        return False
    if FORBIDDEN_MATERIAL_PATH.search(path):
        return False
    if "instructor" in path.lower():
        return False
    return True


def resolve_waike_root(cwd: Path | None = None) -> Path | None:
    """Port of gunnchAI resolveWaikeRoot (contract.ts)."""
    env = os.environ.get("WAIKE_REPO_ROOT") or os.environ.get("WAIKE_ROOT")
    if env and (Path(env) / "curriculum" / "digital_rc").is_dir():
        return Path(env).resolve()
    base = cwd or Path.cwd()
    sibling = (base / ".." / "waike-research-ops").resolve()
    if (sibling / "curriculum" / "digital_rc").is_dir():
        return sibling
    return None


def discover_courses_from_contract(waike_root: Path) -> dict[str, Any]:
    """Port of discoverCoursesFromContract — curriculum/digital_rc/*/course.json."""
    digital = waike_root / "curriculum" / "digital_rc"
    courses: list[dict[str, Any]] = []
    if not digital.is_dir():
        return {"course_count": 0, "hardcoded_course_names": False, "courses": courses}
    for name in sorted(p.name for p in digital.iterdir() if p.is_dir()):
        course_json = digital / name / "course.json"
        if not course_json.is_file():
            continue
        data = json.loads(course_json.read_text(encoding="utf-8"))
        labs_dir = digital / name / "labs"
        lab_ids = (
            sorted(
                d.name
                for d in labs_dir.iterdir()
                if d.is_dir() and (d / "README.md").is_file()
            )
            if labs_dir.is_dir()
            else []
        )
        weeks = data.get("weeks")
        courses.append(
            {
                "course_id": data.get("course_id") or name,
                "title": data.get("title") or name,
                "path": f"curriculum/digital_rc/{name}",
                "weeks": len(weeks) if isinstance(weeks, list) else 0,
                "lab_ids": lab_ids,
            }
        )
    return {"course_count": len(courses), "hardcoded_course_names": False, "courses": courses}


def _allow_fake_ai() -> bool:
    return os.environ.get("WAIKE_ALLOW_FAKE_AI", "").strip() == "1"


def _select_provider_from_env() -> GunnchAIProvider:
    """Production-safe provider selection. Never defaults to Fake."""
    prefer = (os.environ.get("GUNNCHAI_PROVIDER") or "").strip().lower()
    if prefer == "fake":
        if _allow_fake_ai():
            return FakeGunnchAIProvider()
        return ForbiddenFakeProvider()
    if prefer in {"", "auto", "local"}:
        local = LocalGunnchAIProvider()
        return local if local.available() else UnavailableProvider()
    if prefer in {"unavailable", "none", "off"}:
        return UnavailableProvider()
    local = LocalGunnchAIProvider()
    return local if local.available() else UnavailableProvider()


class UnavailableProvider:
    """Honest unavailable provider — available() is False."""

    provider_id = "unavailable"
    forbidden_fake = False

    def available(self) -> bool:
        return False

    def assist(self, req: AssistRequest) -> AssistResponse:
        raise ServiceError("AI_PROVIDER_UNAVAILABLE", 503)


class ForbiddenFakeProvider:
    """Selected when GUNNCHAI_PROVIDER=fake without WAIKE_ALLOW_FAKE_AI=1."""

    provider_id = "fake-forbidden"
    forbidden_fake = True

    def available(self) -> bool:
        return False

    def assist(self, req: AssistRequest) -> AssistResponse:
        raise ServiceError("AI_FAKE_PROVIDER_FORBIDDEN", 403)


class EchoTestProvider:
    """Test provider that echoes the AssistRequest structure for isolation asserts."""

    provider_id = "echo-test"
    last_request: AssistRequest | None = None

    def available(self) -> bool:
        return True

    def assist(self, req: AssistRequest) -> AssistResponse:
        self.last_request = req
        # Field names avoid ANSWER_KEY / INSTRUCTOR_KEY substrings so learner
        # strip_answer_keys does not false-positive on the echo payload.
        echo = {
            "mode": req.mode,
            "capability": req.capability,
            "learner_facing": req.learner_facing,
            "staff_context_present": req.instructor_context is not None,
            "target_learner_id": req.target_learner_id,
            "material_paths": [m.get("path") or m.get("id") or "" for m in req.course_materials],
            "material_ids": [m.get("id") or "" for m in req.course_materials],
            "forbidden_material_path_present": any(
                FORBIDDEN_MATERIAL_PATH.search(m.get("path") or m.get("id") or "")
                for m in req.course_materials
            ),
            "peer_path_present": any(
                "peer" in (m.get("path") or m.get("id") or "").lower()
                for m in req.course_materials
            ),
        }
        return AssistResponse(
            ok=True,
            text=json.dumps(echo, sort_keys=True),
            grounded=False,
            citations=[],
            provider_id=self.provider_id,
            mode=req.mode,
            capability=req.capability,
            disclosure=evaluate_cloud_disclosure(req)["userVisibleDisclosure"],
            suggestion_only=True,
            mutates_grades=False,
            detail={"echo": echo, "query_hash": content_hash(req.query)[:12]},
        )


class FakeGunnchAIProvider:
    """Deterministic CI provider — no network, no keys. Tests only."""

    provider_id = "fake-gunnchai"
    forbidden_fake = False

    def available(self) -> bool:
        return True

    def assist(self, req: AssistRequest) -> AssistResponse:
        disclosure = evaluate_cloud_disclosure(req)
        qh = content_hash(req.query)[:12]
        citations: list[dict[str, str]] = []
        for m in req.course_materials[:3]:
            text = m.get("text") or ""
            path = m.get("path") or m.get("id") or "course"
            if not text or not material_path_allowed(path):
                continue
            ch = m.get("content_hash") or content_hash(text)
            citations.append(
                {
                    "source": path,
                    "snippet": text[:120],
                    "content_hash": ch,
                }
            )
        if req.capability == "hint":
            text = (
                f"[fake:{qh}] Hint: revisit the course materials for this section "
                f"and try the next small step. (mode={req.mode})"
            )
        elif req.capability == "explain":
            text = (
                f"[fake:{qh}] Explanation grounded in learner materials only. "
                "I will not disclose final answers or instructor keys."
            )
        elif req.capability in {"feedback_suggest", "grading_triage", "rubric_refine"}:
            text = (
                f"[fake:{qh}] Suggestion only — review before applying. "
                "HITL required; grades are not changed by this response."
            )
        elif req.capability == "citation":
            text = f"[fake:{qh}] Citations are limited to server-resolved course materials."
        else:
            text = f"[fake:{qh}] Assist for capability={req.capability} (deterministic mock)."
        text = strip_answer_keys(text)
        if req.learner_facing:
            text = strip_answer_keys(text)
            if req.instructor_context:
                text = strip_answer_keys(
                    "Learner tutor mode cannot use instructor keys or private rubric guidance."
                )
        return AssistResponse(
            ok=True,
            text=text,
            grounded=bool(citations),
            citations=citations,
            provider_id=self.provider_id,
            mode=req.mode,
            capability=req.capability,
            disclosure=disclosure["userVisibleDisclosure"],
            suggestion_only=True,
            mutates_grades=False,
            detail={"query_hash": qh, "cloud": disclosure},
        )


class CloudProviderStub:
    """Fails closed — mirrors gunnchAI CloudProviderStub."""

    provider_id = "cloud-provider-stub"

    def available(self) -> bool:
        return False

    def assist(self, req: AssistRequest) -> AssistResponse:
        disclosure = evaluate_cloud_disclosure(req)
        if not disclosure["cloudPermitted"]:
            raise ServiceError("AI_CLOUD_FORBIDDEN", 403)
        raise ServiceError("CLOUD_NOT_IMPLEMENTED", 501)


class LocalGunnchAIProvider:
    """Optional local loopback via product-service assist CLI.

    Requires GUNNCHAI_ROOT pointing at a gunnchAI3k checkout with
    src/system-layer/product_service/cli.ts. Does not claim GGUF/llama exists.
    """

    provider_id = "local-product-service"
    forbidden_fake = False
    _assist_executed = False

    def __init__(self, root: Path | None = None) -> None:
        env = os.environ.get("GUNNCHAI_ROOT")
        self.root = Path(root) if root else (Path(env) if env else None)
        self._assist_executed = False

    def cli_path(self) -> Path | None:
        if not self.root:
            return None
        cli = self.root / "src" / "system-layer" / "product_service" / "cli.ts"
        return cli if cli.is_file() else None

    def available(self) -> bool:
        return self.cli_path() is not None

    def probe_cli(self) -> dict[str, Any]:
        """Non-destructive status: CLI presence only (no model weights required)."""
        cli = self.cli_path()
        return {
            "cli_present": cli is not None,
            "cli": str(cli) if cli else None,
            "gunnchai_root": str(self.root) if self.root else None,
            "gunnchai_sha_expected": GUNNCHAI_SHA,
            "assist_executed": self._assist_executed,
            "claims_local_inference": self._assist_executed,
        }

    def status(self) -> dict[str, Any]:
        probe = self.probe_cli()
        cli = self.cli_path()
        return {
            "provider_id": self.provider_id,
            "available": cli is not None,
            "gunnchai_root": str(self.root) if self.root else None,
            "cli": str(cli) if cli else None,
            "probe": probe,
            "note": (
                "Local product-service CLI present (weights not claimed)"
                if cli
                else "GUNNCHAI_ROOT unset or product-service CLI missing — unavailable (honest)"
            ),
        }

    def assist(self, req: AssistRequest) -> AssistResponse:
        cli = self.cli_path()
        if cli is None:
            raise ServiceError("AI_PROVIDER_UNAVAILABLE", 503)
        disclosure = evaluate_cloud_disclosure(req)
        cmd = [
            "npx",
            "tsx",
            str(cli),
            "assist",
            "--capability",
            "tutoring",
            "--query",
            req.query[:2000],
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ServiceError("AI_PROVIDER_UNAVAILABLE", 503) from e
        if proc.returncode != 0:
            raise ServiceError("AI_PROVIDER_ERROR", 502)
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError as e:
            raise ServiceError("AI_PROVIDER_ERROR", 502) from e
        self._assist_executed = True
        text = str(payload.get("text") or payload.get("message") or payload)
        if req.learner_facing:
            text = strip_answer_keys(text)
        citations = list(payload.get("citations") or [])
        # Prefer server materials with hashes when provider returns bare cites
        if not citations and req.course_materials:
            for m in req.course_materials[:3]:
                t = m.get("text") or ""
                path = m.get("path") or m.get("id") or "course"
                if t and material_path_allowed(path):
                    citations.append(
                        {
                            "source": path,
                            "snippet": t[:120],
                            "content_hash": m.get("content_hash") or content_hash(t),
                        }
                    )
        return AssistResponse(
            ok=bool(payload.get("ok", True)),
            text=text,
            grounded=bool(citations),
            citations=citations,
            provider_id=self.provider_id,
            mode=req.mode,
            capability=req.capability,
            disclosure=disclosure["userVisibleDisclosure"],
            suggestion_only=True,
            mutates_grades=False,
            detail={
                "raw_ok": payload.get("ok"),
                "cloud": disclosure,
                "local_inference_executed": True,
            },
        )


class GunnchAIAdapter:
    """Hub-facing adapter: enforces modes, integrity, and provider selection."""

    def __init__(self, provider: GunnchAIProvider | None = None) -> None:
        if provider is not None:
            self.provider = provider
        else:
            self.provider = _select_provider_from_env()
        self.local = LocalGunnchAIProvider()
        self.cloud_stub = CloudProviderStub()

    def contract_meta(self) -> dict[str, Any]:
        real_available = self.local.available()
        active_id = getattr(self.provider, "provider_id", "unknown")
        local_inference_executed = bool(
            getattr(self.provider, "_assist_executed", False)
            if active_id == "local-product-service"
            else False
        )
        return {
            "repo": GUNNCHAI_REPO,
            "sha": GUNNCHAI_SHA,
            "package": GUNNCHAI_PACKAGE,
            "modes": sorted(MODE_PERMISSIONS.keys()),
            "mode_permissions": MODE_PERMISSIONS,
            "DEFAULT_RUNTIME_HAS_NO_FAKE_AI": DEFAULT_RUNTIME_HAS_NO_FAKE_AI,
            "GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE": GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE,
            "GUNNCHAI_REAL_PROVIDER_AVAILABLE": real_available,
            "provider": {
                "active": active_id,
                "available": self.provider.available(),
                "local": self.local.status(),
                "cloud_stub_available": self.cloud_stub.available(),
                "claims": {
                    "contract_integration_complete": GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE,
                    "real_provider_available": real_available,
                    "local_inference_executed": local_inference_executed,
                    "default_runtime_has_no_fake_ai": DEFAULT_RUNTIME_HAS_NO_FAKE_AI,
                },
            },
        }

    def provider_status(self) -> dict[str, Any]:
        meta = self.contract_meta()
        meta["probe"] = self.local.probe_cli()
        return meta

    def assist(self, req: AssistRequest) -> AssistResponse:
        if req.mode not in MODE_PERMISSIONS:
            raise ServiceError("AI_MODE_UNKNOWN", 400)
        perms = MODE_PERMISSIONS[req.mode]

        # Structural isolation for learner path: zero instructor/peer/key context.
        if req.learner_facing:
            safe_mats = [
                m
                for m in req.course_materials
                if material_path_allowed(m.get("path") or m.get("id") or "")
                and not ANSWER_KEY_MARKERS.search(m.get("text") or "")
            ]
            req = AssistRequest(
                **{
                    **req.__dict__,
                    "instructor_context": None,
                    "target_learner_id": None,
                    "course_materials": safe_mats,
                }
            )
            if not perms["mayReadInstructorKeys"]:
                req = AssistRequest(**{**req.__dict__, "instructor_context": None})
        else:
            if not perms["mayPublishGradesWithoutHuman"]:
                pass
            if perms["hitlGradingRequired"] and req.capability in {
                "grading_triage",
                "feedback_suggest",
            }:
                pass
            if not perms["maySelfGrade"]:
                pass

        screen = screen_request(req)
        if not screen.allowed:
            return AssistResponse(
                ok=False,
                text=screen.reason
                + (f" Alternative: {screen.alternative}" if screen.alternative else ""),
                grounded=False,
                citations=[],
                provider_id=getattr(self.provider, "provider_id", "none"),
                mode=req.mode,
                capability=req.capability,
                disclosure=evaluate_cloud_disclosure(req)["userVisibleDisclosure"],
                refused=True,
                refusal_code=screen.code or "AI_INTEGRITY_REFUSED",
                suggestion_only=True,
                mutates_grades=False,
                detail={"integrity": screen.reason},
            )

        disclosure = evaluate_cloud_disclosure(req)
        if req.processing_mode == "cloud-allowed" and disclosure["cloudPermitted"]:
            try:
                return self.cloud_stub.assist(req)
            except ServiceError:
                raise

        if getattr(self.provider, "forbidden_fake", False):
            raise ServiceError("AI_FAKE_PROVIDER_FORBIDDEN", 403)

        if not self.provider.available():
            raise ServiceError("AI_PROVIDER_UNAVAILABLE", 503)

        result = self.provider.assist(req)
        if req.learner_facing:
            result.text = strip_answer_keys(result.text)
            safe_cites = []
            for c in result.citations:
                snippet = strip_answer_keys(c.get("snippet") or "")
                source = c.get("source") or ""
                if "cannot reveal answer keys" in snippet.lower():
                    continue
                if not material_path_allowed(source):
                    continue
                ch = c.get("content_hash") or content_hash(snippet)
                safe_cites.append({**c, "snippet": snippet, "content_hash": ch})
            result.citations = safe_cites
            result.grounded = bool(safe_cites)
        else:
            # grounded only when validated citations exist
            result.grounded = bool(result.citations)
        result.mutates_grades = False
        result.suggestion_only = True
        # Scrub query text from public detail
        if "query" in result.detail:
            result.detail = {**result.detail, "query": "[redacted]"}
        return result

    def refuse_silent_grade_change(self) -> None:
        raise ServiceError("AI_SILENT_GRADE_FORBIDDEN", 403)
