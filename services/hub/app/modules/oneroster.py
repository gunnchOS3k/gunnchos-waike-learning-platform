"""OneRoster pilot subset: orgs, users, courses, classes, enrollments.

Pilot CSV semantics only — not full OneRoster certification.
Imported identity never bypasses local authorization.
Classes map to real LMS sections; enrollments map to real enrollments with revoke.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from typing import Any

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row, _rows
from app.modules import txn

SUPPORTED_TYPES = ("orgs", "users", "courses", "classes", "enrollments")
ENTITY_MAP = {
    "orgs": "org",
    "users": "user",
    "courses": "course",
    "classes": "class",
    "enrollments": "enrollment",
}

ROLE_MAP = {
    "student": Role.LEARNER,
    "learner": Role.LEARNER,
    "teacher": Role.INSTRUCTOR,
    "instructor": Role.INSTRUCTOR,
    "aide": Role.GRADER,
    "grader": Role.GRADER,
    "administrator": Role.SITE_ADMIN,
    "admin": Role.SITE_ADMIN,
}

# Roles that must never be applied from OneRoster without explicit operator policy.
FORBIDDEN_ESCALATION = {Role.SITE_ADMIN}

MAX_ROWS = 10_000
FORMULA_RE = re.compile(r"^[=+\-@]")
INACTIVE_STATUSES = {"inactive", "tobedeleted", "deleted"}


class OneRosterService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        identity: Any | None = None,
        sections: Any | None = None,
        sync: Any | None = None,
        privacy: Any | None = None,
    ) -> None:
        self.conn = conn
        self.identity = identity
        self.sections = sections
        self.sync = sync
        self.privacy = privacy

    def support_matrix(self) -> dict[str, Any]:
        return {
            "standard": "OneRoster pilot subset",
            "claim": "NOT_FULL_ONEROSTER",
            "supported": {
                "orgs": True,
                "users": True,
                "courses": True,
                "classes": True,
                "enrollments": True,
            },
            "unsupported": [
                "demographics",
                "academicSessions",
                "lineItems",
                "results",
                "resources",
                "full REST sync",
            ],
            "fields": {
                "sourcedId": True,
                "status": True,
                "dateLastModified": True,
                "role_mapping": True,
                "org_relationship": True,
                "course_class_relationship": True,
                "enrollment_relationship": True,
                "local_section_mapping": True,
                "enrollment_revoke": True,
            },
            "auth": "site_admin / operator only; no password import; no auth bypass",
        }

    def _require_operator(self, actor: Actor) -> None:
        if not actor.is_site_admin:
            raise ServiceError("ONEROSTER_FORBIDDEN", 403)

    def _safe_filename(self, name: str) -> str:
        base = name.replace("\\", "/").split("/")[-1]
        if ".." in base or not base:
            raise ServiceError("ONEROSTER_UNSAFE_FILENAME", 400)
        return base[:200]

    def _detect_formula(self, cell: str) -> bool:
        return bool(FORMULA_RE.match((cell or "").lstrip()))

    def import_csv(
        self,
        actor: Actor,
        *,
        entity_file: str,
        csv_text: str,
        filename: str = "import.csv",
    ) -> dict[str, Any]:
        self._require_operator(actor)
        if entity_file not in SUPPORTED_TYPES:
            raise ServiceError("ONEROSTER_UNSUPPORTED_TYPE", 400)
        if self.privacy is not None and hasattr(self.privacy, "assert_import_allowed"):
            # Import itself is operator-only; export gate is separate.
            pass
        safe_name = self._safe_filename(filename)
        raw = csv_text.encode("utf-8", errors="strict")
        if len(raw) > 5_000_000:
            raise ServiceError("ONEROSTER_TOO_LARGE", 400)
        sha = hashlib.sha256(raw).hexdigest()
        try:
            reader = csv.DictReader(io.StringIO(csv_text))
        except csv.Error as e:
            raise ServiceError("ONEROSTER_MALFORMED", 400) from e
        if reader.fieldnames is None:
            raise ServiceError("ONEROSTER_MALFORMED", 400)

        entity_type = ENTITY_MAP[entity_file]
        now = _now()
        validated: list[tuple[dict[str, str], str, str | None]] = []
        rejects: list[dict[str, Any]] = []
        rows_seen = 0

        # Validate-all-rows-before-mutate: parse + validate without writing.
        for row in reader:
            rows_seen += 1
            if rows_seen > MAX_ROWS:
                raise ServiceError("ONEROSTER_ROW_LIMIT", 400)
            try:
                for v in row.values():
                    if isinstance(v, str) and self._detect_formula(v):
                        raise ServiceError("ONEROSTER_FORMULA_INJECTION", 400)
                sourced = (row.get("sourcedId") or "").strip()
                if not sourced:
                    raise ServiceError("ONEROSTER_MISSING_SOURCED_ID", 400)
                status = (row.get("status") or "active").strip().lower()
                if status not in {"active", "inactive", "tobedeleted", "deleted"}:
                    raise ServiceError("ONEROSTER_BAD_STATUS", 400)
                dlm = (row.get("dateLastModified") or "").strip() or None
                self._validate_row(actor, entity_type, sourced, status, row)
                validated.append((row, status, dlm))
            except ServiceError as e:
                rejects.append({"sourcedId": row.get("sourcedId"), "code": e.code})

        if rejects:
            # Rejected row → no partial side effects.
            import_id = _id("orimp")
            report = {
                "entity_file": entity_file,
                "rejects": rejects[:50],
                "rows_seen": rows_seen,
                "atomic": True,
                "mutated": False,
            }
            self.conn.execute(
                """
                INSERT INTO oneroster_imports(
                  import_id, site_id, actor_id, source_filename, source_sha256,
                  created_count, updated_count, rejected_count, report_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    import_id,
                    actor.site_id,
                    actor.actor_id,
                    safe_name,
                    sha,
                    0,
                    0,
                    len(rejects),
                    json.dumps(report),
                    now,
                ),
            )
            self.conn.commit()
            return {
                "import_id": import_id,
                "source_sha256": sha,
                "created": 0,
                "updated": 0,
                "rejected": len(rejects),
                "report": report,
            }

        created = updated = 0
        txn.enter(self.conn, "oneroster_import")
        try:
            for row, status, dlm in validated:
                result = self._apply_row(actor, entity_type, row, now)
                if result == "created":
                    created += 1
                elif result == "updated":
                    updated += 1
            import_id = _id("orimp")
            report = {
                "entity_file": entity_file,
                "rejects": [],
                "rows_seen": rows_seen,
                "atomic": True,
                "mutated": True,
            }
            self.conn.execute(
                """
                INSERT INTO oneroster_imports(
                  import_id, site_id, actor_id, source_filename, source_sha256,
                  created_count, updated_count, rejected_count, report_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    import_id,
                    actor.site_id,
                    actor.actor_id,
                    safe_name,
                    sha,
                    created,
                    updated,
                    0,
                    json.dumps(report),
                    now,
                ),
            )
            _audit(
                self.conn,
                actor.actor_id,
                "oneroster.import",
                "oneroster_import",
                import_id,
                {
                    "filename_hash": sha,
                    "created": created,
                    "updated": updated,
                    "rejected": 0,
                },
            )
            txn.release(self.conn, "oneroster_import")
            txn.commit(self.conn)
        except Exception:
            txn.rollback(self.conn, "oneroster_import")
            raise

        return {
            "import_id": import_id,
            "source_sha256": sha,
            "created": created,
            "updated": updated,
            "rejected": 0,
            "report": report,
        }

    def _validate_row(
        self,
        actor: Actor,
        entity_type: str,
        sourced: str,
        status: str,
        row: dict[str, str],
    ) -> None:
        if entity_type == "user":
            role_raw = (row.get("role") or row.get("roles") or "learner").split(",")[0].strip().lower()
            mapped = ROLE_MAP.get(role_raw)
            if mapped is None:
                raise ServiceError("ONEROSTER_ROLE_MISMATCH", 400)
            if mapped in FORBIDDEN_ESCALATION:
                raise ServiceError("ONEROSTER_ROLE_ESCALATION", 400)
            if "password" in {k.lower() for k in row}:
                raise ServiceError("ONEROSTER_PASSWORD_FORBIDDEN", 400)
            org = (row.get("orgSourcedId") or row.get("org") or "").strip()
            if org:
                other = _row(
                    self.conn,
                    """
                    SELECT site_id FROM oneroster_entities
                    WHERE entity_type='org' AND sourced_id=? AND site_id!=?
                    """,
                    (org, actor.site_id),
                )
                if other is not None:
                    raise ServiceError("ONEROSTER_CROSS_SITE_COLLISION", 400)
            return
        if entity_type == "class":
            course = (row.get("courseSourcedId") or row.get("course") or "").strip()
            if course and status == "active":
                cref = _row(
                    self.conn,
                    "SELECT entity_id FROM oneroster_entities WHERE site_id=? AND entity_type='course' AND sourced_id=?",
                    (actor.site_id, course),
                )
                if cref is None:
                    raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
            return
        if entity_type == "enrollment":
            user_sid = (row.get("userSourcedId") or row.get("user") or "").strip()
            class_sid = (row.get("classSourcedId") or row.get("class") or "").strip()
            if not user_sid or not class_sid:
                raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
            u = _row(
                self.conn,
                "SELECT entity_id, local_ref FROM oneroster_entities WHERE site_id=? AND entity_type='user' AND sourced_id=?",
                (actor.site_id, user_sid),
            )
            c = _row(
                self.conn,
                "SELECT entity_id, local_ref FROM oneroster_entities WHERE site_id=? AND entity_type='class' AND sourced_id=?",
                (actor.site_id, class_sid),
            )
            if u is None or c is None:
                raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
            return

    def _apply_row(
        self, actor: Actor, entity_type: str, row: dict[str, str], now: str
    ) -> str:
        sourced = (row.get("sourcedId") or "").strip()
        status = (row.get("status") or "active").strip().lower()
        dlm = (row.get("dateLastModified") or "").strip() or None

        if entity_type == "user":
            return self._apply_user(actor, sourced, status, dlm, row, now)
        if entity_type == "enrollment":
            return self._apply_enrollment(actor, sourced, status, dlm, row, now)
        if entity_type == "class":
            return self._apply_class(actor, sourced, status, dlm, row, now)

        payload = {k: v for k, v in row.items() if k and v is not None}
        existing = _row(
            self.conn,
            """
            SELECT entity_id, status, payload_json FROM oneroster_entities
            WHERE site_id=? AND entity_type=? AND sourced_id=?
            """,
            (actor.site_id, entity_type, sourced),
        )
        if existing is None:
            eid = _id("ore")
            self.conn.execute(
                """
                INSERT INTO oneroster_entities(
                  entity_id, site_id, entity_type, sourced_id, status, payload_json,
                  local_ref, date_last_modified, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,NULL,?,?,?)
                """,
                (
                    eid,
                    actor.site_id,
                    entity_type,
                    sourced,
                    status,
                    json.dumps(payload),
                    dlm,
                    now,
                    now,
                ),
            )
            return "created"
        prev = json.loads(existing["payload_json"] or "{}")
        if prev == payload and existing["status"] == status:
            return "unchanged"
        self.conn.execute(
            """
            UPDATE oneroster_entities
            SET status=?, payload_json=?, date_last_modified=?, updated_at=?
            WHERE entity_id=?
            """,
            (status, json.dumps(payload), dlm, now, existing["entity_id"]),
        )
        return "updated"

    def _default_package_id(self) -> str:
        pkg = _row(self.conn, "SELECT package_id FROM packages ORDER BY created_at LIMIT 1")
        if pkg:
            return str(pkg["package_id"])
        pid = "pkg_oneroster_default"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO packages(package_id, module_id, title, source_commit, immutable, created_at)
            VALUES (?,?,?,?,1,?)
            """,
            (pid, "ONEROSTER", "OneRoster imported course", "", _now()),
        )
        return pid

    def _apply_class(
        self,
        actor: Actor,
        sourced: str,
        status: str,
        dlm: str | None,
        row: dict[str, str],
        now: str,
    ) -> str:
        title = (row.get("title") or row.get("classCode") or sourced).strip()[:200]
        code = (row.get("classCode") or row.get("code") or sourced)[:40]
        # Prefer explicit section_id only as a hint to an EXISTING section — never hide in title.
        hint_section = (row.get("section_id") or "").strip() or None
        payload = {k: v for k, v in row.items() if k and v is not None and k != "section_id"}
        payload["title"] = title
        if "classCode" not in payload:
            payload["classCode"] = code

        existing = _row(
            self.conn,
            """
            SELECT entity_id, status, local_ref, payload_json FROM oneroster_entities
            WHERE site_id=? AND entity_type='class' AND sourced_id=?
            """,
            (actor.site_id, sourced),
        )
        section_id = existing["local_ref"] if existing and existing["local_ref"] else None

        if section_id is None and hint_section:
            sec = _row(
                self.conn,
                "SELECT section_id, site_id FROM sections WHERE section_id=?",
                (hint_section,),
            )
            if sec is None:
                raise ServiceError("ONEROSTER_SECTION_NOT_FOUND", 400)
            if sec["site_id"] != actor.site_id:
                raise ServiceError("ONEROSTER_FOREIGN_SECTION", 400)
            section_id = hint_section

        if section_id is None and status == "active":
            section_id = _id("sec")
            package_id = self._default_package_id()
            # Ensure unique code within site.
            code_try = code
            n = 0
            while _row(
                self.conn,
                "SELECT section_id FROM sections WHERE site_id=? AND code=?",
                (actor.site_id, code_try),
            ):
                n += 1
                code_try = f"{code[:30]}-{n}"
            self.conn.execute(
                """
                INSERT INTO sections(section_id, site_id, package_id, code, title, published, created_at)
                VALUES (?,?,?,?,?,1,?)
                """,
                (section_id, actor.site_id, package_id, code_try, title, now),
            )
            self.conn.execute(
                """
                INSERT OR IGNORE INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at)
                VALUES (?,?,?,?)
                """,
                (section_id, "{}", f"OneRoster class {sourced}", now),
            )
        elif section_id and status == "active":
            self.conn.execute(
                "UPDATE sections SET title=? WHERE section_id=? AND site_id=?",
                (title, section_id, actor.site_id),
            )

        # Store section_id as local_ref only — never embed as title.
        payload_store = dict(payload)
        if section_id:
            payload_store["mapped_section_id"] = section_id

        if existing is None:
            self.conn.execute(
                """
                INSERT INTO oneroster_entities(
                  entity_id, site_id, entity_type, sourced_id, status, payload_json,
                  local_ref, date_last_modified, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _id("ore"),
                    actor.site_id,
                    "class",
                    sourced,
                    status,
                    json.dumps(payload_store),
                    section_id,
                    dlm,
                    now,
                    now,
                ),
            )
            return "created"
        self.conn.execute(
            """
            UPDATE oneroster_entities
            SET status=?, payload_json=?, local_ref=COALESCE(?, local_ref),
                date_last_modified=?, updated_at=?
            WHERE entity_id=?
            """,
            (status, json.dumps(payload_store), section_id, dlm, now, existing["entity_id"]),
        )
        return "updated"

    def _apply_user(
        self,
        actor: Actor,
        sourced: str,
        status: str,
        dlm: str | None,
        row: dict[str, str],
        now: str,
    ) -> str:
        role_raw = (row.get("role") or row.get("roles") or "learner").split(",")[0].strip().lower()
        mapped = ROLE_MAP.get(role_raw)
        if mapped is None:
            raise ServiceError("ONEROSTER_ROLE_MISMATCH", 400)
        if mapped in FORBIDDEN_ESCALATION:
            raise ServiceError("ONEROSTER_ROLE_ESCALATION", 400)
        org = (row.get("orgSourcedId") or row.get("org") or "").strip()
        if org:
            other = _row(
                self.conn,
                """
                SELECT site_id FROM oneroster_entities
                WHERE entity_type='org' AND sourced_id=? AND site_id!=?
                """,
                (org, actor.site_id),
            )
            if other is not None:
                raise ServiceError("ONEROSTER_CROSS_SITE_COLLISION", 400)

        username = (row.get("username") or row.get("email") or sourced).strip()
        display = (row.get("givenName") or "") + " " + (row.get("familyName") or "")
        display = display.strip() or username
        payload = {k: v for k, v in row.items() if k and v is not None}
        if "password" in {k.lower() for k in row}:
            raise ServiceError("ONEROSTER_PASSWORD_FORBIDDEN", 400)

        existing = _row(
            self.conn,
            """
            SELECT entity_id, status, local_ref, payload_json FROM oneroster_entities
            WHERE site_id=? AND entity_type='user' AND sourced_id=?
            """,
            (actor.site_id, sourced),
        )
        local_ref = existing["local_ref"] if existing else None
        if status in INACTIVE_STATUSES:
            if existing and existing["local_ref"]:
                self.conn.execute(
                    "UPDATE users SET disabled=1 WHERE user_id=? AND site_id=?",
                    (existing["local_ref"], actor.site_id),
                )
                self._revoke_user_access(actor, existing["local_ref"], reason="oneroster_user_inactive")
            action = "updated" if existing else "created"
        else:
            if local_ref is None:
                local_ref = _id("oru")
                self.conn.execute(
                    """
                    INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                    VALUES (?,?,?,?,?,1,?)
                    """,
                    (local_ref, actor.site_id, username[:80], display[:120], "!", now),
                )
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                    VALUES (?,?,?,?,1,?)
                    """,
                    (_id("ra"), local_ref, actor.site_id, mapped.value, now),
                )
                action = "created"
            else:
                u = _row(self.conn, "SELECT username FROM users WHERE user_id=?", (local_ref,))
                if u and u["username"] != username:
                    raise ServiceError("ONEROSTER_IDENTITY_CONFLICT", 400)
                self.conn.execute(
                    "UPDATE users SET display_name=? WHERE user_id=?",
                    (display[:120], local_ref),
                )
                action = "updated"

        if existing is None:
            self.conn.execute(
                """
                INSERT INTO oneroster_entities(
                  entity_id, site_id, entity_type, sourced_id, status, payload_json,
                  local_ref, date_last_modified, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _id("ore"),
                    actor.site_id,
                    "user",
                    sourced,
                    status,
                    json.dumps(payload),
                    local_ref,
                    dlm,
                    now,
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE oneroster_entities
                SET status=?, payload_json=?, local_ref=?, date_last_modified=?, updated_at=?
                WHERE entity_id=?
                """,
                (status, json.dumps(payload), local_ref, dlm, now, existing["entity_id"]),
            )
        return action

    def _revoke_user_access(self, actor: Actor, user_id: str, *, reason: str) -> None:
        now = _now()
        self.conn.execute(
            "UPDATE sessions SET revoked=1, revoked_at=? WHERE user_id=? AND revoked=0",
            (now, user_id),
        )
        # Reconcile offline leases when Gate A sync is available.
        if self.sync is not None:
            leases = _rows(
                self.conn,
                "SELECT lease_id FROM offline_leases WHERE user_id=? AND site_id=? AND revoked_at IS NULL",
                (user_id, actor.site_id),
            )
            for lease in leases:
                self.conn.execute(
                    "UPDATE offline_leases SET revoked_at=?, revoke_reason=? WHERE lease_id=?",
                    (now, reason, lease["lease_id"]),
                )
        elif _row(
            self.conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND name='offline_leases'",
        ):
            self.conn.execute(
                """
                UPDATE offline_leases SET revoked_at=?, revoke_reason=?
                WHERE user_id=? AND site_id=? AND revoked_at IS NULL
                """,
                (now, reason, user_id, actor.site_id),
            )

    def _apply_enrollment(
        self,
        actor: Actor,
        sourced: str,
        status: str,
        dlm: str | None,
        row: dict[str, str],
        now: str,
    ) -> str:
        user_sid = (row.get("userSourcedId") or row.get("user") or "").strip()
        class_sid = (row.get("classSourcedId") or row.get("class") or "").strip()
        if not user_sid or not class_sid:
            raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
        u = _row(
            self.conn,
            "SELECT entity_id, local_ref FROM oneroster_entities WHERE site_id=? AND entity_type='user' AND sourced_id=?",
            (actor.site_id, user_sid),
        )
        c = _row(
            self.conn,
            "SELECT entity_id, local_ref, payload_json FROM oneroster_entities WHERE site_id=? AND entity_type='class' AND sourced_id=?",
            (actor.site_id, class_sid),
        )
        if u is None or c is None:
            raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)

        section_id = c["local_ref"]
        if not section_id:
            payload_class = json.loads(c["payload_json"] or "{}")
            section_id = payload_class.get("mapped_section_id")
        if not section_id:
            raise ServiceError("ONEROSTER_CLASS_UNMAPPED", 400)

        sec = _row(
            self.conn,
            "SELECT section_id, site_id FROM sections WHERE section_id=?",
            (section_id,),
        )
        if sec is None:
            raise ServiceError("ONEROSTER_SECTION_NOT_FOUND", 400)
        if sec["site_id"] != actor.site_id:
            raise ServiceError("ONEROSTER_FOREIGN_SECTION", 400)

        local_user = u["local_ref"]
        enrollment_ref = None
        if local_user:
            existing_enr = _row(
                self.conn,
                "SELECT enrollment_id, status FROM enrollments WHERE section_id=? AND user_id=? ORDER BY enrolled_at DESC",
                (section_id, local_user),
            )
            if status == "active":
                if existing_enr and existing_enr["status"] == "active":
                    enrollment_ref = existing_enr["enrollment_id"]
                elif existing_enr:
                    self.conn.execute(
                        "UPDATE enrollments SET status='active', deactivated_at=NULL WHERE enrollment_id=?",
                        (existing_enr["enrollment_id"],),
                    )
                    enrollment_ref = existing_enr["enrollment_id"]
                else:
                    enrollment_ref = _id("enr")
                    self.conn.execute(
                        """
                        INSERT INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
                        VALUES (?,?,?,?,?)
                        """,
                        (enrollment_ref, section_id, local_user, "active", now),
                    )
            elif status in INACTIVE_STATUSES:
                if existing_enr and existing_enr["status"] == "active":
                    self.conn.execute(
                        "UPDATE enrollments SET status='inactive', deactivated_at=? WHERE enrollment_id=?",
                        (now, existing_enr["enrollment_id"]),
                    )
                    enrollment_ref = existing_enr["enrollment_id"]
                    # Revoke access: sessions for this user keep existing, but revoke section leases.
                    if _row(
                        self.conn,
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='offline_leases'",
                    ):
                        self.conn.execute(
                            """
                            UPDATE offline_leases SET revoked_at=?, revoke_reason=?
                            WHERE user_id=? AND section_id=? AND site_id=? AND revoked_at IS NULL
                            """,
                            (now, "oneroster_enrollment_inactive", local_user, section_id, actor.site_id),
                        )
                elif existing_enr:
                    enrollment_ref = existing_enr["enrollment_id"]

        return self._upsert_entity(
            actor, "enrollment", sourced, status, dlm, row, now, enrollment_ref or local_user
        )

    def _upsert_entity(
        self,
        actor: Actor,
        entity_type: str,
        sourced: str,
        status: str,
        dlm: str | None,
        row: dict[str, str],
        now: str,
        local_ref: str | None = None,
    ) -> str:
        payload = {k: v for k, v in row.items() if k and v is not None}
        existing = _row(
            self.conn,
            """
            SELECT entity_id, status, payload_json FROM oneroster_entities
            WHERE site_id=? AND entity_type=? AND sourced_id=?
            """,
            (actor.site_id, entity_type, sourced),
        )
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO oneroster_entities(
                  entity_id, site_id, entity_type, sourced_id, status, payload_json,
                  local_ref, date_last_modified, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _id("ore"),
                    actor.site_id,
                    entity_type,
                    sourced,
                    status,
                    json.dumps(payload),
                    local_ref,
                    dlm,
                    now,
                    now,
                ),
            )
            return "created"
        prev = json.loads(existing["payload_json"] or "{}")
        if prev == payload and existing["status"] == status:
            return "unchanged"
        self.conn.execute(
            """
            UPDATE oneroster_entities
            SET status=?, payload_json=?, local_ref=COALESCE(?, local_ref),
                date_last_modified=?, updated_at=?
            WHERE entity_id=?
            """,
            (status, json.dumps(payload), local_ref, dlm, now, existing["entity_id"]),
        )
        return "updated"

    def export_csv(self, actor: Actor, entity_file: str) -> str:
        if not actor.is_site_admin and not actor.is_instructor_side:
            raise ServiceError("ONEROSTER_FORBIDDEN", 403)
        if self.privacy is not None:
            self.privacy.assert_export_allowed(actor.site_id, "oneroster")
        if entity_file not in SUPPORTED_TYPES:
            raise ServiceError("ONEROSTER_UNSUPPORTED_TYPE", 400)
        entity_type = ENTITY_MAP[entity_file]
        rows = _rows(
            self.conn,
            """
            SELECT sourced_id, status, date_last_modified, payload_json
            FROM oneroster_entities
            WHERE site_id=? AND entity_type=?
            ORDER BY sourced_id
            """,
            (actor.site_id, entity_type),
        )
        buf = io.StringIO()
        fieldnames = ["sourcedId", "status", "dateLastModified"]
        extras: list[str] = []
        parsed: list[dict[str, str]] = []
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            out = {
                "sourcedId": r["sourced_id"],
                "status": r["status"],
                "dateLastModified": r["date_last_modified"] or "",
            }
            for k, v in payload.items():
                if k in {"sourcedId", "status", "dateLastModified", "mapped_section_id"}:
                    continue
                out[k] = v
                if k not in extras and k not in fieldnames:
                    extras.append(k)
            parsed.append(out)
        writer = csv.DictWriter(buf, fieldnames=fieldnames + sorted(extras), extrasaction="ignore")
        writer.writeheader()
        for row in parsed:
            writer.writerow(row)
        return buf.getvalue()

    def import_status(self, actor: Actor, import_id: str | None = None) -> dict[str, Any]:
        self._require_operator(actor)
        if import_id:
            row = _row(
                self.conn,
                "SELECT * FROM oneroster_imports WHERE import_id=? AND site_id=?",
                (import_id, actor.site_id),
            )
            if row is None:
                raise ServiceError("ONEROSTER_IMPORT_NOT_FOUND", 404)
            return dict(row)
        rows = _rows(
            self.conn,
            """
            SELECT import_id, source_filename, created_count, updated_count, rejected_count, created_at
            FROM oneroster_imports WHERE site_id=? ORDER BY created_at DESC LIMIT 20
            """,
            (actor.site_id,),
        )
        return {"imports": [dict(r) for r in rows]}
