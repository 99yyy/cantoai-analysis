---
name: cantoai-interrogate
description: "Read-only adversarial review of one tooling pull request (a repair/tooling- branch changing src/ or tests/) in this repository by several reviewers, ending in one advisory verdict. Use only when your launch prompt asks for a cantoai-interrogate review of a named pull request. Never for a task's research numbers or output files, and never on your own initiative."
---

# cantoai-interrogate

Adapted from the `interrogate` skill of pstack 0.15.5 (`cursor/plugins`, MIT, see `../LICENSE-pstack`). Changes for this repository: tooling pull requests only, one per run; reviewer models come from the launch prompt; the verdict is your final message and one advisory comment; a project lens is added.

Spawn several reviewers to adversarially review the change. Each gets the same prompt and rubric. The deliverable is one synthesized verdict, which is advisory only (analysis contract, clause 8). Do not change any file, do not commit, do not push, and do not open a pull request or an issue. Your final message is the verdict; fyp reads it from this run's transcript.

This skill is for tooling pull requests, whose branch starts with `repair/tooling-`. If the named pull request is not one, say so at the top of your final message, review it only if the launch prompt says to anyway, and post no comment on it.

For a tooling pull request, also post the verdict as one comment on it, so the owner sees it where he merges:

- Begin the comment with `Automated advisory review (cantoai-interrogate). Not an approval.`
- Post exactly one comment. Never edit the title or body, approve, request changes, label, merge or close the pull request, and never comment on an issue.
- If you have no tool that can comment on a pull request, skip the comment and say so in your final message.

## Step 1, Scope

Review exactly the pull request your launch prompt names.

- If you started at that pull request's head, the change is `git diff origin/main...HEAD`.
- Otherwise fetch it read-only: `git fetch origin pull/<n>/head:review-<n>` and diff `origin/main...review-<n>`.
- Give the reviewers the diff plus the files they need to understand it: callers, callees, the task brief if one applies, and `.cursor/rules/analysis-contract.mdc`.
- If a task is still open (its brief `tasks/TASK-N.md` is not `status: closed`), never open, read or quote its output files, the paths in the worker and verifier write sets (`scope`, class `agent`, `roles` in `scripts/gate_config.json`), unless the reviewed pull request itself changes them. Fetch only `main` and the branch under review. A verdict that carries one side's numbers could reach the other side.

## Step 2, Intent

Take the intent from the launch prompt. If it has none, derive it from the pull-request body and commit messages and state it in one paragraph. Do not wait for a reply: there is no user in this run.

## Step 3, Reviewers

Launch all reviewers in a single message with the Task tool, `readonly: true`, `subagent_type: generalPurpose`.

- Models: if the launch prompt lists reviewer models, spawn one reviewer per listed model. Otherwise spawn three reviewers and omit `model`, so they run on your own model.
- If the Task tool rejects a model, run that reviewer on your own model and say so in the verdict. Never open a pull request or edit a file to change a model name.

Read `references/reviewer-prompt.md` and fill it with:
1. the intent;
2. the diff or file contents;
3. `references/rubric.md`;
4. `references/code-quality-review.md`;
5. `references/cantoai-lens.md`.

Every reviewer gets the same filled template.

## Step 4, Synthesize

1. Parse all findings.
2. Findings raised by two or more reviewers independently are the strongest signal. Reviewers on one model family share blind spots, so agreement among them is weaker evidence than agreement across families; say which case applies.
3. Weigh single-reviewer findings on their merits.
4. Merge duplicates and note who raised each.
5. Note disagreements.

## Step 5, Lead judgment

You are the lead reviewer, a pragmatic senior engineer, not a neutral aggregator. Read `references/lead-judgment.md`. Put every finding in one bucket:

- **Act on**: real problems with correctness, security, reproducibility, the analysis contract or maintainability. These would block a merge.
- **Consider**: legitimate, but the cost of fixing may outweigh it now.
- **Noted**: valid but not actionable at this stage.
- **Dismissed**: wrong, nitpicky or missing context, with a one-line reason.

For each finding give the reviewer(s), the bucket and a one-line rationale. Keep "Act on" to at most five items.

## Output

### Intent
> the paragraph from Step 2

### Reviewers
- one bullet per reviewer: label, model, number of findings

### Act On
### Consider
### Noted
### Dismissed
### Agreement Map
Where reviewers agreed, where they diverged, and what that says.

End with one line: `VERDICT: merge` or `VERDICT: fix first (<n> act-on items)`.
