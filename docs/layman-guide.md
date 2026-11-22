# A Friendly Guide to Recursive Self-Improvement (RSI)

If you have never worked with AI engineering before, **Recursive Self-Improvement (RSI)** sounds like something out of science fiction. In reality, the core idea is surprisingly everyday—and this small project lets you watch a safe version of it happen step by step on your own computer.

---

## The Everyday Analogy: Improving Your Own Recipe

Imagine you are trying to perfect a chili recipe for a cooking contest:

1. **Baseline (Version 0):** You cook your basic recipe and let three judges taste it. They give it **3 out of 10** because it lacks seasoning and the beans are undercooked.
2. **Inspect What Went Wrong:** Instead of changing random ingredients, you read the judges' notes: *"Too bland, beans still crunchy."*
3. **Try One Targeted Tweak (Cycle 1):** You simmer the beans longer and add cumin. You test it again. Score jumps to **6 out of 10**. **You keep this version!**
4. **Try Another Tweak (Cycle 2):** Next, you add smoked paprika and roasted garlic. Score jumps to **9 out of 10**. **You keep this version too!**
5. **A Bad Experiment (Cycle 3):** Someone suggests dumping in a whole cup of salt to "boost flavor." The judges spit it out—score drops to **2 out of 10** and fails the basic *"is it edible?"* rule. **You throw out that experiment and go back to your 9/10 recipe.**
6. **Final Polish (Cycle 4):** You add a squeeze of lime at the end. Score hits **10 out of 10**.

That loop—**try -> measure against a fixed test -> keep if better, undo if worse -> repeat**—is Recursive Self-Improvement.

Another simple analogy is **refining your study routine**: you try flashcards for a week, check your practice quiz score, keep what raised your score, drop habits that lowered it, and never cheat by rewriting the quiz answer key!

---

## What This Demo Actually Shows

In this project, the AI's "recipe" is a small Python program (`solver.py`) whose job is to pull structured information (like names, prices, emails, and settings) out of messy text—for example, computer logs or notes written by humans.

When you run the demo (`python3 run_rsi.py`):
- **Start (`v0-baseline`):** The program only understands ultra-neat text. It scores **32%**.
- **Cycle 1:** It notices it fails on text wrapped inside chat markdown boxes, so it learns how to unwrap them. Score rises to **52%**. **Kept.**
- **Cycle 2:** It notices it fails on comma-separated lists and numbers written as words like `true` or `$10`, so it learns to convert them properly. Score rises to **90%**. **Kept.**
- **Cycle 3:** It tries a shortcut trick that looks simpler—but accidentally breaks website links (`https://example.com:8080`). The safety tests catch the mistake immediately, and the system **rolls back** to Cycle 2.
- **Cycle 4:** Learning from that mistake, it adds a smarter quote-aware reader and handles nickname columns (`qty` -> `quantity`). Score hits **100%**. **Kept.**
- **Cycle 5:** Since everything already passes, a tiny cosmetic tweak produces no improvement, so the system rejects it and stops cleanly.

Every single attempt—both successes and mistakes—is written down in a permanent logbook (`runs/demo-run/cycles.jsonl`).

---

## A Concrete Example: Following One Messy Note End-to-End

To see what the code is actually doing, imagine a support system receives a messy text message like this:

```text
title: "Alert: disk full, node 3", severity: "high", retries: 2
```

What we **want** the program to produce is a clean, structured dictionary where numbers are real numbers (not text) and the quoted message stays intact:

```json
{
  "title": "Alert: disk full, node 3",
  "severity": "high",
  "retries": 2
}
```

Here is how the program's output evolves across the self-improvement loop:

1. **Start (`v0-baseline`):**
   The starting code only knows how to split on the *first* colon (`:`) on each line. So it treats everything after `title:` as one giant chunk:
   ```json
   {
     "title": "\"Alert: disk full, node 3\", severity: \"high\", retries: 2"
   }
   ```
   It missed `severity` and `retries` completely.

2. **Cycle 2 (`v2-kv-coercion`) — Better, but still flawed on quotes:**
   The program learns to split comma-separated items and convert numbers like `2`. However, it splits on *every* comma—even the comma inside `"Alert: disk full, node 3"`:
   ```json
   {
     "title": "\"Alert: disk full",
     "severity": "high",
     "retries": 2
   }
   ```
   `severity` and `retries` are now right, and overall score jumps from 52% to 90%, so this version is **kept**—even though `title` is still broken.

3. **Cycle 3 (`v3-naive-regex-regression`) — The shortcut that gets caught:**
   Next, the system tries a compact pattern-matching shortcut. While testing, it runs the locked safety check on a website link:
   ```text
   endpoint: https://api.example.com:8443/v1
   ```
   The shortcut accidentally stops at the second colon and chops the link down to `"https"`. The safety test (`tests/test_solver.py`) immediately fails (`5/6` passed), so the system **rejects this change and rolls back** to Cycle 2.

