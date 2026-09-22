#!/usr/bin/env python3
"""Every branch must belong to a known class.

Four classes, and nothing else:

    cursor/t<N>-<scope>-...          a Cloud Agent working on task N
    box/t<N>-<scope>-...             the same, on the shared machine
    chore/...                        declarations and top-level documents
    repair/... | cursor/repair-...   a tool fix asked for by the repository owner

A branch matching none of them fails. That is the point. The silent pass for an
unrecognised branch name is how commit 15ea35a reached main: it changed three
declared expected values after contract-check had already gone red on the same
branch, and nothing looked at it because the branch name matched no pattern.

Match order is load-bearing (plan §3.1): AGENT_RE first, then REPAIR_RE, then
CHORE_RE. A worker branch must not be classified as repair or chore because
its name also matches a later prefix.

repair and chore are not authorized by prefix. They are authorized by the
repository owner having opened the pull request: CI passes the PR author
(github.event.pull_request.user.login) and the owner allowlist, and those must
match. Prefix alone is how cursor/repair-… and repair/… used to take deny=[]
and rewrite briefs, corpus, CI, and the contract.

Why the PR author and not github.actor: the actor is whoever triggered the run.
On the `opened` event that is the owner; on every later push by a Cloud Agent it
is cursor[bot], so the same head went red and had to be re-published as a new
PR (#95→#96→#97, #98→#99). Who opened the PR is fixed for its lifetime, which
is what "the owner asked for this" means here. --actor is kept as the fallback
for local ./verify and for runs with no pull request.

What this does and does not prove: it records that the owner's account opened
the PR. Cloud Agents open their PRs through that same account, so this is
consent, not identity. Telling a human commit from an agent commit would need
signature checks against a pinned key; that is a separate change.

What each class may touch:

    agent   anything except DENY and the task briefs; it writes its outputs
            under tasks/TASK-N/, which is allowed. DENY includes the gates
            under scripts/, the corpus pin in README.md, and LOOP.md
    chore   only CHORE_ALLOW, and never DENY (same deny list as agent)
    repair  anything, once the actor is a repository owner

Per-scope path lists are not checked here. They belong to a task declaration,
and until one exists again they are a matter for review.

Usage:
    SCOPE_AUTHOR="$PR_AUTHOR" python scripts/scope_check.py --branch "$HEAD_REF" \\
        --base origin/main --actor "$GITHUB_ACTOR" --owners "$OWNER_ALLOWLIST"

The author arrives in the SCOPE_AUTHOR environment variable (or --author),
not as a required flag: on a pull request CI runs the copy of this script from
the base branch, and a base copy that predates this option must still accept
the same command line, or the change that introduces it can never go green.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from typing import NamedTuple

AGENT_RE = re.compile(r"^(?:cursor|box)/[rt](?P<task>\d+)-(?P<scope>[a-z0-9_]+)-")
REPAIR_RE = re.compile(r"^(?:repair/|cursor/repair-)")
CHORE_RE = re.compile(r"^chore/")

# Only the owner changes the rules, the corpus, the loop docs, or the CI that
# enforces them. An agent that needs one of these changed writes an empty
# commit whose subject starts with BLOCKED: instead (plan §4.4); the owner
# then sets status: blocked or escalated on the brief.
# scripts/ is the gate that judges the agent; README.md pins the corpus sha;
# LOOP.md is the procedure the gate enforces. Changing README sha alone is not
# a full walk-through (data/** is already denied); it is still DENY.
DENY = [
    ".cursor/*", ".cursor/**",
    ".github/*", ".github/**",
    "data/*", "data/**",
    "scripts/*", "scripts/**",
    "README.md", "LOOP.md",
]

# The brief is the agent's scoresheet: the numbers it owes and the tolerance each
# one gets are not its to move. Its outputs sit beside it, under tasks/TASK-N/,
# and it must be able to write those. fnmatch cannot express that distinction --
# its * crosses a slash, so "tasks/*" would deny tasks/TASK-N/results.json as
# well, and every worker and verifier pull request would fail. This matches the
# brief itself and nothing below it.
BRIEF_RE = re.compile(r"^tasks/[^/]+\.md$")

CHORE_ALLOW = [
    "BACKGROUND.md", "PIPELINE.md", "REPORT.md", "RESEARCH_LOG.md",
    "backlog.md", "STOP", "tasks/*", "tasks/**", "docs/*", "docs/**",
    # Campaign notes. LOOP.md stays DENY; numbers/RESULT stay under tasks/.
    "investigations/*", "investigations/**",
]


class BranchClass(NamedTuple):
    name: str
    allow: list[str] | None
    deny: list[str]
    no_brief: bool


def run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def changed(base: str) -> list[str]:
    return sorted(p for p in run("git", "diff", "--name-only", f"{base}...HEAD").splitlines() if p.strip())


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def parse_owners(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(p.strip().casefold() for p in raw.split(",") if p.strip())


def actor_is_owner(actor: str | None, owners: frozenset[str]) -> bool:
    if not actor or not owners:
        return False
    return actor.strip().casefold() in owners


def principal(actor: str | None, author: str | None) -> tuple[str, str | None]:
    """Who is answerable for a repair/ or chore/ branch.

    The PR author when there is a pull request (stable across pushes); the
    event actor otherwise (local ./verify, no-PR runs). Never both: an owner
    pushing to a stranger's PR must not launder it, and an agent pushing to
    the owner's PR must not sink it.
    """
    if author and author.strip():
        return "author", author.strip()
    return "actor", actor.strip() if actor else actor


def classify(
    branch: str,
    actor: str | None,
    owners: frozenset[str],
    author: str | None = None,
) -> BranchClass:
    """Return the branch class. AGENT_RE is matched first (plan §3.1)."""
    if AGENT_RE.match(branch):
        return BranchClass("agent", None, DENY, True)
    kind, who = principal(actor, author)
    if REPAIR_RE.match(branch):
        if not actor_is_owner(who, owners):
            raise ValueError(
                f"scope_check: FAIL branch {branch!r} class repair is not authorized "
                f"for {kind} {who!r}"
            )
        return BranchClass("repair", None, [], False)
    if CHORE_RE.match(branch):
        if not actor_is_owner(who, owners):
            raise ValueError(
                f"scope_check: FAIL branch {branch!r} class chore is not authorized "
                f"for {kind} {who!r}"
            )
        return BranchClass("chore", CHORE_ALLOW, DENY, False)
    raise ValueError(f"scope_check: FAIL branch {branch!r} matches no branch class")


def path_blocked(path: str, cls: BranchClass) -> str | None:
    if match_any(path, cls.deny) or (cls.no_brief and BRIEF_RE.match(path)):
        return "DENY"
    if cls.allow is not None and not match_any(path, cls.allow):
        return "OUT"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument(
        "--author",
        default=None,
        help="GitHub login that opened the pull request; defaults to $SCOPE_AUTHOR; "
        "empty when there is none",
    )
    ap.add_argument(
        "--owners",
        required=True,
        help="comma-separated GitHub logins allowed to use repair/ and chore/",
    )
    args = ap.parse_args()

    branch = args.branch.strip()
    actor = args.actor.strip()
    author = (args.author if args.author is not None else os.environ.get("SCOPE_AUTHOR", "")).strip()
    owners = parse_owners(args.owners)
    try:
        cls = classify(branch, actor, owners, author=author)
    except ValueError as e:
        print(str(e))
        if "matches no branch class" in str(e):
            print("  allowed prefixes: cursor/t<N>-<scope>-, box/t<N>-<scope>-, chore/, repair/")
        else:
            print("  repair/ and chore/ require the pull-request author (--author),")
            print("  or --actor when there is no pull request, on the --owners allowlist")
            print("  allowed prefixes: cursor/t<N>-<scope>-, box/t<N>-<scope>-, chore/, repair/")
        return 1

    files = changed(args.base)
    kind, who = principal(actor, author)
    print(
        f"scope_check: branch={branch} class={cls.name} {kind}={who!r} "
        f"files={len(files)}"
    )

    bad: list[str] = []
    for f in files:
        reason = path_blocked(f, cls)
        if reason == "DENY":
            print(f"  DENY    {f}")
            bad.append(f)
        elif reason == "OUT":
            print(f"  OUT     {f}")
            bad.append(f)
        else:
            print(f"  ok      {f}")

    if bad:
        print(f"scope_check: FAIL {len(bad)} file(s) this branch class may not touch")
        if cls.allow is not None:
            print(f"  chore/ may touch: {cls.allow}")
        print(f"  no class but repair/ may touch: {DENY}")
        if cls.no_brief:
            print("  a task brief tasks/<name>.md is the owner's; an agent writes only under tasks/TASK-N/")
        return 1

    print("scope_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
