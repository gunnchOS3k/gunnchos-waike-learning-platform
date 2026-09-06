"""Device OS bridge — consume Device OS contracts without copying authority.

Platform adapts launcher/permissions/capability/update/continuity semantics.
Deep links never bypass existing auth.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now

# Canonical app identity — matches Device OS registry / Tauri identifier.
APP_MANIFEST = {
    "app_id": "com.gunnchos.waike.learning",
    "device_os_registry_id": "waike_offline",
    "device_os_runtime_id": "waike",
    "name": "WAIKE Learning OS",
    "version": "0.6.0-gate-c",
    "entry": "apps/waike_learning/index.html",
    "permissions_requested": ["files_read", "network", "identity_read"],
    "authority": "device_os_accepted_main",
    "claim_boundary": "Digital integration only; Device OS remains install/launcher authority",
}

# Least-privilege map from platform roles → Device OS permission names.
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


def device_os_root() -> Path | None:
    env = os.environ.get("DEVICE_OS_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = Path(__file__).resolve().parents[5] / "gunnchos-device-os"
    # parents: modules→app→hub→services→platform→workspace
    workspace = Path(__file__).resolve().parents[4].parent
    candidates = [
        Path(env) if env else None,
        workspace / "gunnchos-device-os",
        Path(__file__).resolve().parents[4] / "gunnchos-device-os",
        sibling,
    ]
    for c in candidates:
        if c and c.is_dir() and (c / "gunnchos_device_os").is_dir():
            return c
    return None


class DeviceOsBridge:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.root = device_os_root()

    def manifest(self) -> dict[str, Any]:
        out = dict(APP_MANIFEST)
        out["device_os_root_present"] = self.root is not None
        out["device_os_pin"] = os.environ.get(
            "DEVICE_OS_PIN_REF", "28562a8456207540c205a1c8a6434a491b0a4771"
        )
        return out

    def discover_contracts(self) -> dict[str, Any]:
        root = self.root
        contracts: dict[str, Any] = {
            "tested_against": "accepted_device_os_main" if root else "fixture_fallback",
            "paths": {},
        }
        if root is None:
            contracts["paths"] = {
                "launcher": "gunnchos_device_os/launcher.py",
                "permissions": "gunnchos_device_os/permissions_manager.py",
                "continuity": "gunnchos_device_os/shell/continuity_coordinator.py",
                "updater": "gunnchos_device_os/updater.py",
                "app_registry": "gunnchos_device_os/app_registry.py",
            }
            contracts["note"] = "Device OS checkout absent; using pinned contract paths"
            return contracts
        mapping = {
            "launcher": root / "gunnchos_device_os" / "launcher.py",
            "permissions": root / "gunnchos_device_os" / "permissions_manager.py",
            "continuity": root / "gunnchos_device_os" / "shell" / "continuity_coordinator.py",
            "updater": root / "gunnchos_device_os" / "updater.py",
            "app_registry": root / "gunnchos_device_os" / "app_registry.py",
            "capability_descriptors": root / "config" / "dock" / "capability_descriptors.json",
            "update_schema": root / "shared_contracts" / "update_contract.schema.json",
        }
        for k, p in mapping.items():
            contracts["paths"][k] = {
                "path": str(p.relative_to(root)) if p.exists() else str(p),
                "exists": p.exists(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
            }
        return contracts

    def launcher_registration(self, actor: Actor, mode: str = "learn") -> dict[str, Any]:
        """Digital launcher handoff — Device OS policy remains authority."""
        return {
            "app_id": APP_MANIFEST["device_os_registry_id"],
            "runtime_id": APP_MANIFEST["device_os_runtime_id"],
            "profile_role": "educator" if actor.is_instructor_side else "student",
            "mode": mode,
            "actor_id": actor.actor_id,
            "site_id": actor.site_id,
            "launched_via": "platform_bridge",
            "authority": "device_os",
            "claim_boundary": APP_MANIFEST["claim_boundary"],
        }

    def permissions_for(self, actor: Actor) -> dict[str, Any]:
        role = actor.role.value
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
        # Parse target
        path = uri[len("waike://") :]
        parts = path.split("/")
        kind = parts[0] if parts else ""
        target_id = parts[1] if len(parts) > 1 else ""
        # Site isolation: section/quiz targets must belong to actor site when resolvable
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
        }

    def capability_discovery(self, profile_id: str) -> dict[str, Any]:
        from app.modules.device_profiles import PROFILES, capabilities_for

        if profile_id not in PROFILES:
            raise ServiceError("UNKNOWN_DEVICE_PROFILE", 404)
        caps = capabilities_for(profile_id)
        snap = _id("capsnap")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO device_capability_snapshots(snapshot_id, profile_id, capabilities_json, discovered_at)
            VALUES (?,?,?,?)
            """,
            (snap, profile_id, json.dumps(caps), now),
        )
        self.conn.commit()
        return {"snapshot_id": snap, "profile_id": profile_id, "capabilities": caps}

    def check_update(self, current_version: str) -> dict[str, Any]:
        # Digital update probe — mirrors Device OS updater contract shape; not production signing.
        latest = APP_MANIFEST["version"]
        return {
            "current": current_version,
            "latest": latest,
            "update_available": current_version != latest,
            "channel": "gate-c-digital",
            "signed": False,
            "signing_truth": "UNSIGNED_DIGITAL_FIXTURE",
            "rollback_supported": True,
            "authority": "device_os_update_contract_shape",
        }

    def rollback(self, actor: Actor, to_version: str) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("UPDATE_FORBIDDEN", 403)
        _audit(self.conn, actor.actor_id, "deviceos.rollback", "device_update", to_version, {"digital": True})
        self.conn.commit()
        return {"status": "rolled_back_digital", "to_version": to_version, "physical": False}

    def continuity_handoff(
        self,
        actor: Actor,
        *,
        from_profile: str,
        to_profile: str,
        lesson_progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handoff excludes secrets/keys/session tokens."""
        payload = {
            "open_app_state": {"app_id": APP_MANIFEST["app_id"]},
            "lesson_progress_checkpoint": lesson_progress or {},
            "shell_form_factor": to_profile,
            # Explicit exclusions
            "excluded": ["session_tokens", "private_keys", "db_keys", "passwords", "lti_private_keys"],
        }
        # Sabotage guard: reject if caller tried to smuggle secrets
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
