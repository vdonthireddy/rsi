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

Imagine a delivery driver who starts at the **depot**, needs to drop off packages at 6–8 stops, and then return to the depot—driving the shortest total distance possible:

- **Start (`v0-input-order`):** The program visits stops in whatever scrambled order they were typed on the clipboard, zigzagging back and forth across town. Score: **52%**.
- **Cycle 1 (`v1-nearest-neighbor`) — Kept:** It switches to a common-sense rule: *"Always drive to the closest unvisited stop next."* Total driving distance drops dramatically. Score jumps to **91%**.
- **Cycle 2 (`v2-two-opt`) — Kept:** It notices its route still crosses over itself in a figure-8, so it learns to untangle crossing paths. Now all 6 delivery routes match the shortest possible distance (**100%**).
- **Cycle 3 (`v3-x-sort-regression`) — Caught & Undone:** It tries a shortcut that simply sorts stops from west to east—forgetting the rule that the driver *must* start at the depot. The safety tests catch the mistake immediately and **roll back** to Cycle 2.
- **Cycles 4–5:** Since the route is already 100% optimal, extra tweaks add no improvement and are rejected.

Notice the key takeaway: **the exact same RSI engine and guardrails** (`loop.py` and `guardrails.py`) power both the messy-note reader and the delivery-route planner—only the problem's solver and scorecard were swapped.

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
