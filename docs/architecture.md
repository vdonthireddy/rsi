# Technical Architecture

This document details the internal architecture, safety boundaries, scoring mathematics, and design trade-offs of the **Safe RSI Demo**.

---

## 1. Module Responsibilities

| Module | Mutability During Run | Responsibility |
| --- | --- | --- |
| `src/rsi_demo/baseline_solver.py` | **Locked** (SHA-256 verified) | Immutable `v0-baseline` implementation used to initialize/reset runs. |
| `src/rsi_demo/solver.py` | **Mutable** (only target code file) | Active `extract_record(text: str) -> dict` module rewritten and rolled back across cycles. |
| `src/rsi_demo/guardrails.py` | **Locked** (SHA-256 verified) | Enforces path containment, `HARD_MAX_CYCLES = 5`, AST safety rules, SHA-256 manifest checks, and acceptance criteria. |
| `src/rsi_demo/evaluator.py` | **Locked** (SHA-256 verified) | Defines the 15 fixed `BENCHMARK_CASES`, runs `tests/test_solver.py`, measures latency, and executes inside an isolated subprocess (`--worker`). |
| `src/rsi_demo/proposer.py` | Read-only orchestrator component | Defines `Proposer` protocol, offline `MockProposer`, and optional `OpenAICompatibleProposer`. |
| `src/rsi_demo/loop.py` | Read-only orchestrator component | Coordinates the cycle loop, rollback on failure/regression, version snapshots, and JSONL/JSON logging. |
| `src/rsi_demo/cli.py` | Entry point | Exposes `--cycles`, `--backend`, `--run-id`, `--reset-only`, `--eval-only`, and `--no-reset`. |

---

## 2. Control & Data Flow

```text
  [baseline_solver.py] ──(init)──▶ [solver.py]
                                        │
                                        ▼
                            ┌──▶ [Locked Evaluator] (subprocess, 10s timeout)
                            │      • 15 benchmark cases
                            │      • tests/test_solver.py (unittest)
                            │           │
                            │           ▼
                            │    [EvaluationReport + CaseFailures]
                            │           │
                            │           ▼
                            │    [Proposer (Mock or LLM)]
                            │           │
                            │           ▼
                            │    [AST Safety Check] ──(fail)──▶ Reject & Log (never written)
                            │           │ (pass)
                            │           ▼
                            │    Write candidate to solver.py
                            │           │
                            │           ▼
                            │    [Subprocess Eval + SHA-256 Manifest Verify]
                            │           │
                            │           ▼
                            │    [Acceptance Gate]
                            │      ├──(pass)──▶ Keep & snapshot accepted version
                            └──────┴──(fail)──▶ Restore best_source (rollback) & log reason
```

---

## 3. Scoring & Acceptance Math

### Type-Aware Case F1 (`evaluator.score_case`)
Each key-value pair `(k, v)` in a record is represented as `(str(k), type(v).__name__, normalized_value)`:
- Including `type(v).__name__` ensures `"4"` (`str`) does not match `4` (`int`), and `True` (`bool`) does not match `1` (`int`) despite Python's `True == 1` equality.
- Given expected item set $E$ and actual item set $A$:
  - If $E = \emptyset$ and $A = \emptyset$, score $= 1.0$.
  - Otherwise $\text{precision} = \frac{|E \cap A|}{|A|}$, $\text{recall} = \frac{|E \cap A|}{|E|}$, and $\text{F1} = \frac{2 \cdot \text{precision} \cdot \text{recall}}{\text{precision} + \text{recall}}$.

### Aggregate Metrics
- **Accuracy**: Mean case F1 across all 15 benchmark cases.
- **Case Pass Rate**: Fraction of cases achieving exact `score == 1.0`.
- **Composite Score**:
  $$\text{composite\_score} = 0.85 \times \text{accuracy} + 0.15 \times \text{case\_pass\_rate}$$
- **Latency**: Average and p95 per-call latency in milliseconds across 10 repeats per benchmark case.

### Strict Acceptance Gate (`guardrails.check_candidate_acceptance`)
A candidate replaces the current best version **only if all five conditions hold**:
1. `unit_test_pass_rate == 1.0` (100% of `tests/test_solver.py` pass)
2. `avg_latency_ms <= 50.0` (prevents catastrophic regex backtracking or slow loops)
3. `candidate_accuracy >= best_accuracy` (blocks trading off average accuracy for exact-match hacks)
4. `candidate_composite > best_composite + 1e-6` (requires strict improvement; blocks no-ops at plateau)
5. `LockedFileManifest.verify()` succeeds before and after evaluation

---

## 4. Safety & Anti-Tamper Threat Model

1. **Path Traversal / Arbitrary File Writes**:
   `SandboxPaths.ensure_within_sandbox()` resolves paths with `Path.resolve().is_relative_to(project_root)`. `ensure_mutable_target()` further restricts writes strictly to `src/rsi_demo/solver.py` and `runs/`.
2. **Reward Hacking via Test/Evaluator Modification**:
   `LockedFileManifest` hashes `baseline_solver.py`, `evaluator.py`, `guardrails.py`, and `tests/*.py` with SHA-256 at run start and verifies hashes before and after every cycle.
3. **Malicious or Accidental Unsafe Candidate Code**:
   `validate_candidate_ast()` walks the Python AST prior to writing `solver.py`:
   - Allows imports only from `{"__future__", "collections", "dataclasses", "json", "math", "re", "string", "typing"}`.
   - Forbids `eval`, `exec`, `compile`, `__import__`, `open`, `globals`, `locals`, `getattr`, `setattr`, `delattr`, etc.
   - Forbids reflection/escape attributes (`__subclasses__`, `__globals__`, `__builtins__`, `__code__`, `system`, `popen`).
4. **Runaway Iteration / Infinite Loops**:
   `HARD_MAX_CYCLES = 5` is enforced in code (`validate_max_cycles`), and candidate evaluation runs in a separate subprocess with `timeout=10.0` seconds.

---

## 5. How Real / Frontier RSI Differs

This project is an educational **code-level strategy-improvement loop** on a fixed benchmark. Real or frontier Recursive Self-Improvement differs in several fundamental ways:

1. **Full Model Retraining vs. Inference-Time Code Editing**:
   Frontier RSI explores modifying training algorithms, reward models, synthetic data pipelines, or neural weights—requiring distributed GPU clusters rather than millisecond CPU runs.
2. **Dynamic & Open-Ended Tasks**:
   Our benchmark has 15 fixed cases where `1.0000` is reachable in 4 cycles. Real domains have open-ended distributions where overfitting to a small benchmark ("benchmark saturation" or "Goodhart's Law") is a primary failure mode.
3. **Diminishing Returns & Compute Ceilings**:
   Early cycles fix broad bugs (e.g., `+0.20` and `+0.38` score jumps in Cycles 1–2), whereas later cycles yield smaller gains (`+0.0956` in Cycle 4, `0.0000` at Cycle 5) while verification cost stays constant or grows.
4. **Subtle Specification Gaming**:
   With general-purpose tool access or complex environments, an optimizer may satisfy proxy metrics in unintended ways that static AST allowlists alone cannot catch without independent held-out evaluation and human/formal oversight.
