"""Device Quartet digital profiles — synthetic capability matrices.

Physical performance/ergonomics remain EXTERNAL.
"""

from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "student_14_5": {
        "id": "student_14_5",
        "name": 'Student 14.5"',
        "research_role": "full-session desk learning/work",
        "viewport": {"width": 1920, "height": 1200, "touch": False},
        "input": ["keyboard", "pointer"],
        "compute": "sustained_local",
        "labs": True,
        "offline_cache": True,
        "workflows": ["learner_full", "instructor_full"],
        "companion_only": False,
    },
    "handheld_hybrid": {
        "id": "handheld_hybrid",
        "name": "Handheld Hybrid",
        "research_role": "mobile/docked continuity",
        "viewport": {"width": 1280, "height": 800, "touch": True},
        "input": ["touch", "gamepad_like", "dock_keyboard"],
        "compute": "mobile",
        "labs": True,
        "offline_cache": True,
        "workflows": ["learner_full", "dock_extend"],
        "companion_only": False,
        "not_gaming_only": True,
    },
    "ds_xl_coder": {
        "id": "ds_xl_coder",
        "name": "DS-XL Coder",
        "research_role": "creation/build/test/deploy",
        "viewport": {"width": 2560, "height": 1600, "touch": False, "dual_display": True},
        "input": ["keyboard", "pointer"],
        "compute": "strong_local_dev",
        "labs": True,
        "offline_cache": True,
        "workflows": ["learner_full", "instructor_full", "local_dev_runtime", "terminal_editor"],
        "companion_only": False,
        "strongest_learn_to_build": True,
    },
    "edge_io_wearables": {
        "id": "edge_io_wearables",
        "name": "Edge IO Wearables",
        "research_role": "low-latency sensing/haptics/HUD",
        "viewport": {"width": 480, "height": 480, "touch": True, "hud": True},
        "input": ["sensors", "haptics", "companion_deep_link"],
        "compute": "constrained",
        "labs": False,
        "offline_cache": True,
        "workflows": ["companion", "deep_link", "sensor_haptic"],
        "companion_only": True,
        "standalone_full_lms": False,
    },
}


def capabilities_for(profile_id: str) -> dict[str, Any]:
    p = PROFILES[profile_id]
    return {
        "profile_id": profile_id,
        "viewport": p["viewport"],
        "input": p["input"],
        "compute": p["compute"],
        "labs_supported": p["labs"],
        "offline_cache": p["offline_cache"],
        "workflows": p["workflows"],
        "companion_only": p["companion_only"],
        "ui_density": "full" if not p["companion_only"] else "constrained",
        "physical_validation": "EXTERNAL",
    }


def responsive_behavior(profile_id: str) -> dict[str, Any]:
    caps = capabilities_for(profile_id)
    w = caps["viewport"]["width"]
    return {
        "profile_id": profile_id,
        "layout": "companion_shell" if caps["companion_only"] else ("compact" if w < 1400 else "desktop"),
        "nav": "touch_first" if caps["viewport"].get("touch") else "keyboard_pointer",
        "show_terminal": "local_dev_runtime" in caps["workflows"],
        "show_full_gradebook": not caps["companion_only"],
        "deep_link_primary": caps["companion_only"],
    }


def matrix() -> dict[str, Any]:
    return {
        "profiles": list(PROFILES.values()),
        "fixture_label": "device_quartet_digital_fixture_only",
        "physical_validation": "EXTERNAL — not claimed by Gate C",
        "digital_tests": "synthetic capability profiles only",
    }
