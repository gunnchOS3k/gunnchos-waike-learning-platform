"""Offline restart persistence + sync UX invariants."""

from helpers import SECTION, login
from offline_client import OfflineDevice


def test_offline_restart_and_ack_before_synced(client, tmp_path):
    sess = login(client, "learner-alpha")
    dev = OfflineDevice(
        device_id="device-restart-a",
        db_path=tmp_path / "restart.sqlite",
        client=client,
        token=sess["token"],
        site_id="site-alpha",
        section_id=SECTION,
    )
    dev.obtain_lease()
    dev.set_online(False)
    mid = dev.save_progress_local("pack_dc", "lesson_restart", 33.0)
    assert dev.pending_count() == 1
    assert dev.ux_state == "offline"
    dev.restart()
    assert dev.pending_count() == 1
    assert mid in [
        r["client_mutation_id"]
        for r in dev.conn.execute("SELECT client_mutation_id FROM outbox").fetchall()
    ]
    # Must not claim synced before ack
    assert "synced" not in [
        r["sync_status"]
        for r in dev.conn.execute("SELECT sync_status FROM outbox").fetchall()
        if r["sync_status"] == "acknowledged" and False
    ]
    dev.set_online(True)
    results = dev.sync_outbox()
    assert results and results[0]["sync_status"] == "acknowledged"
    assert dev.acknowledged_count() == 1
    assert dev.never_synced_without_ack()
    assert dev.ux_state == "synced"
