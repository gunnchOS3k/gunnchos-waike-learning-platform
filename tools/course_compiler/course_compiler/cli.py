"""course-compiler CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import compile_module
from .registry import RegistryError, repo_root
from .verify import verify_learner_pack


def _default_keys() -> tuple[Path, Path, Path]:
    keys = repo_root() / "contracts" / "fixtures" / "keys"
    return (
        keys / "TEST_ONLY_ed25519_private.key",
        keys / "TEST_ONLY_ed25519_public.key",
        keys / "TEST_ONLY_instructor_aes256.key",
    )


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


def cmd_verify(args: argparse.Namespace) -> int:
    key = Path(args.public_key) if args.public_key else _default_keys()[1]
    decision = verify_learner_pack(Path(args.pack), key)
    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.ok else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="course-compiler")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("compile")
    p.add_argument("module_id")
    p.add_argument("--out", default="pack_out")
    p.add_argument("--signing-key")
    p.add_argument("--instructor-key")
    p.set_defaults(func=cmd_compile)
    v = sub.add_parser("verify")
    v.add_argument("pack")
    v.add_argument("--public-key")
    v.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
