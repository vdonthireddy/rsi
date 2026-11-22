"""Command-line interface for running and inspecting the RSI demo."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from rsi_demo.evaluator import evaluate_sandboxed
from rsi_demo.guardrails import HARD_MAX_CYCLES, GuardrailViolation, SandboxPaths
from rsi_demo.loop import RunSummary, run_rsi_loop
from rsi_demo.proposer import MockProposer, OpenAICompatibleProposer, Proposer


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _format_summary(summary: RunSummary) -> str:
    lines = [
        "=== Safe RSI Demo Run Summary ===",
        f"Run ID          : {summary.run_id}",
        f"Proposer        : {summary.proposer}",
        f"Cycles          : {summary.cycles_executed} (hard cap: {HARD_MAX_CYCLES})",
        f"Baseline        : {summary.baseline_version} | score={summary.baseline_score:.4f} | acc={summary.baseline_accuracy:.4f}",
        f"Final Best      : {summary.final_version} | score={summary.final_score:.4f} | acc={summary.final_accuracy:.4f}",
        f"Accepted / Back : {summary.accepted_cycles} accepted, {summary.rolled_back_cycles} rolled back",
        f"Artifacts       : {summary.run_dir}/",
        "",
        "Cycle Log:",
    ]
    for c in summary.cycles:
        after_s = f"{c.after_score:.4f}" if c.after_score is not None else "n/a"
        lines.append(
            f"  [Cycle {c.cycle}] {c.decision.upper():11s} | {c.proposed_version:<26s} | "
            f"score {c.before_score:.4f} -> {after_s} | cases={c.cases_passed or 'n/a'} | "
            f"unit={c.unit_tests_passed or 'n/a'}"
        )
        lines.append(f"            reason: {c.decision_reason}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rsi-demo",
        description="Run a safe, sandboxed Recursive Self-Improvement (RSI) loop.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=HARD_MAX_CYCLES,
        help=f"Number of improvement cycles to run (1..{HARD_MAX_CYCLES}, default: {HARD_MAX_CYCLES}).",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "llm"),
        default="mock",
        help="Proposal backend: 'mock' (offline deterministic) or 'llm' (OpenAI-compatible API).",
    )
    parser.add_argument(
        "--run-id",
        default="run-offline-default",
        help="Directory name under runs/ for deterministic logs and version snapshots.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Start from the current solver.py instead of resetting to baseline_solver.py first.",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="Reset solver.py back to baseline_solver.py and exit.",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Evaluate the current solver.py against the locked benchmark and exit.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_default_project_root(),
        help="Project root directory (defaults to repository root).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = SandboxPaths.from_project_root(args.project_root)

    if args.reset_only:
        baseline_source = paths.baseline_path.read_text(encoding="utf-8")
        paths.ensure_mutable_target(paths.solver_path).write_text(
            baseline_source, encoding="utf-8"
        )
        print("Reset src/rsi_demo/solver.py to v0-baseline.")
        return 0

    if args.eval_only:
        report = evaluate_sandboxed(paths.project_root)
        print(
            f"Solver: {report.solver_version} | score={report.composite_score:.4f} | "
            f"accuracy={report.accuracy:.4f} | cases={report.cases_passed}/{report.total_cases} | "
            f"unit_tests={report.unit_tests_passed}/{report.unit_tests_total} | "
            f"avg_latency={report.avg_latency_ms:.3f}ms"
        )
        if report.failures:
            print("Failing benchmark cases:")
            for f in report.failures:
                print(f"  - {f.case_id} (score={f.score:.3f}, tags={f.tags})")
        return 0

    try:
        proposer: Proposer
        if args.backend == "llm":
            proposer = OpenAICompatibleProposer()
        else:
            proposer = MockProposer(include_regression_demo=True)

        summary = run_rsi_loop(
            project_root=paths.project_root,
            max_cycles=args.cycles,
            proposer=proposer,
            run_id=args.run_id,
            reset_to_baseline=not args.no_reset,
        )
        print(_format_summary(summary))
        return 0
    except (GuardrailViolation, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
