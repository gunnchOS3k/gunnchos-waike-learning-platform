"""Gate B: install each of 18 tracks into hub section fixtures."""

from __future__ import annotations

import pytest

from course_compiler.tracks import CANONICAL_TRACK_IDS
from helpers import install_track_into_hub, matrix_row, resolve_pack_dir


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_install_verify_and_visibility(client, packs_18, track_id):
    pack_dir = resolve_pack_dir(track_id, packs_18)
    installed = install_track_into_hub(client, track_id, pack_dir)

    assert installed["verification_ok"] is True
    assert installed["learner_visible"] is True

    row = matrix_row(track_id)
    # Hub section always exposes the package to assigned instructor.
    assert installed["instructor_visible"] is True

    # Matrix may mark instructor_visible EMPTY when instructor pack has zero files
    # (e.g. SEVEN_GC_APPRENTICESHIP) — keep that honesty without inventing content.
    if row.get("instructor_visible") == "EMPTY":
        assert installed["instructor_file_count"] == 0
    else:
        assert installed["instructor_file_count"] > 0 or track_id == "DIGITAL_CONFIDENCE"

    assert installed["section_id"]
    assert installed["package_id"].endswith(track_id.lower())
