#!/usr/bin/env python3
"""Every branch must belong to a known class.

The classes in gate_config, and nothing else:

    cursor/t<N>-<scope>-...          a Cloud Agent working on task N
    box/t<N>-<scope>-...             the same, on the shared machine
    repair/task-<N>-close-...        an owner-opened close; only that task's close write set
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

What each class may touch comes from the ``scope`` section of
``gate_config.json`` (read beside this file first, so CI's base-branch copy in
/tmp/gate judges by the base's config):

    agent   only its role's write set, with {task} bound to the task id in the
            branch name: worker -> results.json, sql/ and the open-analysis
            files of its task; verifier -> mine.json and mine_sql/; auditor ->
            review/TASK-N/, RESULT.json and the launch ledger. A role with no
            write set in the config fails. Protected paths and the task briefs
            are denied on top of that.
    close   a repair/task-<N>-close- branch, matched before repair: the brief,
            RESULT.json, the launch ledger, review/TASK-N/ and backlog.md for
            that task, and never a protected path. {task} in that allow list
            comes from the named group in the class match.
    chore   only its allow list, and never a protected path
    repair  anything, once the PR author is a repository owner

The diff is taken with ``--no-renames``: a rename shows as a delete plus an
add, so moving a protected file cannot hide the delete behind the new name.

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
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

GATE_CONFIG_NAME = "gate_config.json"


def load_scope_config() -> dict:
    """The ``scope`` section of gate_config.json, beside this file first."""
    here = Path(__file__).resolve().parent / GATE_CONFIG_NAME
    cwd = Path.cwd() / "scripts" / GATE_CONFIG_NAME
    for cand in (here, cwd):
        if cand.is_file():
            cfg = json.loads(cand.read_text(encoding="utf-8"))
            if "scope" not in cfg:
                raise ValueError(f"scope_check: {cand} has no 'scope' section")
            return cfg["scope"]
    raise ValueError(f"scope_check: {GATE_CONFIG_NAME} not found beside {__file__} or under ./scripts/")


SCOPE = load_scope_config()
# Only the owner changes the rules, the corpus, the loop docs, or the CI that
# enforces them. An agent that needs one of these changed writes an empty
# commit whose subject starts with BLOCKED: instead (plan §4.4); the owner
# then sets status: blocked or escalated on the brief.
DENY: list[str] = list(SCOPE["protected"])
# The brief is the agent's scoresheet: the numbers it owes and the tolerance each
# one gets are not its to move. Its outputs sit beside it, under tasks/TASK-N/,
# and it must be able to write those.
BRIEF_RE = re.compile(SCOPE["brief"])
CLASSES: list[dict] = list(SCOPE["classes"])


def _class(name: str) -> dict:
    for c in CLASSES:
        if c["name"] == name:
            return c
    raise ValueError(f"scope_check: gate_config scope has no class {name!r}")


def _deny_of(c: dict) -> list[str]:
    d = c.get("deny", "protected")
    return DENY if d == "protected" else list(d)


# Kept as names for ./verify, tests and messages. Match order is CLASSES order.
AGENT_RE = re.compile(_class("agent")["match"])
REPAIR_RE = re.compile(_class("repair")["match"])
CHORE_RE = re.compile(_class("chore")["match"])
CHORE_ALLOW: list[str] = list(_class("chore")["allow"])
ROLES: dict[str, list[str]] = dict(_class("agent")["roles"])


class BranchClass(NamedTuple):
    name: str
    allow: list[str] | None
    deny: list[str]
    no_brief: bool
    role: str | None = None
    task: str | None = None


def run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def changed(base: str) -> list[str]:
    # --no-renames: a moved file is a delete plus an add, and both are judged.
    return sorted(
        p
        for p in run("git", "diff", "--name-only", "--no-renames", f"{base}...HEAD").splitlines()
        if p.strip()
    )


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


def bound_allow(c: dict, matched: re.Match[str]) -> list[str] | None:
    """Allow list for a class that has no roles.

    ``None`` stays unrestricted. ``{task}`` is replaced from the match's named
    group ``task``. A placeholder whose match has no such group is a bad config.
    """
    allow = c.get("allow")
    if allow is None:
        return None
    globs = [str(g) for g in allow]
    if not any("{task}" in g for g in globs):
        return globs
    if "task" not in matched.re.groupindex:
        raise ValueError(
            "scope_check: FAIL class "
            f"{c['name']!r} allow uses {{task}} but its match has no task group"
        )
    task = matched.group("task")
    return [g.replace("{task}", task) for g in globs]


def classify(
    branch: str,
    actor: str | None,
    owners: frozenset[str],
    author: str | None = None,
) -> BranchClass:
    """Return the branch class, in CLASSES order (agent first, plan §3.1)."""
    kind, who = principal(actor, author)
    for c in CLASSES:
        m = re.match(c["match"], branch)
        if not m:
            continue
        if c.get("owner_only") and not actor_is_owner(who, owners):
            raise ValueError(
                f"scope_check: FAIL branch {branch!r} class {c['name']} is not authorized "
                f"for {kind} {who!r}"
            )
        if "roles" in c:
            task = m.group("task")
            role = m.group("role")
            if role not in c["roles"]:
                raise ValueError(
                    f"scope_check: FAIL branch {branch!r} class {c['name']} role {role!r} "
                    f"has no write set (roles: {', '.join(sorted(c['roles']))})"
                )
            allow = [g.replace("{task}", task) for g in c["roles"][role]]
            return BranchClass(c["name"], allow, _deny_of(c), bool(c.get("no_brief")), role, task)
        task = m.group("task") if "task" in m.re.groupindex else None
        return BranchClass(
            c["name"], bound_allow(c, m), _deny_of(c), bool(c.get("no_brief")), None, task
        )
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
        prefixes = ", ".join(f"{c['name']}: {c['match']}" for c in CLASSES)
        if "has no write set" in str(e):
            print("  an agent branch names a role that has a write set in gate_config scope")
        elif "has no task group" in str(e):
            print("  a non-role allow list uses {task} only when its match names a task group")
        elif "matches no branch class" not in str(e):
            print("  repair/ and chore/ require the pull-request author (--author),")
            print("  or --actor when there is no pull request, on the --owners allowlist")
        print(f"  classes: {prefixes}")
        return 1

    files = changed(args.base)
    kind, who = principal(actor, author)
    role_note = f" role={cls.role} task={cls.task}" if cls.role else ""
    print(
        f"scope_check: branch={branch} class={cls.name}{role_note} {kind}={who!r} "
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
            print(f"  {cls.name}{' ' + cls.role if cls.role else ''} may touch: {cls.allow}")
        print(f"  no class but repair may touch: {DENY}")
        if cls.no_brief:
            print("  a task brief tasks/<name>.md is the owner's; an agent writes only under tasks/TASK-N/")
        return 1

    print("scope_check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
