"""Canonical 18-track IDs and digital_rc package folder mapping."""

from __future__ import annotations

CANONICAL_TRACK_IDS: tuple[str, ...] = (
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

# digital_rc folder name when it differs from track_id (or None = no digital_rc package)
DIGITAL_RC_PACKAGE: dict[str, str | None] = {
    "DIGITAL_CONFIDENCE": None,  # legacy lessons/by_course import
    "IT_SUPPORT_HARDWARE": "GENERAL_IT",
    "NETWORKING_INFRA": "COMPUTER_NETWORKING",
    "CYBER_SOC": "CYBERSECURITY",
    # SEVEN_GC_APPRENTICESHIP uses folder name == track_id (default); omit override.
}

PACKAGE_VERSION = "1.0.0"
MIGRATION_METADATA = {
    "from": "digital_confidence_only",
    "to": "registry_18_tracks",
    "content_schema": "waike.course_package.v1",
    "compiler_package_version": PACKAGE_VERSION,
}

DEFAULT_INSTRUCTOR_MARKERS: list[str] = [
    "instructor_solution",
    "instructor_solution_guide",
    "instructor_solution_guides/",
    "solution_guide",
    "solution_notes_for_instructors",
    "instructor_notes",
    "answer_key",
    "answer_keys/",
    "answer_keys.json",
    "/instructor/",
    "instructor_packet",
    "instructor_packet.md",
    "deep_instructor",
    "teaching_notes.md",
    "demo_plan.md",
]


def digital_rc_folder(track_id: str) -> str | None:
    if track_id in DIGITAL_RC_PACKAGE:
        return DIGITAL_RC_PACKAGE[track_id]
    return track_id


def package_version() -> str:
    return PACKAGE_VERSION
