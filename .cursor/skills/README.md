Skills for Cloud Agents on this repository.

Cursor loads the skills in this directory into every Cloud Agent started on the repository, whether from the web, the desktop app, GitHub, Slack or the API, including the agents fyp launches from Grok Bot. A skill without `disable-model-invocation: true` is in the agent's catalog from the start, and the agent uses it when its description matches the task or the launch prompt names it. A skill with `paths` is offered only while the agent works on matching files. The Cloud Agents API has no field for skills, so a launch prompt names a skill in plain words, for example "Use the cantoai-interrogate skill".

In a run on 2026-09-24 an agent started on a branch got the skills of main, not of its branch, so a change to a skill takes effect once it is merged.

| Skill | Used by | When |
|---|---|---|
| `cantoai-tdd` | any agent changing `src/` or `tests/` | fixing a bug that a cheap local test can show |
| `cantoai-test-behavior` | any agent adding or changing a test | every test it adds or changes; weak tests already there are reported, not changed |
| `cantoai-blast-radius` | tooling agents, and gate changes | before a change to shared `src/` code ships |
| `cantoai-interrogate` | a read-only review agent that fyp launches | after CI is green on a tooling pull request (`repair/tooling-*`); its verdict is advisory |
| `open-code-review-delegate` | not in the current flow (v3); `disable-model-invocation: true` | a Bugbot substitute through the `ocr` CLI |

Review of a score-route task's inference scripts is not wired: LOOP.md has no step for it and the launch ledger no role. Adding it means changing `cantoai-interrogate`, which is a bar move.

The four `cantoai-` skills are adapted from pstack 0.15.5 (`github.com/cursor/plugins`, commit `12d587d`, MIT licence in `LICENSE-pstack`). The prefix keeps them apart from the pstack plugin's own skills with the same base names.

Everything under `.cursor/` is agent instruction, so it is a gate file (LOOP.md, history-audit). A pull request that adds or changes a file here needs a `Gate-review:` line. Changing an existing file is a bar move: the body also needs `BAR-CHANGE:` naming it, and the pull request may not change `src/`, any `.sql` file or `data/`. Agent branches may not write here.

The `ocr` CLI is preinstalled by `.cursor/environment.json`. Use `ocr delegate`, not `ocr review`. Only the delegate skill is vendored; the non-delegate skill needs an OCR-side LLM key and is not supported here.
