"""Unit tests for sandbox boundaries, AST safety, tamper detection, and rollbacks."""

from __future__ import annotations

from pathlib import Path
import unittest

from rsi_demo.guardrails import (
    HARD_MAX_CYCLES,
    GuardrailViolation,
    LockedFileManifest,
    SandboxPaths,
    TamperDetectedError,
    check_candidate_acceptance,
    validate_candidate_ast,
    validate_max_cycles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestGuardrails(unittest.TestCase):
    def test_sandbox_blocks_outside_paths_and_locked_writes(self) -> None:
        paths = SandboxPaths.from_project_root(PROJECT_ROOT)
        with self.assertRaises(GuardrailViolation):
            paths.ensure_within_sandbox(PROJECT_ROOT.parent / "outside.txt")
        with self.assertRaises(GuardrailViolation):
            paths.ensure_mutable_target(paths.evaluator_path)
        with self.assertRaises(GuardrailViolation):
            paths.ensure_mutable_target(paths.tests_dir / "test_solver.py")

        self.assertEqual(paths.ensure_mutable_target(paths.solver_path), paths.solver_path)

    def test_hard_iteration_cap(self) -> None:
        self.assertEqual(validate_max_cycles(1), 1)
        self.assertEqual(validate_max_cycles(HARD_MAX_CYCLES), HARD_MAX_CYCLES)
        for bad in (0, -2, HARD_MAX_CYCLES + 1, True):
            with self.assertRaises(GuardrailViolation):
                validate_max_cycles(bad)  # type: ignore[arg-type]

    def test_ast_safety_rejects_dangerous_code(self) -> None:
        bad_candidates = [
            "import os\ndef extract_record(text: str):\n    return {}\n",
            "from subprocess import run\ndef extract_record(text: str):\n    return {}\n",
            "def extract_record(text: str):\n    return eval(text)\n",
            "def extract_record(text: str):\n    open('x', 'w')\n    return {}\n",
            "def extract_record(text: str):\n    return ().__class__.__subclasses__()\n",
            "def wrong_name(text: str):\n    return {}\n",
            "def extract_record(text: str)\n    return {}\n",  # syntax error
        ]
        for source in bad_candidates:
            with self.assertRaises(GuardrailViolation):
                validate_candidate_ast(source)

    def test_tamper_detection_catches_locked_file_edit(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            locked = Path(tmp) / "locked_eval.py"
            locked.write_text("SCORE = 1\n", encoding="utf-8")
            manifest = LockedFileManifest([locked])
            manifest.verify()

            locked.write_text("SCORE = 999\n", encoding="utf-8")
            with self.assertRaises(TamperDetectedError):
                manifest.verify()

    def test_acceptance_gate_enforces_all_conditions(self) -> None:
        ok, _ = check_candidate_acceptance(0.5, 0.5, 0.7, 0.7, 1.0, 1.2)
        self.assertTrue(ok)

        bad_ut, _ = check_candidate_acceptance(0.5, 0.5, 0.9, 0.9, 0.8, 1.2)
        self.assertFalse(bad_ut)

        bad_lat, _ = check_candidate_acceptance(0.5, 0.5, 0.9, 0.9, 1.0, 99.0)
        self.assertFalse(bad_lat)

        bad_reg, _ = check_candidate_acceptance(0.5, 0.6, 0.7, 0.55, 1.0, 1.2)
        self.assertFalse(bad_reg)

        no_gain, _ = check_candidate_acceptance(0.8, 0.8, 0.8, 0.8, 1.0, 1.2)
        self.assertFalse(no_gain)


if __name__ == "__main__":
    unittest.main()
