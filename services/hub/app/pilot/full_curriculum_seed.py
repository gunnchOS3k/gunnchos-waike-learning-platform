"""Load all 18 canonical tracks into a running Hub DB.

Source of truth remains curriculum/registry (PIN + eighteen_tracks.json).
Fails closed if any canonical track cannot be registered.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.modules.assessment_lifecycle import _now
from app.modules.identity import IdentityService
from app.modules.sections import SectionService

EXPECTED_TRACK_IDS = (
    "DIGITAL_CONFIDENCE",
    "IT_SUPPORT_HARDWARE",
    "SOFTWARE_BUILDER",
    "NETWORKING_INFRA",
    "CYBER_SOC",
    "DATA_DASHBOARDS",
    "AI_ML_EDGE",
    "EMBEDDED_PROTOTYPING",
    "WIRELESS_6G",
    "PM_AGILE_LSS",
    "GAME_DEV_INTERACTIVE",
    "SEVEN_GC_APPRENTICESHIP",
    "CLOUD_DEVOPS",
    "COMM_PD_ETHICS",
    "ROBOTICS_CONTROL",
    "GUNNCHOS_PRODUCT_LAB",
    "HARDWARE_ENGINEERING",
    "DATA_VIZ_BI",
)


class CurriculumLoadError(RuntimeError):
    """Raised when any canonical track cannot be loaded into Hub runtime."""


def _platform_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_registry(platform_root: Path | None = None) -> dict[str, Any]:
    root = platform_root or _platform_root()
    registry = root / "curriculum" / "registry" / "eighteen_tracks.json"
    pin_path = root / "curriculum" / "registry" / "PIN.json"
    if not registry.is_file():
        raise CurriculumLoadError(f"MISSING_REGISTRY:{registry}")
    if not pin_path.is_file():
        raise CurriculumLoadError(f"MISSING_PIN:{pin_path}")
    data = json.loads(registry.read_text(encoding="utf-8"))
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    tracks = [t.get("track_id") for t in (data.get("tracks") or []) if t.get("track_id")]
    allowed = list(pin.get("module_ids_allowed") or [])
    if tracks != list(EXPECTED_TRACK_IDS):
        raise CurriculumLoadError(f"REGISTRY_TRACK_MISMATCH:{tracks}")
    if allowed != list(EXPECTED_TRACK_IDS):
        raise CurriculumLoadError(f"PIN_TRACK_MISMATCH:{allowed}")
    return {
        "registry_path": str(registry),
        "pin_path": str(pin_path),
        "pinned_commit": pin.get("pinned_commit") or "",
        "tracks": data.get("tracks") or [],
        "source_repo": pin.get("source_repo"),
    }


def inventory_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT p.package_id, p.module_id, p.title, p.source_commit,
               s.section_id, s.site_id, s.code, s.published
        FROM packages p
        LEFT JOIN sections s ON s.package_id = p.package_id
        ORDER BY p.module_id, s.site_id
        """
    ).fetchall()
    by_track: dict[str, dict[str, Any]] = {}
    for r in rows:
        mid = r["module_id"]
        slot = by_track.setdefault(
            mid,
            {
                "track_id": mid,
                "package_id": r["package_id"],
                "title": r["title"],
                "source_commit": r["source_commit"],
                "sections": [],
            },
        )
        if r["section_id"]:
            slot["sections"].append(
                {
                    "section_id": r["section_id"],
                    "site_id": r["site_id"],
                    "code": r["code"],
                    "published": bool(r["published"]),
                }
            )
    missing = [t for t in EXPECTED_TRACK_IDS if t not in by_track]
    return {
        "expected_track_ids": list(EXPECTED_TRACK_IDS),
        "loaded_track_ids": [t for t in EXPECTED_TRACK_IDS if t in by_track],
        "missing_track_ids": missing,
        "all_18_loaded": len(missing) == 0,
        "tracks": [by_track[t] for t in EXPECTED_TRACK_IDS if t in by_track],
    }


def seed_full_curriculum(
    conn: sqlite3.Connection,
    *,
    identity: IdentityService | None = None,
    sections: SectionService | None = None,
    platform_root: Path | None = None,
    site_ids: tuple[str, ...] = ("site-alpha", "site-beta"),
    instructor_by_site: dict[str, str] | None = None,
    grader_by_site: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Register one package + published section per track per site.

    Does not duplicate taxonomy authorship. Track IDs are preserved from the registry.
    """
    meta = load_registry(platform_root)
    now = _now()
    identity = identity or IdentityService(conn)
    sections = sections or SectionService(conn)
    instructor_by_site = instructor_by_site or {
        "site-alpha": "instructor-alpha",
        "site-beta": "instructor-beta",
    }
    grader_by_site = grader_by_site or {"site-alpha": "grader-alpha"}

    for site_id, name in (("site-alpha", "Alpha Academy"), ("site-beta", "Beta Institute")):
        conn.execute(
            "INSERT OR IGNORE INTO sites(site_id, name, created_at) VALUES (?,?,?)",
            (site_id, name, now),
        )

    loaded: list[dict[str, Any]] = []
    for track in meta["tracks"]:
        track_id = track["track_id"]
        title = track.get("title") or track_id
        package_id = f"pkg_pilot_{track_id.lower()}"
        conn.execute(
            """
            INSERT OR IGNORE INTO packages(package_id, module_id, title, source_commit, immutable, created_at)
            VALUES (?,?,?,?,1,?)
            """,
            (package_id, track_id, title, meta["pinned_commit"], now),
        )
        for site_id in site_ids:
            suffix = "A" if site_id.endswith("alpha") else "B"
            section_id = f"sec_{site_id.split('-')[-1]}_{track_id.lower()}_pilot"
            code = f"PX-{track_id[:10]}-{suffix}"
            conn.execute(
                """
                INSERT OR IGNORE INTO sections(section_id, site_id, package_id, code, title, published, created_at)
                VALUES (?,?,?,?,?,1,?)
                """,
                (section_id, site_id, package_id, code, f"{title} — {site_id}", now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at)
                VALUES (?,?,?,?)
                """,
                (section_id, "{}", "Pixel 6a full-curriculum pilot", now),
            )
            inst = instructor_by_site.get(site_id)
            if inst and conn.execute("SELECT user_id FROM users WHERE user_id=?", (inst,)).fetchone():
                conn.execute(
                    "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
                    (section_id, inst, now),
                )
            grd = grader_by_site.get(site_id)
            if grd and conn.execute("SELECT user_id FROM users WHERE user_id=?", (grd,)).fetchone():
                conn.execute(
                    "INSERT OR IGNORE INTO section_graders(section_id, user_id, assigned_at) VALUES (?,?,?)",
                    (section_id, grd, now),
                )
        loaded.append(
            {
                "track_id": track_id,
                "package_id": package_id,
                "title": title,
                "requirement_id": track.get("requirement_id"),
                "source_commit": meta["pinned_commit"],
            }
        )

    conn.commit()
    inv = inventory_from_db(conn)
    if not inv["all_18_loaded"]:
        raise CurriculumLoadError(f"MISSING_TRACK:{inv['missing_track_ids']}")
    inv["registry"] = {
        "path": meta["registry_path"],
        "pinned_commit": meta["pinned_commit"],
        "source_repo": meta["source_repo"],
    }
    inv["duplicate_sot"] = False
    return inv
