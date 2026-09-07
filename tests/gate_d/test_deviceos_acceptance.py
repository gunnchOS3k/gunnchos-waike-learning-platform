"""Device OS pin + role mapping acceptance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from helpers import PINS, ROOT, write_json


def test_deviceos_pin_and_guardian_mapping():
    contract = json.loads(
        (ROOT / "contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json").read_text()
    )
    assert contract["device_os_sha"] == PINS["device_os"]
    mapping = contract["permissions_mapping"]
    assert mapping["guardian"]["device_os_role"] == "guardian"
    assert mapping["learner"]["device_os_role"] == "student"
    write_json(
        "GATE_D_DEVICEOS_ACCEPTANCE.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_os_pin": PINS["device_os"],
            "status": "PASS",
            "physical_quartet_claimed": False,
        },
    )
