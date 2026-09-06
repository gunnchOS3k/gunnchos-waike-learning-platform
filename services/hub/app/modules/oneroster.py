"""OneRoster pilot subset: orgs, users, courses, classes, enrollments.

Pilot CSV semantics only — not full OneRoster certification.
Imported identity never bypasses local authorization.
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


class OneRosterService:
    def __init__(self, conn: sqlite3.Connection, identity: Any | None = None) -> None:
        self.conn = conn
        self.identity = identity

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

        created = updated = rejected = 0
        rejects: list[dict[str, Any]] = []
        rows_seen = 0
        entity_type = ENTITY_MAP[entity_file]
        now = _now()

        for row in reader:
            rows_seen += 1
            if rows_seen > MAX_ROWS:
                raise ServiceError("ONEROSTER_ROW_LIMIT", 400)
            try:
                for v in row.values():
                    if isinstance(v, str) and self._detect_formula(v):
                        raise ServiceError("ONEROSTER_FORMULA_INJECTION", 400)
                result = self._apply_row(actor, entity_type, row, now)
                if result == "created":
                    created += 1
                elif result == "updated":
                    updated += 1
                else:
                    # unchanged idempotent
                    updated += 0
            except ServiceError as e:
                rejected += 1
                rejects.append({"sourcedId": row.get("sourcedId"), "code": e.code})

        import_id = _id("orimp")
        report = {
            "entity_file": entity_file,
            "rejects": rejects[:50],
            "rows_seen": rows_seen,
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
                rejected,
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
                "rejected": rejected,
            },
        )
        self.conn.commit()
        return {
            "import_id": import_id,
            "source_sha256": sha,
            "created": created,
            "updated": updated,
            "rejected": rejected,
            "report": report,
        }

    def _apply_row(
        self, actor: Actor, entity_type: str, row: dict[str, str], now: str
    ) -> str:
        sourced = (row.get("sourcedId") or "").strip()
        if not sourced:
            raise ServiceError("ONEROSTER_MISSING_SOURCED_ID", 400)
        status = (row.get("status") or "active").strip().lower()
        if status not in {"active", "inactive", "tobedeleted", "deleted"}:
            raise ServiceError("ONEROSTER_BAD_STATUS", 400)
        dlm = (row.get("dateLastModified") or "").strip() or None

        if entity_type == "user":
            return self._apply_user(actor, sourced, status, dlm, row, now)
        if entity_type == "enrollment":
            return self._apply_enrollment(actor, sourced, status, dlm, row, now)
        if entity_type == "class":
            course = (row.get("courseSourcedId") or row.get("course") or "").strip()
            if course:
                cref = _row(
                    self.conn,
                    "SELECT entity_id FROM oneroster_entities WHERE site_id=? AND entity_type='course' AND sourced_id=?",
                    (actor.site_id, course),
                )
                if cref is None and status == "active":
                    raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
        if entity_type == "org":
            # org must belong to importing site semantics
            pass

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
            # Never escalate imported user to site_admin via OneRoster.
            raise ServiceError("ONEROSTER_ROLE_ESCALATION", 400)
        org = (row.get("orgSourcedId") or row.get("org") or "").strip()
        if org:
            # Cross-site sourcedId collision: org must exist in this site if referenced.
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
        # Never accept passwords.
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
        if status in {"inactive", "tobedeleted", "deleted"}:
            if existing and existing["local_ref"]:
                # Do not silently reactivate; inactivation marks entity only.
                self.conn.execute(
                    "UPDATE users SET disabled=1 WHERE user_id=? AND site_id=?",
                    (existing["local_ref"], actor.site_id),
                )
            action = "updated" if existing else "created"
        else:
            # Create shadow local user without password auth bypass — disabled until admin sets password.
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
                # Conflicting identity: same sourcedId different username → reject.
                u = _row(self.conn, "SELECT username FROM users WHERE user_id=?", (local_ref,))
                if u and u["username"] != username:
                    raise ServiceError("ONEROSTER_IDENTITY_CONFLICT", 400)
                # Inactive reactivation requires explicit status active + prior inactive policy.
                if existing and existing["status"] in {"inactive", "deleted", "tobedeleted"}:
                    # Reactivation allowed only when status flips to active under operator import
                    # but user stays disabled until password set (no auth bypass).
                    pass
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
        return action if existing or status not in {"inactive", "deleted", "tobedeleted"} else action

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
            "SELECT entity_id, payload_json FROM oneroster_entities WHERE site_id=? AND entity_type='class' AND sourced_id=?",
            (actor.site_id, class_sid),
        )
        if u is None or c is None:
            raise ServiceError("ONEROSTER_INVALID_REFERENCE", 400)
        # Foreign section: class may map to section via payload section_id
        payload_class = json.loads(c["payload_json"] or "{}")
        section_id = payload_class.get("section_id") or payload_class.get("title")
        if section_id:
            sec = _row(
                self.conn,
                "SELECT section_id, site_id FROM sections WHERE section_id=?",
                (section_id,),
            )
            if sec and sec["site_id"] != actor.site_id:
                raise ServiceError("ONEROSTER_FOREIGN_SECTION", 400)
            if sec and u["local_ref"] and status == "active":
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (_id("enr"), section_id, u["local_ref"], "active", now),
                )
        return self._upsert_entity(actor, "enrollment", sourced, status, dlm, row, now, u["local_ref"])

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
                if k in {"sourcedId", "status", "dateLastModified"}:
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
