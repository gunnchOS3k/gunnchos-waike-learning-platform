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


def _learner_root(pack_dir: Path) -> Path:
    return pack_dir / "learner"


def _pack_rel_files(pack_dir: Path) -> list[str]:
    man = json.loads((pack_dir / "learner_pack_manifest.json").read_text(encoding="utf-8"))
    return [e["path"] for e in (man.get("files") or [])]


def _first_matching(paths: list[str], *predicates) -> str | None:
    for p in paths:
        low = p.lower()
        if all(pred(low, p) for pred in predicates):
            return p
    return None


def _letter_options(choices: list[Any]) -> list[str]:
    return [chr(ord("a") + i) for i in range(len(choices))]


def _ensure_structural_rubric(conn, rubric_id: str, title: str, criteria_names: list[str]) -> str:
    conn.execute(
        "INSERT OR IGNORE INTO rubrics(rubric_id, schema_version, title, source_path, source_commit) "
        "VALUES (?,?,?,?,?)",
        (rubric_id, "1.0.0", title, "pack_runtime_registration", ""),
    )
    for idx, name in enumerate(criteria_names[:5] or ["evidence"]):
        criterion_id = f"{rubric_id}_c{idx}"
        conn.execute(
            "INSERT OR IGNORE INTO rubric_criteria(criterion_id, rubric_id, description, max_points, sort_order) "
            "VALUES (?,?,?,?,?)",
            (criterion_id, rubric_id, name.replace("_", " "), 4.0, idx),
        )
        for score in (4, 3, 2, 1, 0):
            conn.execute(
                "INSERT OR IGNORE INTO rubric_levels(level_id, criterion_id, score, label, description) "
                "VALUES (?,?,?,?,?)",
                (f"{criterion_id}_L{score}", criterion_id, float(score), f"Level {score}", ""),
            )
    return rubric_id


