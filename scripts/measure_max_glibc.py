#!/usr/bin/env python3
"""Measure maximum GLIBC symbol version required by an ELF binary.

Fail-closed helper for the Debian 12 / glibc-2.36 aarch64 artifact gate.
Uses objdump/readelf evidence only — does not trust container labels.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_GLIBC_RE = re.compile(r"GLIBC_([0-9]+(?:\.[0-9]+)+)")


def _parse_ver(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def _collect_from_text(text: str) -> set[str]:
    return set(_GLIBC_RE.findall(text))


def measure(elf: Path) -> tuple[str | None, dict[str, str]]:
    evidence: dict[str, str] = {}
    versions: set[str] = set()

    for tool, args in (
        ("objdump", ["-T", str(elf)]),
        ("readelf", ["-V", str(elf)]),
        ("readelf", ["--dyn-syms", str(elf)]),
    ):
        key = f"{tool}_{'_'.join(args[:-1]).lstrip('-').replace('-', '_')}"
        try:
            out = subprocess.check_output(
                [tool, *args], text=True, stderr=subprocess.STDOUT
            )
        except FileNotFoundError as exc:
            raise SystemExit(f"FATAL: required ELF tool missing: {tool}") from exc
        except subprocess.CalledProcessError as exc:
            out = (exc.output or "") + f"\n# exit={exc.returncode}"
        evidence[key] = out
        versions |= _collect_from_text(out)

    max_ver = max(versions, key=_parse_ver) if versions else None
    return max_ver, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument(
        "--max-allowed",
        default="2.36",
        help="Fail if measured max GLIBC exceeds this version (default: 2.36)",
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        help="Write raw objdump/readelf evidence to this path",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print measured max and exit 0 even if over limit",
    )
    args = parser.parse_args()

    if not args.elf.is_file():
        print(f"FATAL: missing ELF {args.elf}", file=sys.stderr)
        return 2

    max_ver, evidence = measure(args.elf)
    if args.evidence_out is not None:
        parts = [f"# elf={args.elf}\n# measured_max_glibc={max_ver or 'NONE'}\n"]
        for name, body in evidence.items():
            parts.append(f"\n===== {name} =====\n")
            parts.append(body)
            if not body.endswith("\n"):
                parts.append("\n")
        args.evidence_out.write_text("".join(parts), encoding="utf-8")

    if max_ver is None:
        print("FATAL: no GLIBC_* versions found in ELF dynamic symbols", file=sys.stderr)
        return 2

    print(max_ver)
    if args.print_only:
        return 0

    if _parse_ver(max_ver) > _parse_ver(args.max_allowed):
        print(
            f"FATAL: measured max GLIBC_{max_ver} exceeds allowed "
            f"GLIBC_{args.max_allowed}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
