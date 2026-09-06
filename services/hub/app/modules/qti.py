"""QTI subset matching Gate A quiz engine item types.

Secure XML (no XXE / entity expansion). Not full QTI certification.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import zipfile
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row

# Gate A quiz item types we map.
SUPPORTED_INTERACTIONS = {
    "single_choice": "choiceInteraction",
    "multi_select": "choiceInteraction",
    "true_false": "choiceInteraction",
    "short_response": "textEntryInteraction",
    "numeric": "extendedTextInteraction",
    "file_response": "uploadInteraction",
}

UNSUPPORTED = [
    "customInteraction scripts",
    "portableCustomInteraction",
    "adaptive items",
    "external resource fetch",
    "mathML scoring extensions",
]

MAX_ARCHIVE_BYTES = 2_000_000
MAX_UNCOMPRESSED = 8_000_000
DANGEROUS_HTML = re.compile(r"<\s*(script|iframe|object|embed|link|meta)\b", re.I)


def _sanitize_text(text: str) -> str:
    cleaned = html.escape(text or "", quote=True)
    # Strip any residual dangerous tags if caller passed already-escaped mixtures.
    if DANGEROUS_HTML.search(text or ""):
        raise ServiceError("QTI_MALICIOUS_HTML", 400)
    return cleaned


class SecureXMLParser(ET.XMLParser):
    """Reject DOCTYPE / entities (XXE / billion laughs) via pre-check + parse."""

    pass


def parse_xml_secure(data: bytes) -> ET.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ServiceError("QTI_XXE_REJECTED", 400)
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ServiceError("QTI_MALFORMED_XML", 400) from e


class QtiService:
    def __init__(self, conn: sqlite3.Connection, activities: Any | None = None) -> None:
        self.conn = conn
        self.activities = activities

    def support_matrix(self) -> dict[str, Any]:
        return {
            "standard": "QTI subset for Gate A quiz engine",
            "claim": "NOT_FULL_QTI",
            "supported_item_types": list(SUPPORTED_INTERACTIONS),
            "unsupported": UNSUPPORTED,
            "security": [
                "XXE rejected",
                "entity expansion rejected",
                "zip traversal rejected",
                "HTML sanitized",
                "answer-key instructor-only",
            ],
        }

    def import_item_xml(
        self,
        actor: Actor,
        *,
        xml_text: str,
        section_id: str,
        quiz_id: str | None = None,
    ) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("QTI_FORBIDDEN", 403)
        raw = xml_text.encode("utf-8")
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ServiceError("QTI_TOO_LARGE", 400)
        root = parse_xml_secure(raw)
        item = self._parse_assessment_item(root)
        sha = hashlib.sha256(raw).hexdigest()
        now = _now()
        qid = quiz_id or _id("quiz")
        existing = _row(self.conn, "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=?", (qid,))
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO quiz_definitions(
                  quiz_id, section_id, site_id, title, policies_json, answer_key_json,
                  offline_eligible, high_integrity_timed, created_by, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    qid,
                    section_id,
                    actor.site_id,
                    item.get("title") or "QTI Import",
                    json.dumps({"max_attempts": 3}),
                    json.dumps({item["item_id"]: item["answer_key"]}),
                    1,
                    0,
                    actor.actor_id,
                    now,
                ),
            )
        else:
            # Merge answer key (instructor-only storage).
            row = _row(self.conn, "SELECT answer_key_json FROM quiz_definitions WHERE quiz_id=?", (qid,))
            key = json.loads(row["answer_key_json"] or "{}")
            key[item["item_id"]] = item["answer_key"]
            self.conn.execute(
                "UPDATE quiz_definitions SET answer_key_json=? WHERE quiz_id=?",
                (json.dumps(key), qid),
            )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO quiz_items(
              item_id, quiz_id, ordinal, item_type, prompt, options_json, max_points, grading_mode
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                item["item_id"],
                qid,
                item.get("ordinal", 1),
                item["item_type"],
                item["prompt"],
                json.dumps(item.get("options") or []),
                item.get("max_points", 1.0),
                item.get("grading_mode", "objective"),
            ),
        )
        import_id = _id("qti")
        self.conn.execute(
            """
            INSERT INTO qti_imports(
              import_id, site_id, actor_id, section_id, quiz_id, source_sha256,
              item_count, rejected_count, report_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                import_id,
                actor.site_id,
                actor.actor_id,
                section_id,
                qid,
                sha,
                1,
                0,
                json.dumps({"item_id": item["item_id"]}),
                now,
            ),
        )
        _audit(self.conn, actor.actor_id, "qti.import", "qti_import", import_id, {"quiz_id": qid, "sha": sha})
        self.conn.commit()
        return {"import_id": import_id, "quiz_id": qid, "item": {k: v for k, v in item.items() if k != "answer_key"}}

    def _parse_assessment_item(self, root: ET.Element) -> dict[str, Any]:
        tag = root.tag.split("}")[-1]
        if tag not in {"assessmentItem", "item"}:
            # Allow wrapper
            found = None
            for child in root.iter():
                if child.tag.split("}")[-1] == "assessmentItem":
                    found = child
                    break
            if found is None:
                raise ServiceError("QTI_UNSUPPORTED_INTERACTION", 400)
            root = found
        ident = root.attrib.get("identifier") or _id("qi")
        title = _sanitize_text(root.attrib.get("title") or ident)
        prompt_el = None
        for el in root.iter():
            if el.tag.split("}")[-1] in {"prompt", "itemBody"}:
                prompt_el = el
                break
        if prompt_el is not None:
            raw_xml = ET.tostring(prompt_el, encoding="unicode")
            if DANGEROUS_HTML.search(raw_xml):
                raise ServiceError("QTI_MALICIOUS_HTML", 400)
            prompt_raw = "".join(prompt_el.itertext())
        else:
            prompt_raw = title
        prompt = _sanitize_text(prompt_raw.strip() or title)

        interaction = None
        for el in root.iter():
            local = el.tag.split("}")[-1]
            if local.endswith("Interaction") or local in {
                "choiceInteraction",
                "textEntryInteraction",
                "extendedTextInteraction",
                "uploadInteraction",
            }:
                interaction = el
                break
        if interaction is None:
            raise ServiceError("QTI_UNSUPPORTED_INTERACTION", 400)
        itype = interaction.tag.split("}")[-1]
        cardinality = interaction.attrib.get("cardinality", "single")
        options: list[str] = []
        for choice in interaction:
            if choice.tag.split("}")[-1] == "simpleChoice":
                cid = choice.attrib.get("identifier") or choice.text or ""
                options.append(_sanitize_text(cid.strip()))

        if itype == "choiceInteraction":
            if set(options) <= {"true", "false", "True", "False"} or len(options) == 2 and {"true", "false"} <= {
                o.lower() for o in options
            }:
                item_type = "true_false"
            elif cardinality == "multiple":
                item_type = "multi_select"
            else:
                item_type = "single_choice"
        elif itype == "textEntryInteraction":
            item_type = "short_response"
        elif itype == "extendedTextInteraction":
            # numeric if responseDeclaration baseType float/integer
            item_type = "numeric"
            for el in root.iter():
                if el.tag.split("}")[-1] == "responseDeclaration":
                    bt = el.attrib.get("baseType", "")
                    if bt in {"string"}:
                        item_type = "short_response"
                    break
        elif itype == "uploadInteraction":
            item_type = "file_response"
        else:
            raise ServiceError("QTI_UNSUPPORTED_INTERACTION", 400)

        answer_key: dict[str, Any] = {}
        for el in root.iter():
            if el.tag.split("}")[-1] == "correctResponse":
                vals = [
                    (v.text or "").strip()
                    for v in el
                    if v.tag.split("}")[-1] == "value" and (v.text or "").strip()
                ]
                if item_type == "true_false":
                    answer_key = {"correct": vals[0].lower() in {"true", "1", "yes"} if vals else False}
                elif item_type == "multi_select":
                    answer_key = {"correct": vals}
                elif item_type == "single_choice":
                    answer_key = {"correct": vals}
                elif item_type == "numeric":
                    try:
                        answer_key = {"correct": float(vals[0]), "tolerance": 0}
                    except (ValueError, IndexError):
                        answer_key = {"correct": 0, "tolerance": 0}
                elif item_type == "short_response":
                    answer_key = {"correct_normalized": (vals[0] if vals else "").lower()}
                else:
                    answer_key = {"manual": True}

        grading_mode = "manual" if item_type == "file_response" else "objective"
        return {
            "item_id": ident[:80],
            "title": title,
            "prompt": prompt,
            "item_type": item_type,
            "options": options,
            "max_points": 1.0,
            "grading_mode": grading_mode,
            "answer_key": answer_key,
            "ordinal": 1,
        }

    def export_item_xml(self, actor: Actor, item_id: str) -> str:
        if not actor.is_instructor_side:
            raise ServiceError("QTI_FORBIDDEN", 403)
        item = _row(self.conn, "SELECT * FROM quiz_items WHERE item_id=?", (item_id,))
        if item is None:
            raise ServiceError("QTI_ITEM_NOT_FOUND", 404)
        quiz = _row(
            self.conn,
            "SELECT site_id, answer_key_json FROM quiz_definitions WHERE quiz_id=?",
            (item["quiz_id"],),
        )
        if quiz is None or quiz["site_id"] != actor.site_id:
            raise ServiceError("QTI_FORBIDDEN", 403)
        key = json.loads(quiz["answer_key_json"] or "{}").get(item_id, {})
        options = json.loads(item["options_json"] or "[]")
        itype = item["item_type"]
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<assessmentItem xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="{html.escape(item_id)}" title="{html.escape(item["prompt"][:80])}">',
            "<itemBody>",
            f"<prompt>{html.escape(item['prompt'])}</prompt>",
        ]
        if itype in {"single_choice", "multi_select", "true_false"}:
            card = "multiple" if itype == "multi_select" else "single"
            lines.append(f'<choiceInteraction responseIdentifier="RESPONSE" cardinality="{card}">')
            opts = options or (["true", "false"] if itype == "true_false" else [])
            for o in opts:
                lines.append(f'<simpleChoice identifier="{html.escape(str(o))}">{html.escape(str(o))}</simpleChoice>')
            lines.append("</choiceInteraction>")
        elif itype == "short_response":
            lines.append('<textEntryInteraction responseIdentifier="RESPONSE"/>')
        elif itype == "numeric":
            lines.append('<extendedTextInteraction responseIdentifier="RESPONSE"/>')
        elif itype == "file_response":
            lines.append('<uploadInteraction responseIdentifier="RESPONSE"/>')
        lines.append("</itemBody>")
        lines.append('<responseDeclaration identifier="RESPONSE">')
        lines.append("<correctResponse>")
        if itype == "true_false":
            lines.append(f"<value>{'true' if key.get('correct') else 'false'}</value>")
        elif itype in {"single_choice", "multi_select"}:
            for v in key.get("correct") or []:
                lines.append(f"<value>{html.escape(str(v))}</value>")
        elif itype == "numeric":
            lines.append(f"<value>{key.get('correct', 0)}</value>")
        elif itype == "short_response":
            lines.append(f"<value>{html.escape(str(key.get('correct_normalized', '')))}</value>")
        lines.append("</correctResponse>")
        lines.append("</responseDeclaration>")
        lines.append("</assessmentItem>")
        return "\n".join(lines)

    def import_package_zip(self, actor: Actor, data: bytes, section_id: str) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("QTI_FORBIDDEN", 403)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ServiceError("QTI_TOO_LARGE", 400)
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as e:
            raise ServiceError("QTI_BAD_ZIP", 400) from e
        total = 0
        xml_files: list[tuple[str, bytes]] = []
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ServiceError("QTI_ZIP_TRAVERSAL", 400)
            if info.file_size > MAX_UNCOMPRESSED or total + info.file_size > MAX_UNCOMPRESSED:
                raise ServiceError("QTI_ZIP_BOMB", 400)
            total += info.file_size
            if name.endswith(".xml"):
                xml_files.append((name, zf.read(info)))
        if not xml_files:
            raise ServiceError("QTI_EMPTY_PACKAGE", 400)
        results = []
        quiz_id = _id("quiz")
        for _name, raw in xml_files:
            results.append(
                self.import_item_xml(actor, xml_text=raw.decode("utf-8"), section_id=section_id, quiz_id=quiz_id)
            )
        return {"quiz_id": quiz_id, "items": len(results), "imports": results}

    def round_trip_semantic(self, actor: Actor, item_id: str) -> dict[str, Any]:
        xml = self.export_item_xml(actor, item_id)
        item = _row(self.conn, "SELECT * FROM quiz_items WHERE item_id=?", (item_id,))
        assert item is not None
        parsed = self._parse_assessment_item(parse_xml_secure(xml.encode("utf-8")))
        return {
            "item_id": item_id,
            "original_type": item["item_type"],
            "round_trip_type": parsed["item_type"],
            "prompt_match": _sanitize_text(item["prompt"]) == parsed["prompt"]
            or item["prompt"] == parsed["prompt"]
            or html.unescape(parsed["prompt"]) == item["prompt"],
            "type_match": item["item_type"] == parsed["item_type"],
        }
