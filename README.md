# Safe Recursive Self-Improvement (RSI) Demo

A small, self-contained, sandboxed Python project demonstrating **Recursive Self-Improvement (RSI)**: a system that inspects its own task failures, proposes targeted code improvements to its solver, evaluates each candidate against a locked test & benchmark suite, keeps only verified improvements, rolls back regressions, and logs every cycle deterministically.

> Looking for a non-technical explanation? Start with the [Layman Guide](docs/layman-guide.md).
> Want a deep dive into the internals and threat model? See [Architecture](docs/architecture.md).

---

## What Task Does It Solve?

The target task is **semi-structured text-to-JSON record extraction** (`extract_record(text: str) -> dict` in `src/rsi_demo/solver.py`). Real-world logs and LLM outputs frequently mix clean JSON, Markdown code fences, trailing commas, `key=value` inline pairs, comments/banners, currency strings (`$49.50`), quoted delimiters (`"Alert: disk full, node 3"`), URLs containing colons, and inconsistent key aliases (`User_Email`, `Qty`, `Amt`).

Starting from a minimal `v0-baseline` solver (`score=0.3233`, `5/15` or `33.3%` accuracy), the RSI loop iteratively evolves `src/rsi_demo/solver.py` up to `1.0000` (`15/15` cases) within a hard cap of **5 cycles**, while catching and rolling back a flawed regex refactor along the way.

---

## Project Layout

```text
rsi/
├── pyproject.toml                 # Zero third-party runtime dependencies (Python >= 3.11)
├── run_rsi.py                     # Convenience CLI launcher
├── README.md                      # Technical overview & step-by-step checklist
├── docs/
│   ├── architecture.md            # Detailed design, scoring math, & frontier RSI comparison
│   └── layman-guide.md            # Jargon-free explanation with everyday analogies
├── src/rsi_demo/
│   ├── baseline_solver.py         # Locked v0 baseline template
│   ├── solver.py                  # Mutable active solver improved during RSI runs
│   ├── evaluator.py               # Locked 15-case benchmark & subprocess evaluation runner
│   ├── guardrails.py              # Sandbox paths, SHA-256 anti-tamper, AST safety, rollback gates
│   ├── proposer.py                # Offline MockProposer + optional OpenAI-compatible LLM hook
│   ├── loop.py                    # Core RSI orchestrator & deterministic JSONL/JSON logging
│   └── cli.py                     # CLI interface
└── tests/
    ├── test_solver.py             # Locked contract unit tests (must pass 100% every cycle)
    ├── test_guardrails.py         # Safety, AST, tamper-detection, and acceptance-gate tests
    └── test_loop.py               # End-to-end RSI loop & adversarial AST-rejection tests
```

---

## How the RSI Loop Works (Step by Step)

1. **Initialize & Lock Integrity (`guardrails.py`, `loop.py`)**:
   - Validates `1 <= max_cycles <= 5` (`HARD_MAX_CYCLES = 5`).
   - Resolves all paths strictly inside the repository root (`SandboxPaths`).
   - Computes a SHA-256 `LockedFileManifest` over `baseline_solver.py`, `evaluator.py`, `guardrails.py`, and `tests/*.py`.
   - Resets `src/rsi_demo/solver.py` to `baseline_solver.py` (unless `--no-reset` is passed) and evaluates the baseline in an isolated subprocess.
2. **Inspect Failures (`evaluator.py`)**:
   - Collects type-aware F1 `accuracy`, `case_pass_rate`, `unit_test_pass_rate`, `avg_latency_ms`, `p95_latency_ms`, `composite_score`, and structured `CaseFailure` objects tagged by failure mode (`fenced_json`, `kv_inline`, `quoted_delimiters`, etc.).
3. **Propose Candidate (`proposer.py`)**:
   - **Offline (`MockProposer`)**: Inspects failure tags and cycle history to synthesize the next targeted Python improvement—including an intentional bad refactor (`v3-naive-regex-regression`) in Cycle 3 so you can observe safety rollbacks immediately without API keys.
   - **Optional LLM (`OpenAICompatibleProposer`)**: Sends current `solver.py`, metrics, and top failing cases to an OpenAI-compatible `/chat/completions` endpoint using Python stdlib `urllib.request`.
4. **Pre-Execution AST Safety Check (`guardrails.py`)**:
   - Parses candidate code with `ast.parse` *before* writing or executing it. Blocks disallowed imports (`os`, `subprocess`, `sys`, etc.), dangerous calls (`eval`, `exec`, `open`, `getattr`), dunder escapes (`__subclasses__`), and missing `extract_record` signatures.
5. **Isolated Subprocess Evaluation (`evaluator.py`)**:
   - Writes the candidate only to `src/rsi_demo/solver.py` and runs both the 15 locked benchmark cases and `tests/test_solver.py` inside a fresh Python subprocess with a 10-second wall-clock timeout.
   - Re-verifies `LockedFileManifest` SHA-256 hashes immediately after evaluation to detect any tampering.
6. **Accept or Roll Back (`guardrails.py`, `loop.py`)**:
   - Keeps the candidate **only if**: `unit_test_pass_rate == 1.0`, `avg_latency_ms <= 50.0`, `accuracy >= best_accuracy`, and `composite_score > best_composite + 1e-6`.
   - Otherwise restores the previous best `solver.py` immediately and logs the exact rejection reason.
