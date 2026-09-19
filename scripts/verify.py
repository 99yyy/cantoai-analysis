#!/usr/bin/env python3
"""Local entrypoint whose commands match CI.

    ./verify                 pytest + output-check + relations;
                             on a pull request, also scope-check and history-audit
    ./verify task N          output-check + relations for TASK-N
    ./verify relations N     double/permute/identities for TASK-N
    ./verify probe           known-red probes in a throwaway tree;
                             exit 0 only if they go red

Calls the existing scripts. Does not reimplement their rules.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT_CHECK = HERE / "output_check.py"
RELATIONS = HERE / "relations.py"
SCOPE_CHECK = HERE / "scope_check.py"
HISTORY_AUDIT = HERE / "history_audit.py"
FIXTURE_RELATIONS = ROOT / "tests" / "fixtures" / "relations_probe"

USAGE = """usage: ./verify [task N | relations N | probe]
  ./verify              full suite (pytest, output-check, relations; PR: scope-check, history-audit)
  ./verify task N       output-check + relations for TASK-N
  ./verify relations N  double/permute/identities for TASK-N
  ./verify probe        known-red probes; exit 0 iff they go red"""

CONSTANT_SQL = "SELECT 12345;\n"


def print_usage() -> int:
    print(USAGE)
    return 2


def parse_argv(argv: list[str]) -> tuple[str, str | None]:
    if not argv:
        return "full", None
    if argv == ["probe"]:
        return "probe", None
    if len(argv) == 2 and argv[0] == "task":
        return "task", argv[1]
    if len(argv) == 2 and argv[0] == "relations":
        return "relations", argv[1]
    raise SystemExit(print_usage())


def step(label: str) -> None:
    print(f"verify: {label}")
    sys.stdout.flush()


def step_pass(label: str) -> None:
    print(f"verify: {label} PASS")
    sys.stdout.flush()


def step_fail(label: str) -> None:
    print(f"verify: {label} FAIL")
    sys.stdout.flush()


def step_skip(label: str, why: str) -> None:
    print(f"verify: {label} SKIP ({why})")
    sys.stdout.flush()


def git_out(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "").strip()


def owner_from_origin(root: Path) -> str | None:
    code, url = git_out(root, "remote", "get-url", "origin")
    if code != 0 or not url:
        return None
    text = url.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    if "github.com:" in text:
        rest = text.split("github.com:", 1)[1]
        return rest.split("/")[0] or None
    if "github.com/" in text:
        rest = text.split("github.com/", 1)[1]
        return rest.split("/")[0] or None
    return None


def looks_like_pull_request(root: Path) -> bool:
    event = os.environ.get("GITHUB_EVENT_NAME")
    if event == "pull_request":
        return True
    if event in {"push", "schedule"}:
        return False
    code, branch = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return False
    if branch == "main":
        return False
    if branch == "HEAD":
        c1, head = git_out(root, "rev-parse", "HEAD")
        c2, main = git_out(root, "rev-parse", "origin/main")
        return not (c1 == 0 and c2 == 0 and head == main)
    return True


def resolve_base_ref(root: Path) -> str | None:
    explicit = os.environ.get("VERIFY_BASE")
    if explicit is None:
        explicit = os.environ.get("GITHUB_BASE_REF")
    if explicit:
        if "/" not in explicit:
            return f"origin/{explicit}"
        return explicit
    code, _ = git_out(root, "rev-parse", "--verify", "origin/main")
    if code == 0:
        return "origin/main"
    return None


def python_cmd() -> str:
    return sys.executable


def run_script(
    label: str,
    script_PATH: Path,
    args: list[str],
    *,
    cwd: Path | None = None,
) -> int:
    if not script_PATH.is_file():
        step_skip(label, f"{script_PATH.as_posix()} not present")
        return 0
    step(label)
    proc = subprocess.run(
        [python_cmd(), str(script_PATH), *args],
        cwd=str(cwd if cwd is not None else ROOT),
    )
    if proc.returncode != 0:
        step_fail(label)
        return proc.returncode
    step_pass(label)
    return 0


def run_script_captured(
    script_PATH: Path,
    args: list[str],
    cwd: Path,
) -> tuple[int, str]:
    proc = subprocess.run(
        [python_cmd(), str(script_PATH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def run_pytest() -> int:
    tests_DIR = ROOT / "tests"
    has = False
    if tests_DIR.is_dir():
        for _ in tests_DIR.rglob("test_*.py"):
            has = True
            break
    if not has:
        step_skip("pytest", "no tests/test_*.py yet")
        return 0
    step("pytest")
    env = os.environ.copy()
    env["VERIFY_RUNNING"] = "1"
    proc = subprocess.run(
        [python_cmd(), "-m", "pytest", "-q"],
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        step_fail("pytest")
        return proc.returncode
    step_pass("pytest")
    return 0


def output_check_args(task: str | None, *, pull_request: bool) -> list[str]:
    args = ["--repo-root", str(ROOT), "--head-ref", "HEAD"]
    if task is not None:
        args.extend(["--task", task])
        return args
    if pull_request:
        base = resolve_base_ref(ROOT)
        if base is not None:
            args.extend(["--base-ref", base])
    return args


def relations_args(task: str | None) -> list[str]:
    args = ["--repo-root", str(ROOT), "--head-ref", "HEAD"]
    if task is not None:
        args.extend(["--task", task])
    return args


def run_output_check(task: str | None, *, pull_request: bool) -> int:
    return run_script(
        "output-check",
        OUTPUT_CHECK,
        output_check_args(task, pull_request=pull_request),
    )


def run_relations(task: str | None) -> int:
    return run_script("relations", RELATIONS, relations_args(task))


def run_scope_check() -> int:
    if not SCOPE_CHECK.is_file():
        step_skip("scope-check", f"{SCOPE_CHECK.as_posix()} not present")
        return 0
    base = resolve_base_ref(ROOT)
    if base is None:
        step_skip("scope-check", "origin/main not present")
        return 0
    code, branch = git_out(ROOT, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0 or not branch or branch == "HEAD":
        step_skip("scope-check", "no named branch")
        return 0
    actor = os.environ.get("GITHUB_ACTOR")
    if actor is None:
        actor = os.environ.get("VERIFY_ACTOR")
    owners = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if owners is None:
        owners = os.environ.get("VERIFY_OWNERS")
    if owners is None:
        owners = owner_from_origin(ROOT)
    if actor is None:
        actor = owners
    if not actor or not owners:
        step_skip("scope-check", "GITHUB_ACTOR not set")
        return 0
    return run_script(
        "scope-check",
        SCOPE_CHECK,
        [
            "--branch",
            branch,
            "--base",
            base,
            "--actor",
            actor,
            "--owners",
            owners,
        ],
    )


def run_history_audit() -> int:
    if not HISTORY_AUDIT.is_file():
        step_skip("history-audit", f"{HISTORY_AUDIT.as_posix()} not present")
        return 0
    base = resolve_base_ref(ROOT)
    if base is None:
        step_skip("history-audit", "origin/main not present")
        return 0
    body_FILE = os.environ.get("VERIFY_PR_BODY_FILE")
    tmp_DIR = None
    if body_FILE is None:
        tmp_DIR = Path(tempfile.mkdtemp(prefix="verify-pr-body-"))
        body_PATH = tmp_DIR / "pr_body.txt"
        body_PATH.write_text("", encoding="utf-8")
        body_FILE = str(body_PATH)
    try:
        return run_script(
            "history-audit",
            HISTORY_AUDIT,
            ["--base", base, "--pr-body-file", body_FILE],
        )
    finally:
        if tmp_DIR is not None:
            shutil.rmtree(tmp_DIR, ignore_errors=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_mini_corpus(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE videos(
            video_id TEXT PRIMARY KEY, title TEXT, upload_date TEXT
        );
        CREATE TABLE windows(
            uid TEXT PRIMARY KEY, video_id TEXT, tier TEXT
        );
        CREATE TABLE syllables(
            syl_id TEXT PRIMARY KEY, uid TEXT, video_id TEXT,
            char TEXT, jp_match TEXT, jp_realized TEXT, dur REAL
        );
        CREATE TABLE runs(git_sha TEXT);
        """
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('v1', '粵劇', '20240101')"
    )
    conn.execute(
        "INSERT INTO videos(video_id, title, upload_date) VALUES ('v2', '日常', '20250101')"
    )
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w1', 'v1', 'A')")
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w2', 'v2', 'B')")
    conn.execute("INSERT INTO windows(uid, video_id, tier) VALUES ('w3', 'v2', 'C')")
    rows = [
        ("s1", "w1", "v1", "甲", "exact_default", "aa3", 0.1),
        ("s2", "w1", "v1", "乙", "tone", "bb2", 0.1),
        ("s3", "w2", "v2", "丙", "tone", "cc1", 0.1),
        ("s4", "w3", "v2", "丁", "tone", "dd1", 0.1),
    ]
    conn.executemany(
        "INSERT INTO syllables(syl_id, uid, video_id, char, jp_match, jp_realized, dur) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO runs(git_sha) VALUES ('probe')")
    conn.commit()
    conn.close()


