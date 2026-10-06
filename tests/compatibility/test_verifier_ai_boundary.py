"""Gate evidence must preserve the explicitly disabled external AI boundary."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("gate", ["c", "d"])
def test_verifier_respects_disabled_fake_ai(monkeypatch, gate):
    monkeypatch.setenv("WAIKE_ALLOW_FAKE_AI", "0")
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    command = next(line for line in makefile.splitlines() if f"scripts/verify_gate_{gate}.py" in line)
    assert "WAIKE_ALLOW_FAKE_AI:-0" in command
    tree = ast.parse((root / "scripts" / f"verify_gate_{gate}.py").read_text())
    values = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "WAIKE_ALLOW_FAKE_AI"
    ]
    assert len(values) == 1
    import os

    assert eval(compile(ast.Expression(values[0]), "verifier-env", "eval"), {"os": os}) == "0"
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI")
    assert eval(compile(ast.Expression(values[0]), "verifier-env", "eval"), {"os": os}) == "0"
