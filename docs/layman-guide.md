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
