"""course-compiler CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import compile_all, compile_module
from .registry import RegistryError, load_pin, repo_root, resolve_module_id
from .tracks import CANONICAL_TRACK_IDS
from .verify import verify_learner_pack


def _default_keys() -> tuple[Path, Path, Path]:
    keys = repo_root() / "contracts" / "fixtures" / "keys"
    return (
        keys / "TEST_ONLY_ed25519_private.key",
        keys / "TEST_ONLY_ed25519_public.key",
        keys / "TEST_ONLY_instructor_aes256.key",
    )


def _parse_tracks(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    return parts or None


def cmd_compile(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    try:
        report = compile_module(
            args.module_id,
            out_dir=out,
            signing_key_path=Path(args.signing_key) if args.signing_key else None,
            instructor_key_path=Path(args.instructor_key) if args.instructor_key else None,
        )
    except RegistryError as e:
        print(json.dumps({"ok": False, "reason": e.reason.value, "detail": e.detail}))
        return 2
    decision = verify_learner_pack(out, _default_keys()[1])
    print(json.dumps({"ok": decision.ok, "report": report, "verify": decision.to_dict()}, indent=2))
    return 0 if decision.ok else 1


def cmd_compile_all(args: argparse.Namespace) -> int:
    pin = load_pin()
    tracks = _parse_tracks(args.tracks)
    if tracks:
        try:
            tracks = [resolve_module_id(t, pin) for t in tracks]
        except RegistryError as e:
            print(json.dumps({"ok": False, "reason": e.reason.value, "detail": e.detail}))
            return 2
    out_root = Path(args.out).resolve()
    results = compile_all(
        tracks=tracks,
        out_root=out_root,
        signing_key_path=Path(args.signing_key) if args.signing_key else None,
        instructor_key_path=Path(args.instructor_key) if args.instructor_key else None,
    )
    verify_summary = {}
    vk = _default_keys()[1]
    for tid, payload in results["tracks"].items():
        if not payload.get("ok"):
            verify_summary[tid] = {"ok": False, "compile": False, "error": payload.get("error")}
            continue
        decision = verify_learner_pack(out_root / tid, vk)
        verify_summary[tid] = {"ok": decision.ok, "compile": True, "verify": decision.to_dict()}
        if not decision.ok:
            results["ok"] = False
    print(json.dumps({"ok": results["ok"], "verify": verify_summary, "failures": results["failures"]}, indent=2))
    return 0 if results["ok"] else 1


def cmd_verify(args: argparse.Namespace) -> int:
    key = Path(args.public_key) if args.public_key else _default_keys()[1]
    decision = verify_learner_pack(Path(args.pack), key)
    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.ok else 1


def cmd_list_tracks(_args: argparse.Namespace) -> int:
    pin = load_pin()
    allowed = pin.get("module_ids_allowed") or list(CANONICAL_TRACK_IDS)
    print(json.dumps({"tracks": allowed}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="course-compiler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="Compile a single track/module id")
    p.add_argument("module_id")
    p.add_argument("--out", default="pack_out")
    p.add_argument("--signing-key")
    p.add_argument("--instructor-key")
    p.add_argument(
        "--tracks",
        help="Ignored for single compile; accepted for CLI symmetry with compile-all",
    )
    p.set_defaults(func=cmd_compile)

    pa = sub.add_parser("compile-all", help="Compile all allow-listed tracks (or --tracks subset)")
    pa.add_argument("--out", default="pack_out_18")
    pa.add_argument("--tracks", help="Comma-separated track ids (optional subset)")
    pa.add_argument("--signing-key")
    pa.add_argument("--instructor-key")
    pa.set_defaults(func=cmd_compile_all)

    v = sub.add_parser("verify")
    v.add_argument("pack")
    v.add_argument("--public-key")
    v.set_defaults(func=cmd_verify)

    lt = sub.add_parser("list-tracks")
    lt.set_defaults(func=cmd_list_tracks)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
