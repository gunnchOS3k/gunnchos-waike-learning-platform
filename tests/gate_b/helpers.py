"""Importable Gate B helpers (fixtures stay in conftest.py)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.modules.identity import FIXTURE_PASSWORD

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))
if str(ROOT / "tools" / "course_compiler") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

KEYS = ROOT / "contracts" / "fixtures" / "keys"
VK = KEYS / "TEST_ONLY_ed25519_public.key"
AES = KEYS / "TEST_ONLY_instructor_aes256.key"
PACK_OUT_18 = ROOT / "pack_out_18"
MATRIX_PATH = ROOT / "reports" / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"

SITE_FOR_USER = {
    "admin-alpha": "site-alpha",
    "instructor-alpha": "site-alpha",
    "grader-alpha": "site-alpha",
    "learner-alpha": "site-alpha",
    "learner-beta": "site-alpha",
    "learner-a": "site-alpha",
    "admin-beta": "site-beta",
    "instructor-beta": "site-beta",
    "learner-gamma": "site-beta",
}

SECTION = "sec_alpha_dc_w01"


def login(client: TestClient, username: str, site_id: str | None = None) -> dict:
    sid = site_id or SITE_FOR_USER.get(username, "site-alpha")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": FIXTURE_PASSWORD, "site_id": sid},
    )
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def user_id(session: dict) -> str:
    return session["user"]["user_id"]


def waike_root() -> Path:
    import os

    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    raise FileNotFoundError("waike-research-ops missing")


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_matrix() -> dict[str, Any]:
    assert MATRIX_PATH.is_file(), f"missing matrix: {MATRIX_PATH}"
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def matrix_row(track_id: str) -> dict[str, Any]:
    data = load_matrix()
    for row in data.get("rows") or []:
        if row.get("track") == track_id:
            return row
    raise KeyError(track_id)


def activity_counts_from_pack(pack_dir: Path) -> dict[str, int]:
    man = json.loads((pack_dir / "learner_pack_manifest.json").read_text(encoding="utf-8"))
    inv = man.get("activity_inventory") or {}
    return {
        "lessons": int(inv.get("lessons") or 0),
        "assignments": int(inv.get("assignments") or 0),
        "quizzes": int(inv.get("quizzes") or 0),
        "labs": int(inv.get("labs") or 0),
        "rubrics": int(inv.get("rubrics") or 0),
    }


def pack_has_offline_marker(pack_dir: Path) -> bool:
    man = json.loads((pack_dir / "learner_pack_manifest.json").read_text(encoding="utf-8"))
    return any("offline_pack" in e.get("path", "") for e in (man.get("files") or []))


def resolve_pack_dir(track_id: str, packs_root: Path | None = None) -> Path:
    """Prefer shared pack_out_18 / fixture root; compile on demand otherwise."""
    from course_compiler.compiler import compile_module

    if packs_root is not None:
        candidate = packs_root / track_id
        if (candidate / "learner_pack_manifest.json").is_file():
            return candidate
    cached = PACK_OUT_18 / track_id
    if (cached / "learner_pack_manifest.json").is_file():
        return cached
    raise FileNotFoundError(
        f"pack for {track_id} missing under {packs_root or PACK_OUT_18}; "
        "session fixture should compile first"
    )


def ensure_compiled_pack(track_id: str, out_root: Path) -> Path:
    from course_compiler.compiler import compile_module

    out = out_root / track_id
    if (out / "learner_pack_manifest.json").is_file():
        return out
    compile_module(track_id, out_dir=out)
    return out


def verify_pack(pack_dir: Path) -> Any:
    from course_compiler.verify import verify_learner_pack

    return verify_learner_pack(pack_dir, VK)


def register_package(app, track_id: str, source_commit: str = "") -> str:
    package_id = f"pkg_gate_b_{track_id.lower()}"
    conn = app.state.db
    existing = conn.execute(
        "SELECT package_id FROM packages WHERE package_id=?", (package_id,)
    ).fetchone()
    if existing:
        return package_id
    conn.execute(
        """
        INSERT INTO packages(package_id, module_id, title, source_commit, immutable, created_at)
        VALUES (?,?,?,?,1,?)
        """,
        (package_id, track_id, f"{track_id} Gate B", source_commit, _now()),
    )
    conn.commit()
    return package_id


def install_track_into_hub(
    client: TestClient,
    track_id: str,
    pack_dir: Path,
    *,
    site_id: str = "site-alpha",
    admin_user: str = "admin-alpha",
    instructor_user: str = "instructor-alpha",
    learner_user: str = "learner-alpha",
) -> dict[str, Any]:
    """Verify pack signature, register package, create section, enroll, assert visibility."""
    decision = verify_pack(pack_dir)
    assert decision.ok, (track_id, decision.to_dict())

    app = client.app
    pin_commit = ""
    pin_path = ROOT / "curriculum" / "registry" / "PIN.json"
    if pin_path.is_file():
        pin_commit = json.loads(pin_path.read_text(encoding="utf-8")).get("pinned_commit") or ""

    package_id = register_package(app, track_id, source_commit=pin_commit)
    admin = login(client, admin_user, site_id=site_id)
    ah = auth_header(admin["token"])
    code = f"GB-{track_id[:12]}"
    created = client.post(
        "/api/v1/admin/sections",
        headers=ah,
        json={
            "code": code,
            "title": f"{track_id} Gate B section",
            "package_id": package_id,
            "published": True,
        },
    )
    assert created.status_code == 200, created.text
    section = created.json()
    section_id = section["section_id"]

    inst = login(client, instructor_user, site_id=site_id)
    learner = login(client, learner_user, site_id=site_id)
    assign = client.post(
        f"/api/v1/admin/sections/{section_id}/instructors",
        headers=ah,
        json={"user_id": user_id(inst)},
    )
    assert assign.status_code == 200, assign.text
    enroll = client.post(
        f"/api/v1/admin/sections/{section_id}/enrollments",
        headers=ah,
        json={"user_id": user_id(learner)},
    )
    assert enroll.status_code == 200, enroll.text

    home = client.get("/api/v1/learner/home", headers=auth_header(learner["token"]))
    assert home.status_code == 200, home.text
    home_rows = home.json()
    learner_visible = any(
        s["section_id"] == section_id
        and (s.get("package") or {}).get("module_id") == track_id
        for s in home_rows
    )

    dash = client.get(
        f"/api/v1/instructor/sections/{section_id}/dashboard",
        headers=auth_header(inst["token"]),
    )
    instructor_visible = dash.status_code == 200
    if instructor_visible:
        pkg = (dash.json().get("section") or {}).get("package") or {}
        instructor_visible = pkg.get("module_id") == track_id

    # Instructor pack present?
    im = pack_dir / "instructor_pack_manifest.json"
    instructor_files = 0
    if im.is_file():
        instructor_files = len(json.loads(im.read_text(encoding="utf-8")).get("files") or [])

    return {
        "track_id": track_id,
        "pack_dir": pack_dir,
        "package_id": package_id,
        "section_id": section_id,
        "verification_ok": True,
        "learner_visible": learner_visible,
        "instructor_visible": instructor_visible,
        "instructor_file_count": instructor_files,
        "activity_counts": activity_counts_from_pack(pack_dir),
        "offline_pack": pack_has_offline_marker(pack_dir),
        "learner_token": learner["token"],
        "instructor_token": inst["token"],
        "admin_token": admin["token"],
        "learner_user_id": user_id(learner),
        "instructor_user_id": user_id(inst),
    }


def criterion_scores(assignment_detail: dict, points: float) -> list[dict]:
    out = []
    for c in assignment_detail["rubric"]["criteria"]:
        level = next((lv for lv in c["levels"] if abs(lv["score"] - points) < 1e-9), None)
        out.append(
            {
                "criterion_id": c["criterion_id"],
                "points": points,
                "level_id": level["level_id"] if level else None,
                "comment": f"gate-b p={points}",
            }
        )
    return out
