"""Pinned WAIKE registry loader — fail closed on unknown IDs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .compat import RejectionReason


class RegistryError(Exception):
    def __init__(self, reason: RejectionReason, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_pin(pin_path: Path | None = None) -> dict[str, Any]:
    path = pin_path or (repo_root() / "curriculum" / "registry" / "PIN.json")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_waike_root(pin: dict[str, Any] | None = None) -> Path:
    pin = pin or load_pin()
    candidates: list[Path] = []
    hint = pin.get("absolute_path_hint")
    if hint:
        candidates.append(Path(hint))
    rel = pin.get("source_path")
    if rel:
        candidates.append((repo_root() / rel).resolve())
    candidates.append(repo_root().parent / "waike-research-ops")
    for c in candidates:
        if not c.is_dir():
            continue
        if (c / "lessons" / "by_course").is_dir() or (
            c / "curriculum" / "taxonomy" / "eighteen_tracks.json"
        ).exists():
            return c
    raise RegistryError(RejectionReason.UNKNOWN_MODULE, f"WAIKE root not found; tried {candidates}")


def observed_waike_commit(waike_root: Path) -> str:
    """Return `git rev-parse HEAD` for the checked-out WAIKE source (fail closed)."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(waike_root), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise RegistryError(
            RejectionReason.PROVENANCE_MISMATCH,
            f"unable to read observed WAIKE HEAD at {waike_root}: {exc}",
        ) from exc
    sha = out.strip()
    if len(sha) < 40:
        raise RegistryError(
            RejectionReason.PROVENANCE_MISMATCH,
            f"observed WAIKE HEAD malformed: {sha!r}",
        )
    return sha


def verify_waike_provenance(pin: dict[str, Any] | None = None, waike_root: Path | None = None) -> dict[str, str]:
    """Abort when declared PIN commit differs from observed checkout HEAD."""
    pin = pin or load_pin()
    root = waike_root or resolve_waike_root(pin)
    declared = str(pin.get("pinned_commit") or "").strip()
    observed = observed_waike_commit(root)
    if not declared:
        raise RegistryError(RejectionReason.PROVENANCE_MISMATCH, "PIN.json missing pinned_commit")
    if declared != observed:
        raise RegistryError(
            RejectionReason.PROVENANCE_MISMATCH,
            f"declared_pinned_commit={declared} observed_source_commit={observed}",
        )
    return {
        "declared_pinned_commit": declared,
        "observed_source_commit": observed,
        "waike_root": str(root),
    }


def assert_signing_key_allowed(signing_key_path: Path, *, release_mode: bool = False) -> None:
    """Fail closed: TEST_ONLY keys cannot be used as production signing material."""
    name = signing_key_path.name
    text = ""
    try:
        text = signing_key_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass
    labeled_test = "TEST_ONLY" in name or "TEST_ONLY" in text[:200]
    if release_mode and labeled_test:
        raise RegistryError(
            RejectionReason.RELEASE_TEST_KEY_FORBIDDEN,
            f"release mode rejects TEST_ONLY signing key: {signing_key_path}",
        )
    if not release_mode and not labeled_test:
        # Development may use fixtures; require explicit TEST_ONLY labeling for committed fixtures.
        raise RegistryError(
            RejectionReason.RELEASE_TEST_KEY_FORBIDDEN,
            f"dev/test signing key must be explicitly labeled TEST_ONLY: {signing_key_path}",
        )

def load_taxonomy(waike_root: Path, pin: dict[str, Any] | None = None) -> dict[str, Any]:
    pin = pin or load_pin()
    preferred = [
        repo_root() / "curriculum" / "registry" / "CANONICAL_TRACK_REGISTRY.export.json",
        waike_root / "artifacts" / "taxonomy" / "CANONICAL_TRACK_REGISTRY.export.json",
        waike_root / "curriculum" / "taxonomy" / "eighteen_tracks.json",
        repo_root() / "curriculum" / "registry" / "eighteen_tracks.json",
    ]
    for path in preferred:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise RegistryError(RejectionReason.UNKNOWN_MODULE, "taxonomy file missing")


def resolve_module_id(raw_id: str, pin: dict[str, Any] | None = None) -> str:
    pin = pin or load_pin()
    allowed = set(pin.get("module_ids_allowed") or [])
    aliases = pin.get("aliases") or {}
    # GENERAL_IT is explicitly not a unique alias
    if raw_id == "GENERAL_IT" or raw_id in (pin.get("non_aliases") or {}):
        raise RegistryError(
            RejectionReason.UNKNOWN_MODULE,
            "GENERAL_IT is a multi-track package id, not a unique track alias",
        )
    candidate = aliases.get(raw_id, raw_id)
    # Evidence-backed package aliases from pin (not in PR1 allow-list unless allowed)
    evidence = pin.get("package_aliases_evidence_backed") or {}
    if candidate in evidence:
        candidate = evidence[candidate]
    if raw_id in evidence:
        candidate = evidence[raw_id]
    if candidate not in allowed:
        raise RegistryError(
            RejectionReason.UNKNOWN_MODULE,
            f"module '{raw_id}' not in explicit allow-list {sorted(allowed)}",
        )
    return candidate


def get_track(module_id: str, taxonomy: dict[str, Any]) -> dict[str, Any]:
    tracks = taxonomy.get("tracks") or taxonomy.get("canonical_tracks") or []
    for t in tracks:
        tid = t.get("track_id") or t.get("id")
        if tid == module_id:
            return t
    raise RegistryError(RejectionReason.UNKNOWN_MODULE, f"track {module_id} absent from taxonomy")
