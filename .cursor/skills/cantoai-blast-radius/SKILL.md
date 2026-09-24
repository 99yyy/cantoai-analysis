---
name: cantoai-blast-radius
description: "Before a change to shared code in src/ ships, find what it could break beyond the diff and prove the one fact it is safe because of by running real code. Use when your launch prompt names cantoai-blast-radius, or when asked what a change to src/ could break."
---

# cantoai-blast-radius

Adapted from the `blast-radius` skill of pstack 0.15.5 (`cursor/plugins`, MIT, see `../LICENSE-pstack`). Steps that depended on skills not vendored here were rewritten.

Find what a change breaks somewhere else, before it ships. Listing the callers is not the job; grep does that in a second. The job is the breakage grep will not show you.

## Do not trust your own write-up

A blast-radius write-up that sounds right is worthless: it reads as convincing whether or not it is true. Find the one or two facts the change's safety depends on and prove them by running code.

For each such fact, get it as far down this list as is cheap, and say where it stopped:

1. You said so. Worthless on its own.
2. You pointed at the line: a real `file:line`, or the library's own source.
3. You showed the bad case cannot happen, by walking the failure step by step.
4. You ran it: a script or test that calls the real code and fails loudly if you are wrong.
5. You reproduced it end to end: you ran the tests that import the changed module, or an affected task's `run_worker.py`, and compared its output with the committed file without committing the new one. (`./verify task <N>` replays a task's SQL; it does not run `src/`.)

## Steps

1. **Read the change.** The diff, the symbols it adds, changes and deletes, and what it now does differently, including what the diff does not spell out. Read the pull request and its commits with `git log` and `gh pr view` (read-only).
2. **Find the one fact it is safe because of.** Most risky-looking changes are safe because of a single fact, such as "this function is only called from X and never with an empty frame". If it holds, most risky cases clear at once. Spend your time here.
3. **Look where grep stops.** Read the source of the library you call and its pinned version in `requirements.txt`. Work out when things run: import time, process exit, file locks, SQLite transactions. Follow what a symbol search misses: a column name in a `.sql` file, a key in `results.json`, a file another task's `run_worker.py` reads, a path in `scripts/gate_config.json`.
4. **In this repository, check the closed tasks.** A change to a shared `src/` module can change what an earlier task's `run_worker.py` or tests compute. Name every task and test that reaches the changed code.
5. **Be honest about each risk.** Give each a real likelihood and a real cost. Keep the risks you confirmed; list the ones you checked and cleared separately. Cite a real `file:line`; a search that finds nothing is still an answer; never invent a caller or an API.
6. **Prove the one fact.** Write a script or test that runs the real code, run it, and paste what happened. Keep a throwaway script out of the commit unless your write set allows it.

## What to hand back

- **What it does.** What changed, including the part that is not obvious.
- **The one fact it is safe because of.** State it, the level it reached on the list above, and the proof. If you could not prove it, write "unproven".
- **Risks.** Each with how it breaks, the `file:line`, how likely and how bad, and how to check.
- **Cleared.** What you checked and why it is fine.
- **Before you merge.** The cheapest test or reproduction that would catch the real bug, including the script you wrote.