def write_brief(repo: Path, names: list[tuple[str, str]]) -> None:
    md = repo / "tasks" / "TASK-9.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# TASK-9\n", "status: open\n", "```numbers\n"]
    for name, tol in names:
        lines.append(f"{name}  {tol}\n")
    lines.append("```\n")
    md.write_text("".join(lines), encoding="utf-8")


def write_side(
    repo: Path,
    names: list[tuple[str, float, str, str]],
) -> None:
    dest = repo / "tasks" / "TASK-9" / "sql"
    dest.mkdir(parents=True, exist_ok=True)
    payload = []
    for name, value, sql_name, sql_text in names:
        (dest / sql_name).write_text(sql_text, encoding="utf-8")
        payload.append(
            {
                "name": name,
                "value": value,
                "n": 1,
                "query": f"tasks/TASK-9/sql/{sql_name}",
            }
        )
    out = repo / "tasks" / "TASK-9" / "results.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def pin_readme(repo: Path, corpus: Path) -> None:
    (repo / "README.md").write_text(
        f"sha256: `{sha256_file(corpus)}`\n", encoding="utf-8"
    )


def probe_constant_sql(tmp_DIR: Path) -> tuple[bool, str]:
    """Constant SELECT must fail the corpus-plan gate."""
    repo = tmp_DIR / "constant"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    write_mini_corpus(corpus)
    pin_readme(repo, corpus)
    write_brief(repo, [("n_count", "0")])
    write_side(repo, [("n_count", 12345.0, "n_count.sql", CONSTANT_SQL)])
    code, out = run_script_captured(
        OUTPUT_CHECK,
        ["--repo-root", str(repo), "--corpus", str(corpus)],
        cwd=repo,
    )
    went_red = code != 0 and "EXPLAIN QUERY PLAN" in out
    return went_red, out