4. **Cycle 4 (`v3-quote-aware-aliasing`) — The clean fix:**
   Learning from Cycle 3's failure, the system writes a quote-aware reader that ignores commas and colons inside `"..."` quotes, keeps website links whole, and standardizes nicknames (like turning `Qty: 7` and `Amt: $49.50` into `quantity: 7` and `amount: 49.5`). Now our messy note produces the exact target output:
   ```json
   {
     "title": "Alert: disk full, node 3",
     "severity": "high",
     "retries": 2
   }
   ```
   All 15 benchmark cases and all 6 safety tests pass (**100%**).

---

## How the Pieces Work Together (Start to Finish)

When you run `./restart.sh` (or `python3 run_rsi.py`), here is the exact chain of events behind the scenes:

1. **Reset to a clean starting line (`baseline_solver.py` -> `solver.py`):**
   The launcher resets the active program (`src/rsi_demo/solver.py`) back to the simple `v0-baseline` copy so every run starts fairly.
2. **Seal the rules (`guardrails.py`):**
   The guardrail system takes digital fingerprints (SHA-256 hashes) of the test files and scoring rules. It also enforces a hard limit of **5 cycles** and restricts edits strictly to `solver.py`.
3. **Grade the current version (`evaluator.py`):**
   The evaluator runs `solver.py` in a separate, timed mini-process against 15 locked test cases and 6 core safety tests (`tests/test_solver.py`). It produces a scorecard and a list of what failed.
4. **Propose a fix (`proposer.py`):**
   The proposer reads the failure list (for example, *"failed on quoted commas"*) and writes a new candidate version of `solver.py`.
5. **Safety-check, test, and decide (`guardrails.py` + `loop.py`):**
   - First, an automatic code scanner inspects the candidate's structure (AST) to make sure it doesn't use forbidden commands (like reading files or running system commands).
   - Next, the evaluator tests the candidate and re-checks the SHA-256 fingerprints to confirm nothing cheated.
   - If all safety tests pass **and** the score strictly improves, the new version is **kept**. Otherwise, `solver.py` is **rolled back** to the previous best version.
6. **Save the logbook (`runs/demo-run/`):**
   Every cycle's score, decision, and code snapshot is saved in `runs/demo-run/cycles.jsonl`, `summary.json`, and `versions/` so you can inspect the whole story afterward.

---

## Example 2: Planning a Delivery Driver's Route (`--task route_optimizer`)

To show that the RSI safety engine isn't tied to just one problem, the project also includes a completely different second example: **route planning** (`python3 run_rsi.py --task route_optimizer`).

Imagine a delivery driver who starts at the **depot**, needs to drop off packages at several stops, and then return to the depot—driving the shortest total distance possible.

### A Concrete Route Example (`scrambled_square`)

Suppose the driver has four stops on a 10×10 block city grid, given in a scrambled order:

```text
depot at (0, 0)    →  Start here
s1    at (10, 10)  →  Top-right corner
s2    at (0, 10)   →  Top-left corner
s3    at (10, 0)   →  Bottom-right corner
```

The shortest possible loop simply walks around the outer edge of the square (`depot → s2 → s1 → s3 → depot`), which is **40.0 blocks** total.

Here is how the solver evolves across the 5 cycles:

1. **Start (`v0-input-order`):**
   The baseline program visits stops in the exact scrambled order they were typed:
   ```text
   depot (0,0) → s1 (10,10) → s2 (0,10) → s3 (10,0) → depot (0,0)
   ```
   Because it cuts diagonally across the middle *twice* in an "X" shape, the driver travels **48.3 blocks** instead of 40.0. Across all 6 test maps, it scores **52%**.

2. **Cycle 1 (`v1-nearest-neighbor`) — Kept:**
   The program switches to a common-sense rule: *"From wherever you are, drive to the closest unvisited stop next."*
   On our square, from `depot (0,0)` it picks `s2 (0,10)` (10 blocks away) instead of diagonal `s1 (10,10)` (14.1 blocks away), tracing the clean outer loop:
   ```text
   depot → s2 → s1 → s3 → depot   (40.0 blocks!)
   ```
   Across all 6 maps, the overall score jumps from **52% to 91%**.

3. **Cycle 2 (`v2-two-opt`) — Kept:**
   On larger 6–8 stop maps (like `figure_eight_crossing`), nearest-neighbor can still paint itself into a corner with one crossing path. Cycle 2 adds a rule that checks if any two trip segments cross like an "X" and untangles them. Now all 6 delivery maps hit the shortest possible distance (**100%**).

4. **Cycle 3 (`v3-x-sort-regression`) — Caught & Undone:**
   Next, it tries a shortcut: *"Just sort all stops from west to east!"*
   Look what happens on a map where the depot is on the east side:
   ```text
   Stops: depot (10, 0), west (-5, 0), north (2, 5)
   Shortcut output: ["west", "north", "depot"]
   ```
   The driver started at `"west"` instead of `"depot"`! The safety test (`tests/test_route_solver.py`) immediately catches the broken rule (`4/5` passed) and **rolls back** to Cycle 2.

