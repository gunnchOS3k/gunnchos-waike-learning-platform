"""Deterministic JSON helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def dumps_canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def dump_canonical(path, obj: Any) -> None:
    path.write_text(dumps_canonical(obj), encoding="utf-8")


def source_date_epoch_utc() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is not None:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
