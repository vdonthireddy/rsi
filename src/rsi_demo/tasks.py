"""Task registry separating the generic RSI engine from task-specific targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rsi_demo.evaluator import EvaluationReport, evaluate_sandboxed
from rsi_demo.proposer import MockProposer, OpenAICompatibleProposer, Proposer
from rsi_demo.route_evaluator import evaluate_route_sandboxed
from rsi_demo.route_proposer import RouteMockProposer
from rsi_demo.scheduler_evaluator import evaluate_scheduler_sandboxed
from rsi_demo.scheduler_proposer import SchedulerMockProposer


@dataclass(frozen=True)
class TaskSpec:
    """Defines the mutable target file, locked evaluator, and entrypoint for an RSI task."""

    name: str
    solver_rel_path: str
    baseline_rel_path: str
    evaluator_rel_path: str
    unit_test_rel_path: str
    entrypoint: str
    evaluate_fn: Callable[[Path, float], EvaluationReport]
    mock_proposer_factory: Callable[[], Proposer]


TASKS: dict[str, TaskSpec] = {
    "text_parser": TaskSpec(
        name="text_parser",
        solver_rel_path="src/rsi_demo/solver.py",
        baseline_rel_path="src/rsi_demo/baseline_solver.py",
        evaluator_rel_path="src/rsi_demo/evaluator.py",
        unit_test_rel_path="tests/test_solver.py",
        entrypoint="extract_record",
        evaluate_fn=evaluate_sandboxed,
        mock_proposer_factory=lambda: MockProposer(include_regression_demo=True),
    ),
    "route_optimizer": TaskSpec(
        name="route_optimizer",
        solver_rel_path="src/rsi_demo/route_solver.py",
        baseline_rel_path="src/rsi_demo/baseline_route_solver.py",
        evaluator_rel_path="src/rsi_demo/route_evaluator.py",
        unit_test_rel_path="tests/test_route_solver.py",
        entrypoint="plan_route",
        evaluate_fn=evaluate_route_sandboxed,
        mock_proposer_factory=lambda: RouteMockProposer(include_regression_demo=True),
    ),
    "task_scheduler": TaskSpec(
        name="task_scheduler",
        solver_rel_path="src/rsi_demo/scheduler_solver.py",
        baseline_rel_path="src/rsi_demo/baseline_scheduler_solver.py",
        evaluator_rel_path="src/rsi_demo/scheduler_evaluator.py",
        unit_test_rel_path="tests/test_scheduler_solver.py",
        entrypoint="plan_schedule",
        evaluate_fn=evaluate_scheduler_sandboxed,
        mock_proposer_factory=lambda: SchedulerMockProposer(include_regression_demo=True),
    ),
}


def get_task_spec(task_name: str) -> TaskSpec:
    """Return the TaskSpec for `task_name` or raise ValueError."""
    if task_name not in TASKS:
        raise ValueError(f"Unknown task '{task_name}'. Available: {', '.join(sorted(TASKS))}")
    return TASKS[task_name]


def build_proposer(task_name: str, backend: str) -> Proposer:
    """Instantiate either the task's offline mock proposer or the LLM proposer."""
    spec = get_task_spec(task_name)
    if backend == "llm":
        return OpenAICompatibleProposer()
    if backend == "mock":
        return spec.mock_proposer_factory()
    raise ValueError(f"Unknown backend '{backend}'. Expected 'mock' or 'llm'.")
