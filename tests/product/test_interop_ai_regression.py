from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_interop_and_ai_regression_files_present() -> None:
    required = [
        ROOT / "tests" / "gate_c",
        ROOT / "tests" / "gate_b" / "test_ai_policy.py",
        ROOT / "tests" / "gate_b" / "test_ai_prompt_injection.py",
        ROOT / "tests" / "gate_b" / "test_ai_grade_safety.py",
        ROOT / "tests" / "gate_b" / "test_ai_context_isolation.py",
    ]
    for path in required:
        assert path.exists(), path