def probe_relations_literal_denom(tmp_DIR: Path) -> tuple[bool, str]:
    """Hardcoded COUNT(*) denominator must fail double; original replay still matches."""
    if not FIXTURE_RELATIONS.is_dir():
        return False, f"missing {FIXTURE_RELATIONS.as_posix()}"
    rate_sql_PATH = FIXTURE_RELATIONS / "rate_tone_pre_pm.sql"
    n_sql_PATH = FIXTURE_RELATIONS / "n_count.sql"
    rare_sql_PATH = FIXTURE_RELATIONS / "rare_share_pre.sql"
    missing = [p for p in (rate_sql_PATH, n_sql_PATH, rare_sql_PATH) if not p.is_file()]
    if missing:
        return False, f"missing {missing[0].as_posix()}"
    repo = tmp_DIR / "denom"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    write_mini_corpus(corpus)
    pin_readme(repo, corpus)
    write_brief(
        repo,
        [
            ("n_count", "0"),
            ("rate_tone_pre_pm", "0.5"),
            ("rare_share_pre", "0.0005"),
        ],
    )
    denom_sql_PATH = FIXTURE_RELATIONS / "tier_ab_count.sql"
    if not denom_sql_PATH.is_file():
        return False, f"missing {denom_sql_PATH.as_posix()}"
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    try:
        n_count = conn.execute(n_sql_PATH.read_text(encoding="utf-8")).fetchone()[0]
        rate = conn.execute(rate_sql_PATH.read_text(encoding="utf-8")).fetchone()[0]
        rare = conn.execute(rare_sql_PATH.read_text(encoding="utf-8")).fetchone()[0]
        denom = conn.execute(denom_sql_PATH.read_text(encoding="utf-8")).fetchone()[0]
    finally:
        conn.close()
    mutated = rate_sql_PATH.read_text(encoding="utf-8").replace(
        "/ COUNT(*)", f"/ {int(denom)}"
    )
    if "/ COUNT(*)" in mutated:
        return False, "probe did not replace COUNT(*) in rate_tone_pre_pm.sql"
    write_side(
        repo,
        [
            ("n_count", float(n_count), "n_count.sql", n_sql_PATH.read_text(encoding="utf-8")),
            ("rate_tone_pre_pm", float(rate), "rate_tone_pre_pm.sql", mutated),
            ("rare_share_pre", float(rare), "rare_share_pre.sql", rare_sql_PATH.read_text(encoding="utf-8")),
        ],
    )
    code, out = run_script_captured(
        RELATIONS,
        ["--repo-root", str(repo), "--corpus", str(corpus)],
        cwd=repo,
    )
    went_red = (
        code != 0
        and "relations: FAIL" in out
        and "rate_tone_pre_pm: double" in out
    )
    return went_red, out