7. **Deterministic Logging (`runs/<run-id>/`)**:
   - Writes `cycles.jsonl` (one JSON record per cycle), `summary.json`, and `versions/` snapshots (`00_baseline_solver.py`, accepted/rejected candidates, and `best_solver.py`).

---

## How Evaluation Prevents False Gains & Reward Hacking

- **Locked Evaluation & Tests**: `evaluator.py` and `tests/test_solver.py` are outside the writable target set and hashed with SHA-256 before and after every cycle. Any modification triggers `TamperDetectedError`.
- **AST Import & Builtin Sandboxing**: Candidate solvers cannot import `rsi_demo.evaluator`, `os`, or `sys`, nor call `open()` or `eval()`, preventing them from reading expected answers or modifying test state at runtime.
- **Type-Aware Scoring**: `score_case()` compares `(key, type(value).__name__, value)` tuples so `"4"` does not match `4` and `True` does not falsely equal `1` in Python.
- **Regression & Contract Gating**: A candidate that raises benchmark score on one subset while breaking `tests/test_solver.py` (like truncating `https://...` URLs at `:`) or regressing overall accuracy is automatically rolled back.

---

## Real RSI vs. This Safe Demo

| Dimension | This Local Demo | Real / Frontier RSI Research |
| --- | --- | --- |
| **What changes** | A single small Python module (`solver.py`) | Model weights, training pipelines, tool scaffolds, or multi-module architectures |
| **Search / Proposal** | Deterministic mock rules or single-turn LLM prompt | Autonomous coding agents, RL/self-play, synthetic data generation, or evolutionary search |
| **Evaluation** | Fixed 15-case benchmark + 6 unit tests | Large held-out suites, formal verification, fuzzing, and adversarial red-teaming |
| **Compute & Cost** | Milliseconds on CPU, capped at 5 cycles | Massive GPU clusters, diminishing returns as easy gains saturate, and overfitting risks |
| **Failure Mode** | Caught by SHA-256 manifest + AST sandbox | Subtle specification gaming across distributed tools or long-horizon reward hacking |

---

## Step-by-Step Checklist: Run, Inspect, and Extend

### 1. Run the Test Suite
```bash
python3 -m pytest -v
```
All 13 unit and integration tests (`test_guardrails.py`, `test_loop.py`, `test_solver.py`) should pass.

### 2. Run the Offline RSI Demo (No API Keys Needed)
```bash
# Example 1 (default): Text-to-JSON Record Parser
python3 run_rsi.py --run-id demo-run

# Example 2: 2D Delivery Route Optimizer (nearest-neighbor -> 2-opt)
python3 run_rsi.py --task route_optimizer --run-id route-demo-run
```
Expected progression:
- **Baseline (`v0-baseline`)**: `score=0.3233`, `acc=0.3333`
- **Cycle 1 (`v1-json-recovery`)**: `ACCEPTED` -> `score=0.5233` (`7/15` cases)
- **Cycle 2 (`v2-kv-coercion`)**: `ACCEPTED` -> `score=0.9044` (`13/15` cases)
- **Cycle 3 (`v3-naive-regex-regression`)**: `ROLLED_BACK` -> `score=0.8540`, `unit=5/6` (caught URL colon truncation!)
- **Cycle 4 (`v3-quote-aware-aliasing`)**: `ACCEPTED` -> `score=1.0000` (`15/15` cases)
- **Cycle 5 (`v4-plateau-noop`)**: `ROLLED_BACK` -> `score=1.0000` (no strict gain at plateau)

### 3. Inspect Logs and Version Snapshots
```bash
cat runs/demo-run/summary.json
cat runs/demo-run/cycles.jsonl
ls -la runs/demo-run/versions/
```
You can also evaluate the current solver or reset back to baseline at any time:
```bash
python3 run_rsi.py --eval-only
python3 run_rsi.py --reset-only
```

### 4. (Optional) Run with a Live OpenAI-Compatible LLM Backend
```bash
export RSI_LLM_API_KEY="your-api-key"
export RSI_LLM_MODEL="gpt-4o-mini"          # optional
export RSI_LLM_BASE_URL="https://api.openai.com/v1"  # optional (supports local Ollama/vLLM too)
python3 run_rsi.py --backend llm --cycles 3 --run-id llm-run
```
Every LLM-generated candidate goes through the exact same AST safety check, subprocess isolation, SHA-256 tamper check, unit tests, and rollback gate.

### 5. Extend the Project Safely
1. **Add harder benchmark cases**: Edit `BENCHMARK_CASES` in `src/rsi_demo/evaluator.py` (for example, nested lists or European decimal formats) and add matching invariants to `tests/test_solver.py`.
2. **Add a custom proposer**: Implement the `Proposer` protocol in `src/rsi_demo/proposer.py` (`propose(cycle, current_source, report, history) -> Proposal`).
3. **Never bypass `guardrails.py`**: Keep `HARD_MAX_CYCLES`, AST checks, and `LockedFileManifest` intact—treat `tests/` and `evaluator.py` as immutable ground truth during any improvement run.
