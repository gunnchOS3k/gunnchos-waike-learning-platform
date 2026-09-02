"""Deterministic JSON helpers."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
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


def zip_date_time() -> tuple[int, int, int, int, int, int]:
    """Zip local date_time tuple derived from SOURCE_DATE_EPOCH when set."""
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        dt = datetime.now(tz=timezone.utc)
    else:
        dt = datetime.fromtimestamp(int(raw), tz=timezone.utc)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def zip_write_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=zip_date_time())
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix — avoid platform variance in zip headers
    zf.writestr(info, data)


def zip_write_file(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    zip_write_bytes(zf, arcname, src.read_bytes())
