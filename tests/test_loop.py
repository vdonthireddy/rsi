"""End-to-end tests for the bounded RSI loop, logging, and rollback behavior."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from rsi_demo.evaluator import EvaluationReport
from rsi_demo.loop import run_rsi_loop
from rsi_demo.proposer import MockProposer, Proposal


REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_sandbox_project(dest: Path) -> Path:
    shutil.copytree(REPO_ROOT / "src", dest / "src")
    shutil.copytree(REPO_ROOT / "tests", dest / "tests")
    return dest


class _RogueASTProposer:
    name = "rogue-ast-test"

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict],
    ) -> Proposal:
        return Proposal(
            version_label="rogue-os-import",
            hypothesis="Attempt to import os and tamper with tests.",
            rationale="Adversarial guardrail test.",
            target_failure_tags=("security",),
            candidate_source=(
                "import os\n"
                "def extract_record(text: str):\n"
                "    return {'hacked': os.getcwd()}\n"
            ),
        )


class TestRSILoop(unittest.TestCase):
    def test_offline_5_cycle_loop_improves_rolls_back_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = _copy_sandbox_project(Path(tmp))
            summary = run_rsi_loop(
                project_root=sandbox,
                max_cycles=5,
                proposer=MockProposer(include_regression_demo=True),
                run_id="test-run-01",
            )

            self.assertEqual(summary.cycles_executed, 5)
            self.assertEqual(summary.baseline_version, "v0-baseline")
            self.assertEqual(summary.final_version, "v3-quote-aware-aliasing")
            self.assertGreater(summary.final_score, summary.baseline_score)
            self.assertEqual(summary.final_score, 1.0)
            self.assertEqual(summary.final_accuracy, 1.0)
            self.assertEqual(summary.accepted_cycles, 3)
            self.assertEqual(summary.rolled_back_cycles, 2)

            decisions = [c.decision for c in summary.cycles]
            # Cycle 1 accepted, Cycle 2 accepted, Cycle 3 regression rolled back,
            # Cycle 4 accepted (1.0), Cycle 5 plateau rolled back.
            self.assertEqual(
                decisions,
                ["accepted", "accepted", "rolled_back", "accepted", "rolled_back"],
            )

            run_dir = sandbox / "runs" / "test-run-01"
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "cycles.jsonl").exists())
            self.assertTrue((run_dir / "versions" / "best_solver.py").exists())

            jsonl_lines = (run_dir / "cycles.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(jsonl_lines), 5)
            parsed_cycle_3 = json.loads(jsonl_lines[2])
            self.assertEqual(parsed_cycle_3["decision"], "rolled_back")
            self.assertIn("Unit tests failed", parsed_cycle_3["decision_reason"])

            # Verify deterministic reproducibility across identical runs.
            summary_repeat = run_rsi_loop(
                project_root=sandbox,
                max_cycles=5,
                proposer=MockProposer(include_regression_demo=True),
                run_id="test-run-02",
            )
            self.assertEqual(summary.final_score, summary_repeat.final_score)
            self.assertEqual(
                [c.candidate_sha256 for c in summary.cycles],
                [c.candidate_sha256 for c in summary_repeat.cycles],
            )

    def test_rogue_ast_proposal_is_blocked_without_modifying_solver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = _copy_sandbox_project(Path(tmp))
            baseline_template = (sandbox / "src" / "rsi_demo" / "baseline_solver.py").read_text(
                encoding="utf-8"
            )
            summary = run_rsi_loop(
                project_root=sandbox,
                max_cycles=1,
                proposer=_RogueASTProposer(),
                run_id="rogue-test",
            )
            solver_after = (sandbox / "src" / "rsi_demo" / "solver.py").read_text(
                encoding="utf-8"
            )
            self.assertEqual(baseline_template, solver_after)
            self.assertEqual(summary.rolled_back_cycles, 1)
            self.assertFalse(summary.cycles[0].ast_check_passed)


if __name__ == "__main__":
    unittest.main()
