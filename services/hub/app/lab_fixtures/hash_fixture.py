"""Trusted LOCAL_SOFTWARE lab fixture: deterministic digest of the learner's input file.

Repo-controlled and referenced by id from the lab definition. The learner supplies the
contents of ``input.txt`` in the temp workdir and nothing else — never the command,
never the interpreter, never an argument.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MAX_INPUT_BYTES = 64 * 1024


def main() -> int:
    workdir = Path.cwd()
    src = workdir / "input.txt"
    if not src.is_file():
        print(json.dumps({"error": "MISSING_INPUT"}), file=sys.stderr)
        return 2
    data = src.read_bytes()[:MAX_INPUT_BYTES]
    digest = hashlib.sha256(data).hexdigest()
    # Sorted keys + no whitespace so identical input yields byte-identical stdout.
    sys.stdout.write(
        json.dumps(
            {"fixture": "hash_fixture_v1", "input_bytes": len(data), "input_sha256": digest},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
