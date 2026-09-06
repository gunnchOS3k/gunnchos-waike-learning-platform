"""Device OS bridge — import and call real Device OS modules when present.

Platform adapts launcher/permissions/capability/update/continuity semantics.
Deep links never bypass existing auth.

When DEVICE_OS_ROOT is set (Gate C CI), this bridge loads:
  - gunnchos_device_os.app_registry
  - gunnchos_device_os.learning_os_launcher / launcher
  - gunnchos_device_os.permissions_manager
  - gunnchos_device_os.shell.continuity_coordinator
  - gunnchos_device_os.updater / rollback
  - config/dock/capability_descriptors.json

Device Quartet profiles remain fixtures only (labeled).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now

# Canonical app identity — matches Device OS registry / Tauri identifier.
APP_MANIFEST = {
    "app_id": "com.gunnchos.waike.learning",
    "device_os_registry_id": "waike_learning_os",
    "device_os_compatibility_alias": "waike_offline",
    "device_os_runtime_id": "waike",
    "device_os_sdk_app_id": "gunnchos.waike_learning",
    "name": "WAIKE Learning OS",
    "version": "0.6.0-gate-c",
    "entry": "apps/client (Tauri Learning OS)",
    "companion_seed_entry": "apps/waike_learning/index.html",
    "launcher_wrapper_relationship": "thin_launcher_companion",
    "permissions_requested": ["files_read", "network", "identity_read"],
    "authority": "device_os_accepted_main",
    "claim_boundary": (
        "Digital integration only; Device OS remains install/launcher authority. "
        "Seed HTML is companion/discovery only — Learning OS Tauri app is SoR."
    ),
}

DEVICE_OS_PIN_DEFAULT = "67cf98255e41d953e56eb142af063940e05c8dbb"

# Least-privilege map from platform roles → Device OS permission names (fixture fallback).
ROLE_PERMISSIONS = {
    "learner": ["files_read", "network", "identity_read", "notifications"],
    "instructor": [
        "files_read",
        "files_write",
        "network",
        "identity_read",
        "notifications",
        "camera",
        "microphone",
    ],
    "grader": ["files_read", "network", "identity_read", "notifications"],
    "site_admin": [
        "files_read",
        "files_write",
        "network",
        "identity_read",
        "notifications",
        "camera",
        "microphone",
        "sensors",
    ],
}

ALLOWED_DEEP_LINK_PREFIXES = (
    "waike://learn/",
    "waike://section/",
    "waike://quiz/",
    "waike://assignment/",
    "waike://sync/",
    "waike://device/profile/",
)

_DEVICE_OS_IMPORTS: dict[str, Any] | None = None


def device_os_root() -> Path | None:
    env = os.environ.get("DEVICE_OS_ROOT")
    workspace = Path(__file__).resolve().parents[4].parent
    candidates = [
        Path(env) if env else None,
        workspace / "gunnchos-device-os",
        Path(__file__).resolve().parents[4] / "gunnchos-device-os",
        Path(__file__).resolve().parents[5] / "gunnchos-device-os",
    ]
    for c in candidates:
        if c and c.is_dir() and (c / "gunnchos_device_os").is_dir():
            return c
    return None


def _load_device_os() -> dict[str, Any] | None:
    """Import real Device OS modules from DEVICE_OS_ROOT (sys.path insert)."""
    global _DEVICE_OS_IMPORTS
    if _DEVICE_OS_IMPORTS is not None:
        return _DEVICE_OS_IMPORTS if _DEVICE_OS_IMPORTS else None

    root = device_os_root()
    if root is None:
        _DEVICE_OS_IMPORTS = {}
        return None

    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    try:
        from gunnchos_device_os import app_registry as dos_registry
        from gunnchos_device_os import launcher as dos_launcher
        from gunnchos_device_os import learning_os_launcher as dos_los
        from gunnchos_device_os import rollback as dos_rollback
        from gunnchos_device_os import updater as dos_updater
        from gunnchos_device_os.permissions_manager import (
            Permission,
            PermissionsManager,
        )
        from gunnchos_device_os.shell.continuity_coordinator import ContinuityCoordinator

        _DEVICE_OS_IMPORTS = {
            "root": root,
            "app_registry": dos_registry,
            "launcher": dos_launcher,
            "learning_os_launcher": dos_los,
            "PermissionsManager": PermissionsManager,
            "Permission": Permission,
            "ContinuityCoordinator": ContinuityCoordinator,
            "updater": dos_updater,
            "rollback": dos_rollback,
        }
        return _DEVICE_OS_IMPORTS
    except Exception as exc:  # noqa: BLE001 — surface import failure honestly
        _DEVICE_OS_IMPORTS = {"error": str(exc), "root": root}
        return None


def require_device_os() -> dict[str, Any]:
    """Gate C path: fail if Device OS modules cannot be loaded."""
    mods = _load_device_os()
    if not mods or "app_registry" not in mods:
        err = ""
        if isinstance(_DEVICE_OS_IMPORTS, dict):
            err = str(_DEVICE_OS_IMPORTS.get("error") or "")
        raise ServiceError(
            "DEVICE_OS_ROOT_REQUIRED",
            503,
            detail={"error": err or "Device OS modules unavailable"},
        )
    return mods


class DeviceOsBridge:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @property
    def root(self) -> Path | None:
        return device_os_root()

    @property
    def _dos(self) -> dict[str, Any] | None:
        return _load_device_os()

    @property
    def device_os_live(self) -> bool:
        mods = self._dos
        return bool(mods and "app_registry" in mods)

    def manifest(self) -> dict[str, Any]:
        out = dict(APP_MANIFEST)
        out["device_os_root_present"] = self.root is not None
        out["device_os_live_imports"] = self.device_os_live
        out["device_os_pin"] = os.environ.get("DEVICE_OS_PIN_REF", DEVICE_OS_PIN_DEFAULT)
        if self.device_os_live:
            reg = self._dos["app_registry"]
            app = reg.get_app(reg.LEARNING_OS_REGISTRY_ID)
            out["device_os_registry_name"] = app.get("name")
            out["device_os_relationship"] = app.get("relationship")
            out["system_of_record"] = app.get("system_of_record")
        return out

    def discover_contracts(self) -> dict[str, Any]:
        root = self.root
        contracts: dict[str, Any] = {
            "tested_against": (
                "device_os_live_modules" if self.device_os_live else "accepted_device_os_pin"
            ),
            "device_os_live_imports": self.device_os_live,
            "paths": {},
        }
        mapping_names = {
            "launcher": "gunnchos_device_os/launcher.py",
            "learning_os_launcher": "gunnchos_device_os/learning_os_launcher.py",
            "permissions": "gunnchos_device_os/permissions_manager.py",
            "continuity": "gunnchos_device_os/shell/continuity_coordinator.py",
            "updater": "gunnchos_device_os/updater.py",
            "app_registry": "gunnchos_device_os/app_registry.py",
            "capability_descriptors": "config/dock/capability_descriptors.json",
            "update_schema": "shared_contracts/update_contract.schema.json",
            "integration_contract": "contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json",
        }
        if root is None:
            contracts["paths"] = {k: v for k, v in mapping_names.items()}
            contracts["note"] = "Device OS checkout absent; using pinned contract paths"
            return contracts

        for k, rel in mapping_names.items():
            if k == "integration_contract":
                # Platform-owned contract lives in this repo
                p = (
                    Path(__file__).resolve().parents[4]
                    / "contracts"
                    / "deviceos"
                    / "WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json"
                )
            else:
                p = root / rel
            contracts["paths"][k] = {
                "path": rel if k != "integration_contract" else str(p),
                "exists": p.exists(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
            }

        if self.device_os_live:
            reg = self._dos["app_registry"]
            contracts["registry_sample"] = {
                "canonical": reg.LEARNING_OS_REGISTRY_ID,
                "apps_education": reg.list_apps("education"),
                "alias_resolves_to": reg.resolve_app_id("waike_offline"),
            }
        return contracts

    def launcher_registration(self, actor: Actor, mode: str = "School") -> dict[str, Any]:
        """Digital launcher handoff — calls Device OS thin launcher when live."""
        profile = "educator" if actor.is_instructor_side else "student"
        if self.device_os_live:
            los = self._dos["learning_os_launcher"]
            result = los.launch_learning_os(
                profile,
                mode,
                deep_link="waike://learn/home",
                platform_role=actor.role.value,
                include_companion_seed=True,
            )
            return {
                "app_id": APP_MANIFEST["device_os_registry_id"],
                "runtime_id": APP_MANIFEST["device_os_runtime_id"],
                "profile_role": profile,
                "mode": mode,
                "actor_id": actor.actor_id,
                "site_id": actor.site_id,
                "launched_via": "device_os_learning_os_launcher",
                "authority": "device_os",
                "relationship": result.get("relationship"),
                "system_of_record": result.get("system_of_record"),
                "seed_is_system_of_record": result.get("seed_is_system_of_record", False),
                "handoff": result.get("handoff"),
                "companion_seed": result.get("companion_seed"),
                "device_os_result": {
                    "registered": result.get("registered"),
                    "available": result.get("available"),
                    "handoff_created": result.get("handoff_created"),
                    "launch_attempted": result.get("launch_attempted"),
                    "process_started": result.get("process_started"),
                    "deep_link_delivered": result.get("deep_link_delivered"),
                    "acknowledged": result.get("acknowledged"),
                    "launched": result.get("launched"),
                    "reason": result.get("reason"),
                    "mock": result.get("mock"),
                    "provenance": result.get("provenance"),
                },
                "claim_boundary": APP_MANIFEST["claim_boundary"],
            }

        # Fixture fallback when Device OS checkout missing (non–Gate C local).
        return {
            "app_id": APP_MANIFEST["device_os_registry_id"],
            "runtime_id": APP_MANIFEST["device_os_runtime_id"],
            "profile_role": profile,
            "mode": mode,
            "actor_id": actor.actor_id,
            "site_id": actor.site_id,
            "launched_via": "platform_bridge_fixture",
            "authority": "device_os",
            "relationship": "thin_launcher_companion",
            "seed_is_system_of_record": False,
            "claim_boundary": APP_MANIFEST["claim_boundary"],
        }

    def permissions_for(self, actor: Actor) -> dict[str, Any]:
        role = actor.role.value
        if self.device_os_live:
            los = self._dos["learning_os_launcher"]
            mapped = los.map_permissions_for_platform_role(role)
            # Platform surface still applies least-privilege ROLE_PERMISSIONS filter.
            baseline = list(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["learner"]))
            if role == "site_admin":
                allow = list(mapped["allowlist"])
            else:
                allow = baseline
            denied = [
                p
                for p in [
                    "camera",
                    "microphone",
                    "location",
                    "ai_cloud_export",
                    "screen_capture",
                    "ring_input",
                    "files_write",
                    "sensors",
                ]
                if p not in allow
            ]
            pm = self._dos["PermissionsManager"](role=mapped["device_os_role"])
            sample = pm.request(
                APP_MANIFEST["device_os_sdk_app_id"],
                self._dos["Permission"].FILES_READ,
            )
            return {
                "role": role,
                "device_os_role": mapped["device_os_role"],
                "allowed": allow,
                "denied": denied,
                "model": "least_privilege",
                "authority": "device_os_permissions_manager",
                "device_os_sample_grant": sample,
                "mapping": mapped.get("mapping"),
            }

        allowed = list(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["learner"]))
        return {
            "role": role,
            "allowed": allowed,
            "denied": [
                p
                for p in [
                    "camera",
                    "microphone",
                    "location",
                    "ai_cloud_export",
                    "screen_capture",
                    "ring_input",
                    "files_write",
                    "sensors",
                ]
                if p not in allowed
            ],
            "model": "least_privilege",
            "authority": "device_os_permissions_manager_semantics",
        }

    def resolve_deep_link(self, actor: Actor, uri: str) -> dict[str, Any]:
        """Auth required — deep links never bypass session."""
        if not actor or not actor.actor_id:
            raise ServiceError("DEEP_LINK_AUTH_REQUIRED", 401)
        uri = (uri or "").strip()
        if not any(uri.startswith(p) for p in ALLOWED_DEEP_LINK_PREFIXES):
            raise ServiceError("DEEP_LINK_REJECTED", 400)
        if ".." in uri or "\\" in uri:
            raise ServiceError("DEEP_LINK_REJECTED", 400)

        if self.device_os_live:
            parsed = self._dos["learning_os_launcher"].parse_deep_link(uri)
            if not parsed.get("valid"):
                raise ServiceError("DEEP_LINK_REJECTED", 400)

        path = uri[len("waike://") :]
        parts = path.split("/")
        kind = parts[0] if parts else ""
        target_id = parts[1] if len(parts) > 1 else ""
        if kind == "section" and target_id:
            row = self.conn.execute(
                "SELECT site_id FROM sections WHERE section_id=?", (target_id,)
            ).fetchone()
            if row and row["site_id"] != actor.site_id:
                raise ServiceError("DEEP_LINK_CROSS_SITE", 403)
        return {
            "uri": uri,
            "kind": kind,
            "target_id": target_id,
            "actor_id": actor.actor_id,
            "authorized": True,
            "auth_bypassed": False,
            "device_os_validated": self.device_os_live,
        }

    def capability_discovery(self, profile_id: str) -> dict[str, Any]:
        """Merge Device OS dock capability descriptors with Device Quartet fixtures.

        Device Quartet profiles are FIXTURES ONLY — labeled as such.
        """
        from app.modules.device_profiles import PROFILES, capabilities_for

        if profile_id not in PROFILES:
            raise ServiceError("UNKNOWN_DEVICE_PROFILE", 404)

        caps = capabilities_for(profile_id)
        caps["fixture_label"] = "device_quartet_digital_fixture_only"
        caps["physical_validation"] = "EXTERNAL"

        production_caps: dict[str, Any] | None = None
        if self.root is not None:
            desc = self.root / "config" / "dock" / "capability_descriptors.json"
            if desc.is_file():
                production_caps = json.loads(desc.read_text(encoding="utf-8"))

        snap = _id("capsnap")
        now = _now()
        payload = {
            "fixture_capabilities": caps,
            "production_capability_descriptors": production_caps,
            "source": "device_os_capability_descriptors+quartet_fixtures",
        }
        self.conn.execute(
            """
            INSERT INTO device_capability_snapshots(snapshot_id, profile_id, capabilities_json, discovered_at)
            VALUES (?,?,?,?)
            """,
            (snap, profile_id, json.dumps(payload), now),
        )
        self.conn.commit()
        return {
            "snapshot_id": snap,
            "profile_id": profile_id,
            "capabilities": caps,
            "production_capability_descriptors_loaded": production_caps is not None,
            "fixture_label": "device_quartet_digital_fixture_only",
        }

    def check_update(self, current_version: str) -> dict[str, Any]:
        if self.device_os_live:
            upd = self._dos["learning_os_launcher"].invoke_updater_contract(current_version)
            los = upd["learning_os_updater"]
            return {
                "current": current_version,
                "latest": los.get("latest", APP_MANIFEST["version"]),
                "update_available": los.get("update_available", current_version != APP_MANIFEST["version"]),
                "channel": los.get("channel", "gate-c-digital"),
                "signed": bool(los.get("signed")),
                "signing_truth": upd.get("signing_truth", "UNSIGNED_DIGITAL_FIXTURE"),
                "rollback_supported": bool(upd.get("rollback_supported")),
                "authority": "device_os_updater",
                "device_os_updater": upd.get("device_os_updater"),
                "rollback_probe": upd.get("rollback"),
                "claim_boundary": upd.get("claim_boundary"),
            }

        latest = APP_MANIFEST["version"]
        return {
            "current": current_version,
            "latest": latest,
            "update_available": current_version != latest,
            "channel": "gate-c-digital",
            "signed": False,
            "signing_truth": "UNSIGNED_DIGITAL_FIXTURE",
            "rollback_supported": False,
            "authority": "device_os_update_contract_shape",
            "claim_boundary": "Fixture path only — no package lifecycle prior version.",
        }

    def rollback(self, actor: Actor, to_version: str) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("UPDATE_FORBIDDEN", 403)
        dos_result = None
        if self.device_os_live:
            dos_result = self._dos["rollback"].rollback_to(to_version)
        _audit(
            self.conn,
            actor.actor_id,
            "deviceos.rollback",
            "device_update",
            to_version,
            {"digital": True, "device_os": dos_result},
        )
        self.conn.commit()
        return {
            "status": "rolled_back_digital",
            "to_version": to_version,
            "physical": False,
            "device_os_rollback": dos_result,
        }

    def continuity_handoff(
        self,
        actor: Actor,
        *,
        from_profile: str,
        to_profile: str,
        lesson_progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handoff excludes secrets/keys/session tokens — uses ContinuityCoordinator when live."""
        if self.device_os_live:
            los = self._dos["learning_os_launcher"]
            storage = Path(tempfile.mkdtemp(prefix="waike-platform-continuity-"))
            result = los.continuity_handoff(
                from_profile=from_profile,
                to_profile=to_profile,
                account_id=actor.actor_id,
                session_id=f"site-{actor.site_id}",
                lesson_progress=lesson_progress,
                storage_root=storage,
            )
            if not result.get("ok"):
                raise ServiceError("CONTINUITY_SECRET_REJECTED", 400)
            raw = json.dumps(result.get("payload") or {}, sort_keys=True).encode("utf-8")
            sha = hashlib.sha256(raw).hexdigest()
            hid = _id("handoff")
            now = _now()
            self.conn.execute(
                """
                INSERT INTO continuity_handoffs(
                  handoff_id, from_profile, to_profile, actor_id, site_id,
                  payload_json, payload_sha256, created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (hid, from_profile, to_profile, actor.actor_id, actor.site_id, raw.decode(), sha, now),
            )
            self.conn.commit()
            return {
                "handoff_id": hid,
                "payload_sha256": sha,
                "contains_secrets": False,
                "device_os_checkpoint": result.get("checkpoint"),
                "continuity_owner": result.get("continuity_owner"),
                "claim_boundary": "Local-first digital continuity; not physical device replacement",
            }

        payload = {
            "open_app_state": {"app_id": APP_MANIFEST["app_id"]},
            "lesson_progress_checkpoint": lesson_progress or {},
            "shell_form_factor": to_profile,
            "excluded": ["session_tokens", "private_keys", "db_keys", "passwords", "lti_private_keys"],
        }
        blob = json.dumps(lesson_progress or {})
        for bad in ("password", "private_key", "session_token", "WAIKE_DEV_DB_KEY", "BEGIN PRIVATE"):
            if bad.lower() in blob.lower():
                raise ServiceError("CONTINUITY_SECRET_REJECTED", 400)
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()
        hid = _id("handoff")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO continuity_handoffs(
              handoff_id, from_profile, to_profile, actor_id, site_id,
              payload_json, payload_sha256, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (hid, from_profile, to_profile, actor.actor_id, actor.site_id, raw.decode(), sha, now),
        )
        self.conn.commit()
        return {
            "handoff_id": hid,
            "payload_sha256": sha,
            "contains_secrets": False,
            "claim_boundary": "Local-first digital continuity; not physical device replacement",
        }
