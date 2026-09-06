"""Gate C API routes: interop, Device OS bridge, hardening."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import Actor, require_actor, require_instructor_side, require_site_admin
from app.modules.assessment_lifecycle import ServiceError
from app.modules.backup_restore import BackupService
from app.modules.device_profiles import PROFILES, matrix as profile_matrix, responsive_behavior
from app.modules.deviceos_bridge import DeviceOsBridge
from app.modules.hardening import (
    AdminConsole,
    Observability,
    PackageLifecycle,
    PrivacyService,
    RateLimiter,
)
from app.modules.lti import LtiService
from app.modules.oneroster import OneRosterService
from app.modules.qti import QtiService

router = APIRouter(prefix="/api/v1")


def _http(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.code)


def _oneroster(request: Request) -> OneRosterService:
    return request.app.state.oneroster


def _qti(request: Request) -> QtiService:
    return request.app.state.qti


def _lti(request: Request) -> LtiService:
    return request.app.state.lti


def _deviceos(request: Request) -> DeviceOsBridge:
    return request.app.state.deviceos


def _backup(request: Request) -> BackupService:
    return request.app.state.backup


def _privacy(request: Request) -> PrivacyService:
    return request.app.state.privacy


def _admin(request: Request) -> AdminConsole:
    return request.app.state.admin


def _obs(request: Request) -> Observability:
    return request.app.state.observability


def _packages(request: Request) -> PackageLifecycle:
    return request.app.state.packages


def _limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


class OneRosterImportBody(BaseModel):
    entity_file: str
    csv_text: str
    filename: str = "import.csv"


class QtiImportBody(BaseModel):
    xml_text: str
    section_id: str
    quiz_id: str | None = None


class LtiRegisterBody(BaseModel):
    issuer: str
    client_id: str
    deployment_id: str
    auth_login_url: str
    auth_token_url: str
    jwks_url: str
    target_link_uri: str


class LtiLaunchBody(BaseModel):
    registration_id: str
    id_token: str
    state: str


class DeepLinkBody(BaseModel):
    uri: str


class ContinuityBody(BaseModel):
    from_profile: str
    to_profile: str
    lesson_progress: dict[str, Any] = Field(default_factory=dict)


class PrivacyBody(BaseModel):
    youth_mode: bool = False
    data_minimization: bool = True
    export_allowed: bool = False
    retention_days: int = 365


class PackageBody(BaseModel):
    track_id: str
    package_version: str
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)


@router.get("/interop/oneroster/matrix")
def oneroster_matrix(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _oneroster(request).support_matrix()


@router.post("/interop/oneroster/import")
def oneroster_import(
    body: OneRosterImportBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        _limiter(request).check(f"oneroster:{actor.actor_id}")
        return _oneroster(request).import_csv(
            actor, entity_file=body.entity_file, csv_text=body.csv_text, filename=body.filename
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/interop/oneroster/export/{entity_file}")
def oneroster_export(
    entity_file: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return {"csv": _oneroster(request).export_csv(actor, entity_file)}
    except ServiceError as e:
        raise _http(e) from e


@router.get("/interop/qti/matrix")
def qti_matrix(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _qti(request).support_matrix()


@router.post("/interop/qti/import")
def qti_import(
    body: QtiImportBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return _qti(request).import_item_xml(
            actor, xml_text=body.xml_text, section_id=body.section_id, quiz_id=body.quiz_id
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/interop/qti/export/{item_id}")
def qti_export(
    item_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_instructor_side(actor)
    try:
        return {"xml": _qti(request).export_item_xml(actor, item_id)}
    except ServiceError as e:
        raise _http(e) from e


@router.get("/interop/lti/matrix")
def lti_matrix(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _lti(request).support_matrix()


@router.post("/interop/lti/registrations")
def lti_register(
    body: LtiRegisterBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _lti(request).register(actor, **body.model_dump())
    except ServiceError as e:
        raise _http(e) from e


@router.post("/interop/lti/oidc/init/{registration_id}")
def lti_oidc_init(registration_id: str, request: Request) -> dict[str, Any]:
    try:
        return _lti(request).oidc_login_init(registration_id)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/interop/lti/launch")
def lti_launch(body: LtiLaunchBody, request: Request) -> dict[str, Any]:
    try:
        _limiter(request).check(f"lti-launch:{body.registration_id}")
        return _lti(request).validate_launch(
            registration_id=body.registration_id, id_token=body.id_token, state=body.state
        )
    except ServiceError as e:
        raise _http(e) from e


@router.get("/deviceos/manifest")
def device_manifest(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _deviceos(request).manifest()


@router.get("/deviceos/contracts")
def device_contracts(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _deviceos(request).discover_contracts()


@router.get("/deviceos/launcher")
def device_launcher(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _deviceos(request).launcher_registration(actor)


@router.get("/deviceos/permissions")
def device_permissions(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _deviceos(request).permissions_for(actor)


@router.post("/deviceos/deep-link")
def device_deep_link(
    body: DeepLinkBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _deviceos(request).resolve_deep_link(actor, body.uri)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/deviceos/profiles")
def device_profiles(actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return profile_matrix()


@router.get("/deviceos/profiles/{profile_id}")
def device_profile(
    profile_id: str, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        caps = _deviceos(request).capability_discovery(profile_id)
        caps["responsive"] = responsive_behavior(profile_id)
        caps["profile"] = PROFILES[profile_id]
        return caps
    except ServiceError as e:
        raise _http(e) from e


@router.get("/deviceos/update")
def device_update(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _deviceos(request).check_update(_deviceos(request).manifest()["version"])


@router.post("/deviceos/continuity")
def device_continuity(
    body: ContinuityBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    try:
        return _deviceos(request).continuity_handoff(
            actor,
            from_profile=body.from_profile,
            to_profile=body.to_profile,
            lesson_progress=body.lesson_progress,
        )
    except ServiceError as e:
        raise _http(e) from e


@router.post("/admin/backup")
def admin_backup(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _backup(request).create_backup(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/admin/dashboard")
def admin_dashboard(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _admin(request).dashboard(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.get("/privacy/matrix")
def privacy_matrix(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    return _privacy(request).matrix(actor.site_id)


@router.put("/privacy/controls")
def privacy_controls(
    body: PrivacyBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _privacy(request).upsert(actor, **body.model_dump())
    except ServiceError as e:
        raise _http(e) from e


@router.get("/diagnostics")
def diagnostics(request: Request, actor: Actor = Depends(require_actor)) -> dict[str, Any]:
    try:
        return _obs(request).diagnostics(actor)
    except ServiceError as e:
        raise _http(e) from e


@router.post("/packages/lifecycle")
def package_lifecycle(
    body: PackageBody, request: Request, actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    require_site_admin(actor)
    try:
        return _packages(request).record(
            actor,
            track_id=body.track_id,
            package_version=body.package_version,
            action=body.action,
            detail=body.detail,
        )
    except ServiceError as e:
        raise _http(e) from e
