"""Machine-readable compatibility policy and typed rejection reasons."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RejectionReason(str, Enum):
    UNSIGNED_PACK = "UNSIGNED_PACK"
    TAMPERED_CONTENT = "TAMPERED_CONTENT"
    WRONG_ROLE = "WRONG_ROLE"
    INCOMPATIBLE_SCHEMA_MAJOR = "INCOMPATIBLE_SCHEMA_MAJOR"
    SCHEMA_DOWNGRADE = "SCHEMA_DOWNGRADE"
    MISSING_SIGNATURE = "MISSING_SIGNATURE"
    BAD_SIGNATURE = "BAD_SIGNATURE"
    UNKNOWN_MODULE = "UNKNOWN_MODULE"
    INSTRUCTOR_MATERIAL_IN_LEARNER = "INSTRUCTOR_MATERIAL_IN_LEARNER"
    PRIVATE_KEY_IN_LEARNER = "PRIVATE_KEY_IN_LEARNER"
    DECRYPT_FAILED = "DECRYPT_FAILED"
    PLATFORM_TOO_OLD = "PLATFORM_TOO_OLD"
    PLATFORM_TOO_NEW = "PLATFORM_TOO_NEW"
    VERIFY_BEFORE_TRUST = "VERIFY_BEFORE_TRUST"
    ONE_BIT_CORRUPTION = "ONE_BIT_CORRUPTION"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    RELEASE_TEST_KEY_FORBIDDEN = "RELEASE_TEST_KEY_FORBIDDEN"


@dataclass
class CompatDecision:
    ok: bool
    reason: RejectionReason | None = None
    detail: str = ""
    ui_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.reason is not None:
            d["reason"] = self.reason.value
            d["ui_code"] = self.ui_code or self.reason.value
        return d


PLATFORM_VERSION = "0.1.0"
SUPPORTED_CONTRACT_MAJORS = {
    "canonical_track_reference": 1,
    "course_module": 1,
    "learner_pack_manifest": 1,
    "instructor_pack_manifest": 1,
    "assessment": 1,
    "rubric": 1,
    "lab_environment": 1,
    "compatibility_manifest": 1,
    "package_signature_metadata": 1,
}


def parse_semver(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"invalid semver: {v}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def check_schema_version(contract_name: str, schema_version: str) -> CompatDecision:
    major, minor, patch = parse_semver(schema_version)
    expected = SUPPORTED_CONTRACT_MAJORS.get(contract_name)
    if expected is None:
        return CompatDecision(False, RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR, f"unknown contract {contract_name}")
    if major != expected:
        return CompatDecision(
            False,
            RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR,
            f"{contract_name} major {major} unsupported (expected {expected})",
        )
    if major < expected:
        return CompatDecision(False, RejectionReason.SCHEMA_DOWNGRADE, f"{contract_name} {schema_version}")
    return CompatDecision(True)


def check_compatibility_manifest(manifest: dict[str, Any], platform_version: str = PLATFORM_VERSION) -> CompatDecision:
    sv = manifest.get("schema_version", "0.0.0")
    decision = check_schema_version("compatibility_manifest", sv)
    if not decision.ok:
        return decision
    pmin = parse_semver(manifest["platform_min"])
    plat = parse_semver(platform_version)
    if plat < pmin:
        return CompatDecision(False, RejectionReason.PLATFORM_TOO_OLD, f"need >= {manifest['platform_min']}")
    pmax = manifest.get("platform_max_exclusive")
    if pmax:
        if plat >= parse_semver(pmax):
            return CompatDecision(False, RejectionReason.PLATFORM_TOO_NEW, f"need < {pmax}")
    for name, policy in manifest.get("contracts", {}).items():
        supported = SUPPORTED_CONTRACT_MAJORS.get(name)
        if supported is None or policy.get("major") != supported:
            return CompatDecision(
                False,
                RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR,
                f"contract {name} major mismatch",
            )
    return CompatDecision(True)


DEFAULT_COMPAT = {
    "schema_version": "1.0.0",
    "platform_min": "0.1.0",
    "platform_max_exclusive": None,
    "contracts": {k: {"major": v, "min_minor": 0} for k, v in SUPPORTED_CONTRACT_MAJORS.items()},
    "client_capabilities": ["ed25519_verify", "aes_gcm_envelope_db", "learner_pack_install"],
}