def _register_pack_assignment(
    conn,
    *,
    track_id: str,
    section_id: str,
    pack_dir: Path,
    rel_path: str,
) -> dict[str, Any]:
    import yaml

    learner = _learner_root(pack_dir)
    src = learner / rel_path
    body = ""
    title = f"{track_id} pack assignment"
    week = 1
    assignment_id = f"gb_{track_id.lower()}_{section_id}_a01"
    if rel_path.endswith((".yaml", ".yml")):
        meta = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        title = str(meta.get("assignment_title") or meta.get("title") or title)
        week = int(meta.get("week") or 1)
        body_candidate = None
        # Prefer paired markdown body when present (DIGITAL_CONFIDENCE layout).
        for cand in (
            learner / "assignment_bodies/by_course/digital_confidence/assignment_01.md",
            src.with_suffix(".md"),
        ):
            if cand.is_file():
                body_candidate = cand
                break
        body = body_candidate.read_text(encoding="utf-8") if body_candidate else json.dumps(meta, indent=2)
        criteria = [str(d) for d in (meta.get("deliverables") or [])] or ["response"]
    else:
        body = src.read_text(encoding="utf-8")
        first_line = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), title)
        title = first_line[:120] or title
        criteria = ["response"]

    # Prefer pack rubrics.json when present (digital_rc).
    rubric_id = f"rubric_gb_{track_id.lower()}"
    rubrics_json = None
    for p in _pack_rel_files(pack_dir):
        if p.lower().endswith("rubrics/rubrics.json"):
            rubrics_json = learner / p
            break
    if rubrics_json and rubrics_json.is_file():
        payload = json.loads(rubrics_json.read_text(encoding="utf-8"))
        first = payload[0] if isinstance(payload, list) and payload else None
        if isinstance(first, dict) and first.get("criteria"):
            rubric_id = f"rubric_gb_{track_id.lower()}_{first.get('rubric_id', 'pack')}"
            criteria = [str(c.get("name") or c.get("desc") or f"c{i}") for i, c in enumerate(first["criteria"])]

    _ensure_structural_rubric(conn, rubric_id, f"{track_id} pack rubric", criteria)

    outcome_id = f"outcome_gb_{track_id.lower()}"
    conn.execute(
        "INSERT OR IGNORE INTO outcomes(outcome_id, module_id, code, title, description) VALUES (?,?,?,?,?)",
        (
            outcome_id,
            track_id,
            f"{track_id[:12]}-PACK",
            f"{track_id} pack outcome",
            "Runtime registration outcome for Gate B pack-sourced assignment",
        ),
    )

    existing = conn.execute(
        "SELECT assignment_id FROM assignments WHERE assignment_id=?", (assignment_id,)
    ).fetchone()
    if existing:
        return {"assignment_id": assignment_id, "module_id": track_id, "source_path": rel_path}

    now = _now()
    conn.execute(
        """
        INSERT INTO assignments(
          assignment_id, module_id, schema_version, title, week, body_markdown,
          source_path, source_commit, rubric_id, outcome_id, mastery_threshold,
          portfolio_connection, revision_policy, current_version, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            assignment_id,
            track_id,
            "1.0.0",
            title,
            week,
            body,
            rel_path,
            "",
            rubric_id,
            outcome_id,
            3.0,
            0,
            "allowed_with_changelog",
            1,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO assignment_versions(
          assignment_version_id, assignment_id, version, title, body_markdown, rubric_id, content_hash, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            f"asgv_{assignment_id}",
            assignment_id,
            1,
            title,
            body,
            rubric_id,
            hashlib_sha256(title + "\n" + body),
            now,
        ),
    )
    return {"assignment_id": assignment_id, "module_id": track_id, "source_path": rel_path}


def hashlib_sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_quiz_answer_key(pack_dir: Path, quiz_id: str) -> dict[str, Any]:
    """Load answer key from decrypted instructor tree when present."""
    from course_compiler.verify import open_instructor_pack

    # Prefer on-disk instructor/ tree produced by open_instructor_pack / compile.
    for path in (pack_dir / "instructor").rglob("answer_keys.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        quizzes = data.get("quizzes") or {}
        if quiz_id in quizzes:
            return {"items": quizzes[quiz_id], "path": str(path.relative_to(pack_dir))}
    # Attempt decrypt if tree missing answer keys
    if AES.is_file():
        dec = open_instructor_pack(pack_dir, AES)
        if getattr(dec, "ok", False):
            for path in (pack_dir / "instructor").rglob("answer_keys.json"):
                data = json.loads(path.read_text(encoding="utf-8"))
                quizzes = data.get("quizzes") or {}
                if quiz_id in quizzes:
                    return {"items": quizzes[quiz_id], "path": str(path.relative_to(pack_dir))}
    return {"items": [], "path": ""}


def _register_pack_quiz(
    conn,
    *,
    track_id: str,
    section_id: str,
    site_id: str,
    instructor_id: str,
    pack_dir: Path,
    rel_path: str,
) -> dict[str, Any]:
    quiz_doc = json.loads((_learner_root(pack_dir) / rel_path).read_text(encoding="utf-8"))
    source_quiz_id = str(quiz_doc.get("quiz_id") or Path(rel_path).stem)
    quiz_id = f"gb_{track_id.lower()}_{section_id}_{source_quiz_id}"[:80]
    existing = conn.execute(
        "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
    ).fetchone()
    if existing:
        return {
            "quiz_id": quiz_id,
            "module_id": track_id,
            "source_path": rel_path,
            "item_ids": [
                r["item_id"]
                for r in conn.execute(
                    "SELECT item_id FROM quiz_items WHERE quiz_id=? ORDER BY ordinal", (quiz_id,)
                ).fetchall()
            ],
            "correct_responses": {},
        }

    ak = _load_quiz_answer_key(pack_dir, source_quiz_id)
    ak_by_id = {str(it.get("id")): it for it in (ak.get("items") or []) if isinstance(it, dict)}
    policies = {
        "availability_start": None,
        "availability_end": None,
        "attempt_limit": 3,
        "time_limit_minutes": 30,
        "autosave": True,
        "offline_eligible": True,
        "answer_visibility": "after_return",
        "feedback_mode": "delayed",
        "anonymous_grading": False,
        "module_id": track_id,
        "pack_source_path": rel_path,
    }
    answer_key: dict[str, Any] = {}
    correct_responses: dict[str, Any] = {}
    items = list(quiz_doc.get("items") or [])
    conn.execute(
        """
        INSERT INTO quiz_definitions(
          quiz_id, section_id, site_id, title, policies_json, answer_key_json,
          offline_eligible, high_integrity_timed, created_by, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            quiz_id,
            section_id,
            site_id,
            f"{track_id} {source_quiz_id}",
            json.dumps(policies),
            json.dumps({}),  # filled below
            1,
            0,
            instructor_id,
            _now(),
        ),
    )
    item_ids: list[str] = []
    for ord_, item in enumerate(items, start=1):
        item_id = f"{quiz_id}_{item.get('id') or ord_}"
        kind = str(item.get("kind") or "mcq").lower()
        choices = list(item.get("choices") or [])
        options = _letter_options(choices) if choices else []
        item_type = "single_choice" if kind in {"mcq", "single_choice", "multiple_choice"} else "short_response"
        prompt = str(item.get("stem") or item.get("prompt") or f"item {ord_}")
        conn.execute(
            """
            INSERT INTO quiz_items(
              item_id, quiz_id, ordinal, item_type, prompt, options_json, max_points, grading_mode
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (item_id, quiz_id, ord_, item_type, prompt, json.dumps(options), 1.0, "objective"),
        )
        item_ids.append(item_id)
        ak_item = ak_by_id.get(str(item.get("id")))
        if ak_item is not None and item_type == "single_choice" and options:
            idx = int(ak_item.get("answer_index") or 0)
            letter = options[idx] if 0 <= idx < len(options) else options[0]
            answer_key[item_id] = {"correct": [letter]}
            correct_responses[item_id] = letter
        elif item_type == "single_choice" and options:
            # No instructor key: still register; use first option as non-scored placeholder key
            answer_key[item_id] = {"correct": [options[0]]}
            correct_responses[item_id] = options[0]
        else:
            answer_key[item_id] = {"correct_normalized": "pack"}
            correct_responses[item_id] = "pack"

    conn.execute(
        "UPDATE quiz_definitions SET answer_key_json=? WHERE quiz_id=?",
        (json.dumps(answer_key), quiz_id),
    )
    return {
        "quiz_id": quiz_id,
        "module_id": track_id,
        "source_path": rel_path,
        "item_ids": item_ids,
        "correct_responses": correct_responses,
    }


def _register_pack_lab(
    conn,
    *,
    track_id: str,
    section_id: str,
    site_id: str,
    instructor_id: str,
    pack_dir: Path,
    rel_path: str,
) -> dict[str, Any]:
    src = _learner_root(pack_dir) / rel_path
    body = src.read_text(encoding="utf-8") if src.is_file() else rel_path
    lab_slug = Path(rel_path).parent.name if Path(rel_path).name.lower().startswith(
        ("readme", "lab_instructions")
    ) else Path(rel_path).stem
    lab_id = f"gb_{track_id.lower()}_{section_id}_{lab_slug}"[:80]
    existing = conn.execute("SELECT lab_id FROM lab_definitions WHERE lab_id=?", (lab_id,)).fetchone()
    if existing:
        return {"lab_id": lab_id, "module_id": track_id, "source_path": rel_path}
    title_line = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), lab_slug)
    conn.execute(
        """
        INSERT INTO lab_definitions(
          lab_id, section_id, site_id, title, mode, spec_json, runner_id,
          offline_eligible, created_by, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            lab_id,
            section_id,
            site_id,
            f"{track_id}: {title_line[:80]}",
            "MANUAL_EVIDENCE",
            json.dumps(
                {
                    "module_id": track_id,
                    "pack_source_path": rel_path,
                    "grading_mode": "manual",
                    "offline_eligible": True,
                    "expected_evidence": ["learner_notes"],
                    "steps": ["complete pack lab evidence"],
                }
            ),
            None,
            1,
            instructor_id,
            _now(),
        ),
    )
    return {"lab_id": lab_id, "module_id": track_id, "source_path": rel_path}