def probe_result_out_of_turns(tmp_DIR: Path) -> tuple[bool, str]:
    """RESULT subtype out_of_turns while rewrite count is below cap must fail."""
    repo = tmp_DIR / "result"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    write_mini_corpus(corpus)
    pin_readme(repo, corpus)
    sha = sha256_file(corpus)
    md = repo / "tasks" / "TASK-7.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# TASK-7\n\nstatus: open\n\n```numbers\nn_count  0\n```\n",
        encoding="utf-8",
    )

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "probe@example.com")
    git("config", "user.name", "probe")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-m", "brief")

    w_sql = repo / "tasks" / "TASK-7" / "sql" / "count_videos.sql"
    v_sql = repo / "tasks" / "TASK-7" / "mine_sql" / "count_videos_as.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    v_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v_sql.write_text("SELECT COUNT(*) FROM videos AS vid;\n", encoding="utf-8")
    rows_w = [
        {
            "name": "n_count",
            "value": 2,
            "n": 2,
            "query": "tasks/TASK-7/sql/count_videos.sql",
        }
    ]
    rows_v = [
        {
            "name": "n_count",
            "value": 2,
            "n": 2,
            "query": "tasks/TASK-7/mine_sql/count_videos_as.sql",
        }
    ]
    (repo / "tasks" / "TASK-7" / "results.json").write_text(
        json.dumps(rows_w, indent=2) + "\n", encoding="utf-8"
    )
    (repo / "tasks" / "TASK-7" / "mine.json").write_text(
        json.dumps(rows_v, indent=2) + "\n", encoding="utf-8"
    )
    git("add", "-A")
    git("commit", "-m", "outputs")

    md.write_text(
        "# TASK-7\n\nstatus: closed\n"
        f"corpus_sha: {sha}\n\n```numbers\nn_count  0\n```\n",
        encoding="utf-8",
    )
    result = {
        "task": "TASK-7",
        "subtype": "out_of_turns",
        "verdict": None,
        "hypothesis": "Agreement falls after 2025.",
        "why": "The rewrite cap is 3.",
        "numbers": {"n_count": {"value": 2.0, "within_tol": True}},
        "turns_used": 3,
        "turn_cap": 3,
        "corpus_sha": sha,
        "forked_from": None,
        "fork_depth": 0,
    }
    (repo / "tasks" / "TASK-7" / "RESULT.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    git("add", "-A")
    git("commit", "-m", "close with lying RESULT")

    code, out = run_script_captured(
        OUTPUT_CHECK,
        [
            "--repo-root",
            str(repo),
            "--corpus",
            str(corpus),
            "--head-ref",
            "HEAD",
        ],
        cwd=repo,
    )
    went_red = (
        code != 0
        and "out_of_turns" in out
        and "rewrite count is 1" in out
        and "cap is 3" in out
    )
    return went_red, out


PARENT_NUMBERS = "```numbers\nn_count  0\n```\n"
PARENT_N = "```n\nn_count  2\n```\n"
MUTATED_NUMBERS = "```numbers\nn_count  1\n```\n"
FORK_HYPOTHESIS = "Agreement falls after 2025."
FORK_WHY = "n_count is 2."


def _git_in(repo: Path):
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    return git


def write_closed_parent(repo: Path, sha: str) -> None:
    """Closed TASK-7 with agreeing videos-count outputs and a refuted RESULT."""
    md = repo / "tasks" / "TASK-7.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# TASK-7\n\nstatus: open\n\nThe gap is film share.\n\n"
        + PARENT_NUMBERS
        + "\n"
        + PARENT_N,
        encoding="utf-8",
    )
    git = _git_in(repo)
    git("init", "-b", "main")
    git("config", "user.email", "probe@example.com")
    git("config", "user.name", "probe")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-m", "brief")

    w_sql = repo / "tasks" / "TASK-7" / "sql" / "count_videos.sql"
    v_sql = repo / "tasks" / "TASK-7" / "mine_sql" / "count_videos_as.sql"
    w_sql.parent.mkdir(parents=True, exist_ok=True)
    v_sql.parent.mkdir(parents=True, exist_ok=True)
    w_sql.write_text("SELECT COUNT(*) FROM videos;\n", encoding="utf-8")
    v_sql.write_text("SELECT COUNT(*) FROM videos AS vid;\n", encoding="utf-8")
    rows_w = [
        {
            "name": "n_count",
            "value": 2,
            "n": 2,
            "query": "tasks/TASK-7/sql/count_videos.sql",
        }
    ]
    rows_v = [
        {
            "name": "n_count",
            "value": 2,
            "n": 2,
            "query": "tasks/TASK-7/mine_sql/count_videos_as.sql",
        }
    ]
    (repo / "tasks" / "TASK-7" / "results.json").write_text(
        json.dumps(rows_w, indent=2) + "\n", encoding="utf-8"
    )
    (repo / "tasks" / "TASK-7" / "mine.json").write_text(
        json.dumps(rows_v, indent=2) + "\n", encoding="utf-8"
    )
    git("add", "-A")
    git("commit", "-m", "outputs")

    md.write_text(
        "# TASK-7\n\nstatus: closed\n"
        f"corpus_sha: {sha}\n\nThe gap is film share.\n\n"
        + PARENT_NUMBERS
        + "\n"
        + PARENT_N,
        encoding="utf-8",
    )
    result = {
        "task": "TASK-7",
        "subtype": "success",
        "verdict": "refuted",
        "hypothesis": FORK_HYPOTHESIS,
        "why": FORK_WHY,
        "numbers": {"n_count": {"value": 2.0, "within_tol": True}},
        "turns_used": 2,
        "turn_cap": 3,
        "corpus_sha": sha,
        "forked_from": None,
        "fork_depth": 0,
    }
    (repo / "tasks" / "TASK-7" / "RESULT.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    git("add", "-A")
    git("commit", "-m", "close with RESULT")


def prior_attempts_block() -> str:
    return (
        "## Prior Attempts\n\n"
        f"- parent: TASK-7\n"
        f"- hypothesis: {FORK_HYPOTHESIS}\n"
        f"- verdict: refuted\n"
        f"- why: {FORK_WHY}\n"
        f"- n_count: 2\n"
    )


def probe_fork_tolerance(tmp_DIR: Path) -> tuple[bool, str]:
    """TASK-N-b that changes one numbers tolerance vs parent must fail."""
    repo = tmp_DIR / "fork-tol"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    write_mini_corpus(corpus)
    pin_readme(repo, corpus)
    sha = sha256_file(corpus)
    write_closed_parent(repo, sha)

    child = repo / "tasks" / "TASK-7-b.md"
    child.write_text(
        "# TASK-7-b\n\nstatus: open\n\nThe gap is rare characters.\n\n"
        + MUTATED_NUMBERS
        + "\n"
        + PARENT_N
        + "\n"
        + prior_attempts_block(),
        encoding="utf-8",
    )
    git = _git_in(repo)
    git("add", "-A")
    git("commit", "-m", "fork with mutated tolerance")

    code, out = run_script_captured(
        OUTPUT_CHECK,
        [
            "--repo-root",
            str(repo),
            "--corpus",
            str(corpus),
            "--head-ref",
            "HEAD",
        ],
        cwd=repo,
    )
    went_red = (
        code != 0
        and "not byte-identical" in out
        and "```numbers" in out
        and "new task" in out
    )
    return went_red, out


def probe_fork_depth_d(tmp_DIR: Path) -> tuple[bool, str]:
    """Opening TASK-N-d when depth would exceed 2 must fail."""
    repo = tmp_DIR / "fork-d"
    repo.mkdir()
    corpus = repo / "mini.sqlite"
    write_mini_corpus(corpus)
    pin_readme(repo, corpus)
    sha = sha256_file(corpus)
    write_closed_parent(repo, sha)

    child = repo / "tasks" / "TASK-7-d.md"
    child.write_text(
        "# TASK-7-d\n\nstatus: open\n\nThe gap is rare characters.\n\n"
        + PARENT_NUMBERS
        + "\n"
        + PARENT_N
        + "\n"
        + prior_attempts_block(),
        encoding="utf-8",
    )
    git = _git_in(repo)
    git("add", "-A")
    git("commit", "-m", "illegal third fork -d")

    code, out = run_script_captured(
        OUTPUT_CHECK,
        [
            "--repo-root",
            str(repo),
            "--corpus",
            str(corpus),
            "--head-ref",
            "HEAD",
        ],
        cwd=repo,
    )
    went_red = (
        code != 0
        and "TASK-7-d" in out
        and "third fork" in out
        and "not open TASK-7-d" in out
    )
    return went_red, out


def run_probe() -> int:
    tmp_DIR = Path(tempfile.mkdtemp(prefix="verify-probe-"))
    failed = False
    try:
        step("probe constant-sql")
        red, out = probe_constant_sql(tmp_DIR)
        if not red:
            print(out)
            print("verify: probe constant-sql stayed green")
            failed = True
        else:
            print("verify: probe constant-sql went red")

        step("probe relations-literal-denom")
        red, out = probe_relations_literal_denom(tmp_DIR)
        if not red:
            print(out)
            print("verify: probe relations-literal-denom stayed green")
            failed = True
        else:
            print("verify: probe relations-literal-denom went red")

        step("probe result-out-of-turns")
        red, out = probe_result_out_of_turns(tmp_DIR)
        if not red:
            print(out)
            print("verify: probe result-out-of-turns stayed green")
            failed = True
        else:
            print("verify: probe result-out-of-turns went red")

        step("probe fork-tolerance")
        red, out = probe_fork_tolerance(tmp_DIR)
        if not red:
            print(out)
            print("verify: probe fork-tolerance stayed green")
            failed = True
        else:
            print("verify: probe fork-tolerance went red")

        step("probe fork-depth-d")
        red, out = probe_fork_depth_d(tmp_DIR)
        if not red:
            print(out)
            print("verify: probe fork-depth-d stayed green")
            failed = True
        else:
            print("verify: probe fork-depth-d went red")
    finally:
        shutil.rmtree(tmp_DIR, ignore_errors=True)
    if failed:
        print("verify: probe FAIL")
        return 1
    print("verify: probe PASS")
    return 0


def run_full() -> int:
    pull_request = looks_like_pull_request(ROOT)
    code = run_pytest()
    if code != 0:
        print("verify: FAIL")
        return code
    code = run_output_check(None, pull_request=pull_request)
    if code != 0:
        print("verify: FAIL")
        return code
    code = run_relations(None)
    if code != 0:
        print("verify: FAIL")
        return code
    if pull_request:
        code = run_scope_check()
        if code != 0:
            print("verify: FAIL")
            return code
        code = run_history_audit()
        if code != 0:
            print("verify: FAIL")
            return code
    else:
        step_skip("scope-check", "main; PR-only in CI")
        step_skip("history-audit", "main; PR-only in CI")
    print("verify: PASS")
    return 0


def run_task(task: str) -> int:
    code = run_output_check(task, pull_request=False)
    if code != 0:
        print("verify: FAIL")
        return code
    code = run_relations(task)
    if code != 0:
        print("verify: FAIL")
        return code
    print("verify: PASS")
    return 0


def run_relations_only(task: str) -> int:
    code = run_relations(task)
    if code != 0:
        print("verify: FAIL")
        return code
    print("verify: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    mode, task = parse_argv(list(sys.argv[1:] if argv is None else argv))
    if mode == "full":
        return run_full()
    if mode == "task" and task is not None:
        return run_task(task)
    if mode == "relations" and task is not None:
        return run_relations_only(task)
    if mode == "probe":
        return run_probe()
    return print_usage()


if __name__ == "__main__":
    sys.exit(main())