5. **Cycles 4–5:**
   Since Cycle 2 already achieves **100%** across all 6 maps, further tweaks add no improvement and are rejected cleanly.

Notice the key takeaway: **the exact same RSI engine and guardrails** (`loop.py` and `guardrails.py`) power both the messy-note reader and the delivery-route planner—only the problem's solver and scorecard were swapped.

---

## Example 3: Scheduling Tasks Before Deadlines (`--task task_scheduler`)

Here is a third, everyday example powered by the exact same RSI engine: **deciding what order to finish tasks before their deadlines** (`python3 run_rsi.py --task task_scheduler`).

Imagine you have 4 chores or work tasks to do one after another starting at **Hour 0**, and each one takes some hours and has a deadline:

```text
migration  →  takes 8 hours, due by Hour 4
sync_a     →  takes 2 hours, due by Hour 6
sync_b     →  takes 2 hours, due by Hour 7
sync_c     →  takes 2 hours, due by Hour 8
```

Every hour a task finishes *after* its deadline counts as **1 hour of lateness**. Here is how the scheduler improves step by step:

1. **Start (`v0-input-order`):**
   It does `migration` first (8 hours!). By the time `migration` finishes at Hour 8, **every single task** is late (`migration` is 4h late, `sync_a` at Hour 10 is 4h late, `sync_b` at Hour 12 is 5h late, `sync_c` at Hour 14 is 6h late = **19 hours total lateness**). Across all 6 test schedules, it scores **27%**.

2. **Cycle 1 (`v1-shortest-job-first`) — Kept:**
   It learns to knock out quick tasks first! Doing `sync_a`, `sync_b`, `sync_c` (2h each) finishes all three **on time** at Hours 2, 4, and 6, leaving only `migration` late (finishing at Hour 14 = 10 hours late). Overall score jumps from **27% to 65%**.

3. **Cycle 2 (`v2-earliest-deadline-first`) — Kept:**
   Next, it switches to sorting by **earliest deadline first**—which fixes medium-length urgent tasks on other schedules (like `reversed_deadlines`) and raises the overall score to **85%**.
   *(However, on our `heavy_blocker_trap` above, `migration` has the earliest deadline at Hour 4, so pure earliest-deadline-first puts the 8-hour blocker back in front and slips back to 19 hours lateness there!)*

4. **Cycle 3 (`v3-drop-long-jobs-regression`) — Caught & Undone:**
   The system tries a sneaky shortcut: *"Just skip any task longer than 4 hours so it can't block the others!"*
   The safety test (`tests/test_scheduler_solver.py`) immediately catches that `migration` was deleted (`3/4` tests passed) and **rolls back** to Cycle 2.

5. **Cycle 4 (`v3-edf-pairwise-swap`) — Kept:**
   Learning from that mistake, it keeps **all** tasks, starts from earliest-deadline-first, and tests swapping pairs of tasks whenever a swap reduces total lateness. It automatically moves the 8-hour `migration` behind the three 2-hour `sync` tasks, cutting total lateness from 19h down to the best possible **10h**—hitting **100%** across all 6 schedules!

6. **Cycle 5 (`v4-plateau-noop`) — Rejected:**
   Everything already hits 100%, so a no-op tweak is rejected cleanly.

---

## Why Guardrails Matter (No Cheating!)

Think back to the cooking contest or study routine analogy. What if a student tried to "improve their grade" by sneaking into the teacher's desk and changing the answer key? Their score would say 100%, even though they learned nothing.

In AI, that problem is called **reward hacking** or **test tampering**. To make sure our demo improves *honestly*, it enforces strict rules:
- **Locked Judge:** The test suite and scoring rules are sealed with digital fingerprints (SHA-256 hashes). If anything touches them during a run, the program immediately hits the emergency stop.
- **Safety Fence (Sandbox):** The system is only allowed to edit one designated solver file inside this folder. It cannot touch files elsewhere on your computer, run shell commands, or peek at the answer key.
- **Automatic Undo (Rollback):** Any change that lowers the score, slows the program down too much, or breaks a basic rule is automatically erased.
- **Hard Stop Limit:** The loop can never run forever—it is capped at a maximum of **5 cycles**.

---

## What This Demo Does *Not* Do

It is important to keep expectations grounded. While this demo illustrates the *logic* of RSI, it is very different from cutting-edge AI research:
- **It does not retrain a neural network:** It edits a small helper script, not billions of AI brain weights.
- **It does not invent open-ended goals:** A human wrote the 15 test cases and set the 5-cycle limit.
- **Real AI improvements get harder over time:** In real research, early fixes are easy and later improvements require enormous computing power and risk subtle loopholes that are much harder to spot than a broken website link.

Think of this project as a **model airplane in a wind tunnel**: small, safe, easy to inspect, and great for learning how the principles work before ever stepping near a real jet engine.
