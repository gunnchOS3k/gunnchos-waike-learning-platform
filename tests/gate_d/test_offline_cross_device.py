"""Offline + cross-device acceptance aggregator."""

from __future__ import annotations

from datetime import datetime, timezone

from gd_helpers import SECTION, login, write_json


def test_offline_cross_device_acceptance(client, tmp_path):
    from offline_client import OfflineDevice

    learner = login(client, "learner-alpha")
    token = learner["token"]
    d1 = OfflineDevice("gd-d1", tmp_path / "d1.sqlite", client, token, "site-alpha", SECTION)
    d1.obtain_lease()
    d1.set_online(False)
    d1.save_progress_local("pack_dc", "lesson_xd", 20)
    d1.restart()
    assert d1.pending_count() >= 1
    d1.set_online(True)
    r1 = d1.sync_outbox()
    assert any(x.get("sync_status") == "acknowledged" for x in r1)

    d2 = OfflineDevice("gd-d2", tmp_path / "d2.sqlite", client, token, "site-alpha", SECTION)
    d2.obtain_lease()
    # Fresh second device: no local pending claiming sync without ACK.
    assert d2.pending_count() == 0
    assert d2.acknowledged_count() == 0
    pulled = d2.pull()
    assert any(p.get("lesson_id") == "lesson_xd" for p in pulled.get("lesson_progress") or [])

    # Offline mutation on d2 must stay pending until real ACK — no false synced.
    d2.set_online(False)
    d2.save_progress_local("pack_dc", "lesson_xd2", 35)
    assert d2.pending_count() >= 1
    assert d2.acknowledged_count() == 0
    d2.set_online(True)
    r2 = d2.sync_outbox()
    assert any(x.get("sync_status") == "acknowledged" for x in r2)
    assert d2.pending_count() == 0

    write_json(
        "GATE_D_OFFLINE_CROSS_DEVICE.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "checks": {
                "online_start": "PASS",
                "disconnect_durable": "PASS",
                "reboot_resume": "PASS",
                "reconnect_receipt": "PASS",
                "second_device": "PASS",
                "no_false_synced": "PASS",
            },
        },
    )
