"""Gate B: offline support flag + progress sync for installed packages."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from course_compiler.tracks import CANONICAL_TRACK_IDS
from helpers import (
    install_track_into_hub,
    matrix_row,
    pack_has_offline_marker,
    resolve_pack_dir,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "gate_a"))
from offline_client import OfflineDevice  # noqa: E402


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_offline_flag_and_progress_sync(client, packs_18, tmp_path, track_id):
    pack_dir = resolve_pack_dir(track_id, packs_18)
    installed = install_track_into_hub(client, track_id, pack_dir)
    section_id = installed["section_id"]
    row = matrix_row(track_id)

    has_offline = pack_has_offline_marker(pack_dir)
    assert installed["offline_pack"] is has_offline
    # Matrix offline column must match pack inventory (honest; DC may be NO)
    if row.get("offline") == "YES":
        assert has_offline is True
    else:
        assert has_offline is False

    # Progress sync works for every installed package (Gate A OfflineDevice pattern)
    device = OfflineDevice(
        device_id=f"gb-off-{track_id[:8]}",
        db_path=tmp_path / f"off_{track_id}.sqlite",
        client=client,
        token=installed["learner_token"],
        site_id="site-alpha",
        section_id=section_id,
    )
    device.obtain_lease()
    device.set_online(False)
    mid = device.save_progress_local(installed["package_id"], f"off_lesson_{track_id}", 25.0)
    assert device.pending_count() == 1
    assert device.ux_state == "offline"
    device.restart()
    assert device.pending_count() == 1
    device.set_online(True)
    results = device.sync_outbox()
    assert results and results[0]["sync_status"] == "acknowledged"
    assert mid in [
        r["client_mutation_id"]
        for r in device.conn.execute("SELECT client_mutation_id FROM outbox").fetchall()
    ]
    assert device.never_synced_without_ack()
    pulled = device.pull()
    assert any(p["lesson_id"] == f"off_lesson_{track_id}" for p in pulled["lesson_progress"])