def register_pack_activities_into_hub(
    app,
    *,
    track_id: str,
    pack_dir: Path,
    section_id: str,
    site_id: str,
    instructor_id: str,
) -> dict[str, Any]:
    """Import representative activities from THIS track's pack into hub tables.

    Never uses DIGITAL_CONFIDENCE Gate A seeds as stand-ins for other tracks.
    Zero-count activity types are marked NOT_APPLICABLE.
    """
    counts = activity_counts_from_pack(pack_dir)
    paths = _pack_rel_files(pack_dir)
    conn = app.state.db
    out: dict[str, Any] = {
        "module_id": track_id,
        "activity_counts": counts,
        "assignment": None,
        "quiz": None,
        "lab": None,
        "lesson": None,
        "status": {
            "lessons": "NOT_APPLICABLE" if counts["lessons"] == 0 else "REGISTERED",
            "assignments": "NOT_APPLICABLE" if counts["assignments"] == 0 else "REGISTERED",
            "quizzes": "NOT_APPLICABLE" if counts["quizzes"] == 0 else "REGISTERED",
            "labs": "NOT_APPLICABLE" if counts["labs"] == 0 else "REGISTERED",
        },
    }

    def _in_dir(low: str, dirname: str) -> bool:
        return f"/{dirname}/" in f"/{low}"

    if counts["assignments"] > 0:
        rel = _first_matching(
            paths,
            lambda low, p: low.endswith((".yaml", ".yml")) and _in_dir(low, "assignments"),
        ) or _first_matching(
            paths,
            lambda low, p: (
                low.endswith(".md")
                and _in_dir(low, "assignments")
                and "assignment_bodies" not in low
            ),
        )
        assert rel, f"{track_id}: assignments>0 but no assignment file in pack"
        out["assignment"] = _register_pack_assignment(
            conn, track_id=track_id, section_id=section_id, pack_dir=pack_dir, rel_path=rel
        )
        assert out["assignment"]["module_id"] == track_id

    if counts["quizzes"] > 0:
        rel = _first_matching(
            paths,
            lambda low, p: _in_dir(low, "quizzes")
            and low.endswith(".json")
            and "answer_key" not in low,
        )
        assert rel, f"{track_id}: quizzes>0 but no quiz json in pack"
        out["quiz"] = _register_pack_quiz(
            conn,
            track_id=track_id,
            section_id=section_id,
            site_id=site_id,
            instructor_id=instructor_id,
            pack_dir=pack_dir,
            rel_path=rel,
        )
        assert out["quiz"]["module_id"] == track_id

    if counts["labs"] > 0:
        rel = _first_matching(
            paths,
            lambda low, p: _in_dir(low, "labs") and low.endswith("lab_instructions.md"),
        ) or _first_matching(
            paths,
            lambda low, p: _in_dir(low, "labs") and low.endswith("readme.md"),
        )
        assert rel, f"{track_id}: labs>0 but no lab instructions in pack"
        out["lab"] = _register_pack_lab(
            conn,
            track_id=track_id,
            section_id=section_id,
            site_id=site_id,
            instructor_id=instructor_id,
            pack_dir=pack_dir,
            rel_path=rel,
        )
        assert out["lab"]["module_id"] == track_id

    if counts["lessons"] > 0:
        rel = _first_matching(
            paths,
            lambda low, p: low.endswith("lesson.md") or low.endswith("lesson_plan.md"),
        )
        out["lesson"] = {
            "module_id": track_id,
            "source_path": rel or "",
            "status": "REGISTERED" if rel else "NOT_APPLICABLE",
        }
        if rel:
            out["status"]["lessons"] = "REGISTERED"

    conn.commit()
    return out


def install_track_into_hub(
    client: TestClient,
    track_id: str,
    pack_dir: Path,
    *,
    site_id: str = "site-alpha",
    admin_user: str = "admin-alpha",
    instructor_user: str = "instructor-alpha",
    learner_user: str = "learner-alpha",
    register_activities: bool = True,
) -> dict[str, Any]:
    """Verify pack signature, register package, create section, enroll, import pack activities."""
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

    registered = None
    if register_activities:
        registered = register_pack_activities_into_hub(
            app,
            track_id=track_id,
            pack_dir=pack_dir,
            section_id=section_id,
            site_id=site_id,
            instructor_id=user_id(inst),
        )

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
        "registered_activities": registered,
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
