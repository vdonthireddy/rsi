"""Offline deterministic proposer for the deadline job-scheduling RSI example."""

from __future__ import annotations

from typing import Any

from rsi_demo.evaluator import EvaluationReport
from rsi_demo.proposer import Proposal


_SCHED_V1_SJF = '''"""Active job-scheduling solver iteratively improved during RSI cycles."""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v1-shortest-job-first"


def plan_schedule(jobs: Sequence[tuple[str, float, float]]) -> list[str]:
    """Schedule shortest-duration jobs first (with deadline tie-break)."""
    if not jobs:
        return []
    ordered = sorted(jobs, key=lambda j: (j[1], j[2]))
    return [job_id for job_id, _, _ in ordered]
'''


_SCHED_V2_EDF = '''"""Active job-scheduling solver iteratively improved during RSI cycles."""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v2-earliest-deadline-first"


def plan_schedule(jobs: Sequence[tuple[str, float, float]]) -> list[str]:
    """Schedule jobs by earliest deadline first (with duration tie-break)."""
    if not jobs:
        return []
    ordered = sorted(jobs, key=lambda j: (j[2], j[1]))
    return [job_id for job_id, _, _ in ordered]
'''


_SCHED_V3_REGRESSION = '''"""Active job-scheduling solver iteratively improved during RSI cycles."""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v3-drop-long-jobs-regression"


def plan_schedule(jobs: Sequence[tuple[str, float, float]]) -> list[str]:
    """Flawed shortcut: drops long jobs to avoid lateness, violating completeness."""
    if not jobs:
        return []
    kept = [j for j in jobs if j[1] <= 4.0]
    ordered = sorted(kept, key=lambda j: (j[2], j[1]))
    return [job_id for job_id, _, _ in ordered]
'''


_SCHED_V3_LOCAL_SWAP = '''"""Active job-scheduling solver iteratively improved during RSI cycles."""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v3-edf-pairwise-swap"


def _total_lateness(seq: list[tuple[str, float, float]]) -> float:
    elapsed = 0.0
    lateness = 0.0
    for _, dur, due in seq:
        elapsed += dur
        if elapsed > due:
            lateness += elapsed - due
    return lateness


def plan_schedule(jobs: Sequence[tuple[str, float, float]]) -> list[str]:
    """Start from EDF and SJF seeds, then apply pairwise swap hill-climbing."""
    if not jobs:
        return []

    seeds = [
        sorted(jobs, key=lambda j: (j[2], j[1])),
        sorted(jobs, key=lambda j: (j[1], j[2])),
    ]
    best_seq = seeds[0]
    best_lat = _total_lateness(best_seq)

    for seed in seeds:
        seq = list(seed)
        cur_lat = _total_lateness(seq)
        improved = True
        while improved:
            improved = False
            for i in range(len(seq) - 1):
                for j in range(i + 1, len(seq)):
                    seq[i], seq[j] = seq[j], seq[i]
                    cand_lat = _total_lateness(seq)
                    if cand_lat + 1e-9 < cur_lat:
                        cur_lat = cand_lat
                        improved = True
                    else:
                        seq[i], seq[j] = seq[j], seq[i]
        if cur_lat < best_lat:
            best_lat = cur_lat
            best_seq = seq

    return [job_id for job_id, _, _ in best_seq]
'''


_SCHED_V4_PLATEAU = _SCHED_V3_LOCAL_SWAP.replace(
    'SOLVER_VERSION = "v3-edf-pairwise-swap"',
    'SOLVER_VERSION = "v4-plateau-noop"',
)


class SchedulerMockProposer:
    """Offline deterministic proposer for deadline job scheduling."""

    name = "mock-scheduler-offline"

    def __init__(self, include_regression_demo: bool = True) -> None:
        self.include_regression_demo = include_regression_demo

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict[str, Any]],
    ) -> Proposal:
        tried = {entry.get("proposed_version") for entry in history}

        if "v1-shortest-job-first" not in tried:
            return Proposal(
                version_label="v1-shortest-job-first",
                hypothesis="Run shortest jobs first to clear quick tasks before they pile up.",
                rationale=f"Input-order baseline fails on {len(report.failures)}/{report.total_cases} schedules.",
                target_failure_tags=("sjf", "ordering"),
                candidate_source=_SCHED_V1_SJF,
            )

        if "v2-earliest-deadline-first" not in tried:
            return Proposal(
                version_label="v2-earliest-deadline-first",
                hypothesis="Prioritize earliest-deadline-first (EDF) to respect due dates directly.",
                rationale="Pure SJF delays urgent medium tasks past their deadlines.",
                target_failure_tags=("edf",),
                candidate_source=_SCHED_V2_EDF,
            )

        if self.include_regression_demo and "v3-drop-long-jobs-regression" not in tried:
            return Proposal(
                version_label="v3-drop-long-jobs-regression",
                hypothesis="Skip long blocking jobs (>4h) to keep short tasks on time.",
                rationale="Attempting to eliminate blocker delays by filtering out slow tasks.",
                target_failure_tags=("local_swap",),
                candidate_source=_SCHED_V3_REGRESSION,
            )

        if "v3-edf-pairwise-swap" not in tried:
            return Proposal(
                version_label="v3-edf-pairwise-swap",
                hypothesis="Refine EDF/SJF seeds with pairwise swap search minimizing total lateness.",
                rationale=(
                    "Dropping long jobs broke completeness; pairwise swapping moves heavy blockers "
                    "behind quick tasks without dropping any job."
                ),
                target_failure_tags=("local_swap", "total_lateness"),
                candidate_source=_SCHED_V3_LOCAL_SWAP,
            )

        return Proposal(
            version_label="v4-plateau-noop",
            hypothesis="Attempt minor version bump at convergence plateau.",
            rationale="All schedules already achieve optimal total lateness.",
            target_failure_tags=(),
            candidate_source=_SCHED_V4_PLATEAU,
        )
