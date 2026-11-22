"""Locked evaluation harness for the deadline job-scheduling RSI example."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from rsi_demo.evaluator import CaseFailure, EvaluationReport


@dataclass(frozen=True)
class SchedulerBenchmarkCase:
    """Single locked scheduling benchmark case."""

    case_id: str
    tags: tuple[str, ...]
    # Each job: (job_id, duration_hours, deadline_hour)
    jobs: tuple[tuple[str, float, float], ...]
    optimal_total_lateness: float


SCHEDULER_BENCHMARK_CASES: tuple[SchedulerBenchmarkCase, ...] = (
    SchedulerBenchmarkCase(
        case_id="reversed_deadlines",
        tags=("edf", "ordering"),
        jobs=(
            ("report", 2.0, 10.0),
            ("slides", 2.0, 6.0),
            ("email", 1.0, 2.0),
            ("invoice", 3.0, 5.0),
        ),
        optimal_total_lateness=0.0,
    ),
    SchedulerBenchmarkCase(
        case_id="urgent_short_tasks",
        tags=("sjf", "edf"),
        jobs=(
            ("big_refactor", 6.0, 12.0),
            ("hotfix_a", 1.0, 2.0),
            ("hotfix_b", 1.0, 3.0),
            ("hotfix_c", 1.0, 4.0),
        ),
        optimal_total_lateness=0.0,
    ),
    SchedulerBenchmarkCase(
        case_id="heavy_blocker_trap",
        tags=("local_swap", "total_lateness"),
        # Doing the 8h task first (deadline 4) makes all three 2h tasks (deadlines 6, 7, 8) late.
        jobs=(
            ("migration", 8.0, 4.0),
            ("sync_a", 2.0, 6.0),
            ("sync_b", 2.0, 7.0),
            ("sync_c", 2.0, 8.0),
        ),
        optimal_total_lateness=10.0,
    ),
    SchedulerBenchmarkCase(
        case_id="mixed_errands",
        tags=("edf", "local_swap"),
        jobs=(
            ("laundry", 4.0, 7.0),
            ("groceries", 2.0, 3.0),
            ("call_bank", 1.0, 2.0),
            ("cook", 2.0, 5.0),
            ("clean", 3.0, 10.0),
        ),
        optimal_total_lateness=4.0,
    ),
    SchedulerBenchmarkCase(
        case_id="tight_sprint",
        tags=("local_swap", "total_lateness"),
        jobs=(
            ("t1", 5.0, 3.0),
            ("t2", 1.0, 4.0),
            ("t3", 2.0, 5.0),
            ("t4", 2.0, 6.0),
            ("t5", 4.0, 12.0),
        ),
        optimal_total_lateness=9.0,
    ),
    SchedulerBenchmarkCase(
        case_id="already_tight_zero",
        tags=("edf",),
        jobs=(
            ("j3", 3.0, 6.0),
            ("j1", 1.0, 1.0),
            ("j4", 2.0, 8.0),
            ("j2", 2.0, 3.0),
        ),
        optimal_total_lateness=0.0,
    ),
)


def compute_total_lateness(
    jobs: tuple[tuple[str, float, float], ...],
    order: list[str],
) -> float:
    """Compute sum of max(0, finish_time - deadline) for a valid schedule."""
    job_map = {job_id: (dur, due) for job_id, dur, due in jobs}
    elapsed = 0.0
    total_lateness = 0.0
    for job_id in order:
        dur, due = job_map[job_id]
        elapsed += dur
        if elapsed > due:
            total_lateness += elapsed - due
    return total_lateness


def score_schedule(case: SchedulerBenchmarkCase, order: object) -> tuple[float, str | None]:
    """Return (score in [0.0, 1.0], error_or_none)."""
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        return 0.0, "Schedule must be a list of job ID strings."
    expected_ids = [j[0] for j in case.jobs]
    if len(order) != len(expected_ids) or set(order) != set(expected_ids):
        return 0.0, "Schedule must include every job exactly once."

    lateness = compute_total_lateness(case.jobs, order)
    # Use (1 + optimal) / (1 + actual) so 0-lateness optimal cases score smoothly in (0, 1].
    score = min(1.0, (1.0 + case.optimal_total_lateness) / (1.0 + lateness))
    return round(score, 6), None


def _run_scheduler_unit_tests(project_root: Path) -> tuple[int, int, list[str]]:
    tests_dir = project_root / "tests"
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(tests_dir), pattern="test_scheduler_solver.py")
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        runner = unittest.TextTestRunner(stream=devnull, verbosity=0)
        result = runner.run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = max(0, total - failed)
    errors = [
        f"{test}: {trace.strip().splitlines()[-1]}"
        for test, trace in (result.failures + result.errors)
    ]
    return passed, total, errors


def evaluate_scheduler_in_process(
    project_root: Path,
    latency_repeats: int = 10,
) -> EvaluationReport:
    """Evaluate `rsi_demo.scheduler_solver` in the active process."""
    src_dir = str((project_root / "src").resolve())
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from rsi_demo import scheduler_solver as solver_mod  # noqa: PLC0415

    solver_version = str(getattr(solver_mod, "SOLVER_VERSION", "unknown"))
    plan_fn = solver_mod.plan_schedule

    case_scores: list[float] = []
    latencies_ms: list[float] = []
    failures: list[CaseFailure] = []
    cases_passed = 0

    for case in SCHEDULER_BENCHMARK_CASES:
        actual: list[str] | None = None
        err: str | None = None
        start = time.perf_counter()
        try:
            for _ in range(max(1, latency_repeats)):
                actual = plan_fn(list(case.jobs))
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        elapsed_ms = ((time.perf_counter() - start) * 1000.0) / max(1, latency_repeats)
        latencies_ms.append(elapsed_ms)

        if err is not None:
            case_score = 0.0
        else:
            case_score, err = score_schedule(case, actual)

        case_scores.append(case_score)
        if case_score >= 0.99:
            cases_passed += 1
        else:
            lateness = (
                compute_total_lateness(case.jobs, actual)
                if err is None and isinstance(actual, list)
                else None
            )
            failures.append(
                CaseFailure(
                    case_id=case.case_id,
                    tags=list(case.tags),
                    input_text=f"{len(case.jobs)} jobs (optimal_lateness={case.optimal_total_lateness:.1f}h)",
                    expected={"optimal_total_lateness": case.optimal_total_lateness},
                    actual={"order": actual, "total_lateness": lateness},
                    score=case_score,
                    error=err,
                )
            )

    ut_passed, ut_total, ut_errors = _run_scheduler_unit_tests(project_root)
    ut_pass_rate = (ut_passed / ut_total) if ut_total > 0 else 0.0

    total_cases = len(SCHEDULER_BENCHMARK_CASES)
    accuracy = sum(case_scores) / total_cases
    case_pass_rate = cases_passed / total_cases
    sorted_lat = sorted(latencies_ms)
    p95_idx = min(len(sorted_lat) - 1, int(0.95 * (len(sorted_lat) - 1)))
    avg_latency_ms = sum(latencies_ms) / len(latencies_ms)
    p95_latency_ms = sorted_lat[p95_idx]
    composite_score = round(0.85 * accuracy + 0.15 * case_pass_rate, 6)

    return EvaluationReport(
        solver_version=solver_version,
        accuracy=round(accuracy, 6),
        case_pass_rate=round(case_pass_rate, 6),
        cases_passed=cases_passed,
        total_cases=total_cases,
        unit_test_pass_rate=round(ut_pass_rate, 6),
        unit_tests_passed=ut_passed,
        unit_tests_total=ut_total,
        avg_latency_ms=round(avg_latency_ms, 4),
        p95_latency_ms=round(p95_latency_ms, 4),
        composite_score=composite_score,
        failures=failures,
        unit_test_errors=ut_errors,
    )


def evaluate_scheduler_sandboxed(
    project_root: Path,
    timeout_seconds: float = 10.0,
) -> EvaluationReport:
    """Run scheduler evaluation in a fresh isolated subprocess with timeout protection."""
    root = Path(project_root).resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = str((root / "src").resolve())

    proc = subprocess.run(
        [sys.executable, "-m", "rsi_demo.scheduler_evaluator", "--worker", str(root)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Scheduler evaluation subprocess failed (code {proc.returncode}): {proc.stderr.strip()}"
        )
    payload = json.loads(proc.stdout)
    failures = [CaseFailure(**item) for item in payload.pop("failures", [])]
    return EvaluationReport(failures=failures, **payload)


def _main_worker() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        root = Path(sys.argv[2]).resolve()
        report = evaluate_scheduler_in_process(root)
        print(json.dumps(report.to_dict()))
        return 0
    print("Usage: python -m rsi_demo.scheduler_evaluator --worker <project_root>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main_worker())
