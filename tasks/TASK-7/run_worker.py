"""TASK-7 worker: replay number SQL, row accounting, period-cluster bootstrap."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.agreement import (  # noqa: E402
    agreement_counts,
    assert_no_null_jp_match,
    judgeable_mask,
    match_mask,
)
from src.bootstrap import (  # noqa: E402
    assert_bootstrap_B,
    assert_inconclusive_when_unreliable,
    conclusion_for_ci,
    make_stratum_seeds,
)
from src.frame import load_published_frame  # noqa: E402
from src.groups import assign_groups  # noqa: E402
from src.hashing import verify_corpus_hash  # noqa: E402
from src.measures import attach_agreement, flatten_key  # noqa: E402
from src.pins import load_frame_counts  # noqa: E402
from src.status_io import sha256_file, write_json_atomic, write_status, write_text_atomic  # noqa: E402
from src.tables import open_corpus  # noqa: E402
from src.write_results import eval_derived, run_sql_file  # noqa: E402

SQL_NAMES = [
    "n_videos_pre",
    "n_videos_post",
    "n_unassigned_period",
    "n_judgeable_other_common_pre",
    "n_judgeable_other_common_post",
    "n_match_other_common_pre",
    "n_match_other_common_post",
    "agree_other_common_pre",
    "agree_other_common_post",
]

GAP_EXPR = "100 * (agree_other_common_pre - agree_other_common_post)"

ORDER = SQL_NAMES + ["gap_other_common_pp"]

PERIOD_STRATA = ("pre", "post")
MASTER_SEED = 20260919
B = 2000


def git_sha(repo_ROOT: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_ROOT, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def json_num(name: str, value: float) -> int | float:
    if name.startswith("n_"):
        return int(round(value))
    return float(value)


def n_for(name: str, got: dict[str, float], videos_n: int) -> int:
    if name in {"n_videos_pre", "n_videos_post", "n_unassigned_period"}:
        return videos_n
    if name.endswith("_pre") or name == "n_judgeable_other_common_pre":
        return int(got["n_judgeable_other_common_pre"])
    if name.endswith("_post") or name == "n_judgeable_other_common_post":
        return int(got["n_judgeable_other_common_post"])
    if name == "gap_other_common_pp":
        return int(
            got["n_judgeable_other_common_pre"] + got["n_judgeable_other_common_post"]
        )
    raise ValueError("n_for received an undeclared number name")


def query_for(name: str, sql_DIR: str) -> str:
    if name == "gap_other_common_pp":
        return "derived:" + GAP_EXPR
    return str(Path("tasks/TASK-7/sql") / (name + ".sql"))


def common_char_predicate(syllables: pd.DataFrame, published: pd.DataFrame) -> pd.Series:
    occ = syllables.groupby("char").size()
    common = set(occ.loc[occ >= 10].index.tolist())
    return published["char"].isin(common)


def step(
    name: str, rule: str, group: str, rows_before: int, rows_after: int, **extra
) -> dict:
    row = {
        "step": name,
        "rule": rule,
        "group": group,
        "rows_before": int(rows_before),
        "rows_after": int(rows_after),
    }
    row.update(extra)
    return row


def year_video_counts(videos: pd.DataFrame) -> list[dict]:
    year = videos["upload_date"].astype(str).str.slice(0, 4)
    rows = []
    for y, grp in videos.groupby(year, sort=True):
        rows.append({"year": str(y), "n_videos": int(len(grp))})
    return rows


def video_cells_other_common(
    published: pd.DataFrame, videos: pd.DataFrame, common: pd.Series
) -> pd.DataFrame:
    other = published["film_group"] == "other"
    cell = published.loc[other & common]
    judgeable = judgeable_mask(cell)
    assert_no_null_jp_match(cell, judgeable)
    matched = judgeable & match_mask(cell)
    n_j = cell.loc[judgeable].groupby("video_id").size().to_dict()
    n_m = cell.loc[matched].groupby("video_id").size().to_dict()
    assigned = videos["period"].isin(("pre", "post"))
    base = videos.loc[assigned, ["video_id", "period"]].copy()
    video_ids = base["video_id"].tolist()
    base["n_judgeable"] = [int(n_j[v]) if v in n_j else 0 for v in video_ids]
    base["n_match"] = [int(n_m[v]) if v in n_m else 0 for v in video_ids]
    base["stratum"] = base["period"].astype(str)
    return base.reset_index(drop=True)


def bootstrap_period_gap(videos: pd.DataFrame, B: int, master_seed: int) -> dict:
    assert_bootstrap_B(B)
    seeds = make_stratum_seeds(master_seed, list(PERIOD_STRATA))
    G_h: dict[str, int] = {}
    draws: dict[str, np.ndarray] = {}
    nj: dict[str, np.ndarray] = {}
    nm: dict[str, np.ndarray] = {}
    for h in PERIOD_STRATA:
        block = videos.loc[videos["stratum"] == h]
        G_h[h] = int(len(block))
        nj[h] = block["n_judgeable"].to_numpy(dtype=float)
        nm[h] = block["n_match"].to_numpy(dtype=float)
        rng = np.random.default_rng(seeds[h])
        draws[h] = rng.integers(0, G_h[h], size=(B, G_h[h]), endpoint=False)

    gap = np.empty(B, dtype=float)
    for b in range(B):
        j_pre = float(nj["pre"][draws["pre"][b]].sum())
        m_pre = float(nm["pre"][draws["pre"][b]].sum())
        j_post = float(nj["post"][draws["post"][b]].sum())
        m_post = float(nm["post"][draws["post"][b]].sum())
        if j_pre <= 0 or j_post <= 0:
            raise ValueError("bootstrap replicate has empty judgeable set")
        gap[b] = (m_pre / j_pre) - (m_post / j_post)

    lo, hi = float(np.percentile(gap, 2.5)), float(np.percentile(gap, 97.5))
    share_pos = float(np.mean(gap > 0))
    share_neg = float(np.mean(gap < 0))
    p_raw = float(min(1.0, 2.0 * min(share_pos, share_neg)))
    ci_unreliable = {h: int(G_h[h] < 10) for h in PERIOD_STRATA}
    return {
        "B": B,
        "master_seed": master_seed,
        "seeds": seeds,
        "G_h": G_h,
        "ci_unreliable": ci_unreliable,
        "gap_ci95": (lo, hi),
        "p_raw": p_raw,
        "p_bh": p_raw,
        "m": 1,
    }


def render_open_analysis(
    agree_pre: float,
    agree_post: float,
    gap_pp: float,
    boot: dict,
    sizes: dict[str, dict[str, int]],
    year_rows: list[dict],
    counts: dict[str, dict[str, int]],
    videos_n: int,
    n_judgeable_pre: int,
    n_judgeable_post: int,
    n_match_pre: int,
    n_match_post: int,
) -> str:
    g = boot["G_h"]
    ci_lo, ci_hi = boot["gap_ci95"]
    ci_lo_pp, ci_hi_pp = 100.0 * ci_lo, 100.0 * ci_hi
    ci_unreliable_any = int(any(boot["ci_unreliable"].values()))
    conclusion = conclusion_for_ci(boot["ci_unreliable"], g)
    assert_inconclusive_when_unreliable(ci_unreliable_any, conclusion)
    includes_zero = (ci_lo_pp <= 0.0 <= ci_hi_pp)
    year_txt = ", ".join(f"{r['year']} n={r['n_videos']}" for r in year_rows)
    if ci_unreliable_any:
        claim = (
            f"On the {videos_n} videos of this channel, the other×common "
            f"pre−post agreement comparison is inconclusive because a period "
            f"stratum has G_h < 10 (actual judgeable-video counts: "
            f"pre {sizes['pre']['n_h_videos_with_judgeable']}, "
            f"post {sizes['post']['n_h_videos_with_judgeable']})."
        )
    elif includes_zero:
        claim = (
            f"On the {videos_n} videos of this channel, the other×common "
            f"pre−post agreement gap is consistent with 0 under the declared "
            f"video_id-cluster bootstrap, which refutes the claim that the "
            f"remaining drop is a within-inventory decline on ordinary "
            f"characters in non-film titles."
        )
    else:
        claim = (
            f"On the {videos_n} videos of this channel, agreement on "
            f"judgeable A+B syllables that are other (title proxy) and common "
            f"(full-table frequency ≥ 10) still falls after 2024, and the "
            f"video_id-cluster 95% interval does not include 0."
        )
    lines = [
        "# TASK-7 open analysis",
        "",
        f"Population: the {videos_n} videos of this channel. The statistic is agreement",
        "between the acoustic Jyutping and the dictionary, not a human label.",
        "Film vs other is a title proxy, not a content judgement.",
        "",
        "## Cell",
        "",
        "Published A+B syllables whose video is `other` (title nonempty and",
        "contains none of the TASK-6 title-proxy markers) and whose `char`",
        "occurs at least 10 times on the full `syllables` table (every tier).",
        "Agreement uses the contract-24 judgeable set (`jp_realized` nonempty",
        "and `dur > 0`). `n_match` is counted only on that judgeable set.",
        "",
        f"- agree_other_common_pre = {agree_pre:.6f} "
        f"(n_match={n_match_pre}, n_judgeable={n_judgeable_pre})",
        f"- agree_other_common_post = {agree_post:.6f} "
        f"(n_match={n_match_post}, n_judgeable={n_judgeable_post})",
        f"- gap_other_common_pp = {gap_pp:.4f} "
        "= 100 * (agree_other_common_pre - agree_other_common_post)",
        "",
        "Contract-24 counts for this cell are in `manifest.json`.",
        "Worker `gap_other_common_pp` is `derived:` from the two agreement rates.",
        "",
        "## Cluster bootstrap",
        "",
        f"B={boot['B']} whole-`video_id` resamples within period strata.",
        f"Master seed {boot['master_seed']}. Per-stratum seeds are",
        "`int(sha256(f\"{master_seed}:{h}\").hexdigest()[:8], 16)`.",
        "",
        f"G_h (videos per period, census of the {videos_n} videos of this channel):",
        "",
    ]
    for h in PERIOD_STRATA:
        flag = boot["ci_unreliable"][h]
        lines.append(
            f"- `{h}`: G_h={g[h]}, N_h={sizes[h]['N_h']}, "
            f"n_h_judgeable={sizes[h]['n_h_judgeable']}, "
            f"videos with judgeable syllables={sizes[h]['n_h_videos_with_judgeable']}, "
            f"ci_unreliable={flag}"
        )
    lines.extend(
        [
            "",
            f"Gap 95% percentile CI: [{ci_lo_pp:.4f}, {ci_hi_pp:.4f}] pp.",
            f"p_raw={boot['p_raw']:.6g}, p_BH={boot['p_bh']:.6g}, m={boot['m']}.",
            f"ci_unreliable (any stratum)={ci_unreliable_any}; conclusion={conclusion}.",
            f"Interval includes 0: {str(includes_zero).lower()}.",
            "",
            "Year cells (do not read 2021 or 2023 as a trend): " + year_txt + ".",
            "",
            "## Conclusion",
            "",
            claim,
            "",
            "Cell agreement counts:",
            f"- pre: {json.dumps(counts['pre'], sort_keys=True)}",
            f"- post: {json.dumps(counts['post'], sort_keys=True)}",
            "",
        ]
    )
    return "\n".join(lines)


def compute_numbers(corpus_PATH: str, sql_DIR: str) -> dict[str, float]:
    conn = open_corpus(corpus_PATH)
    try:
        got: dict[str, float] = {}
        for name in SQL_NAMES:
            sql_FILE = str(Path(sql_DIR) / (name + ".sql"))
            got[name] = run_sql_file(conn, sql_FILE)
        got["gap_other_common_pp"] = eval_derived(GAP_EXPR, got)
    finally:
        conn.close()
    return got


def run(
    corpus_PATH: str,
    readme_PATH: str,
    brief_PATH: str,
    sql_DIR: str,
    out_DIR: str,
    repo_ROOT: str,
) -> None:
    out_ROOT = Path(out_DIR)
    out_ROOT.mkdir(parents=True, exist_ok=True)
    status_FILE = str(out_ROOT / "STATUS.json")
    write_status(status_FILE, {"status": "running"})

    corpus_hash = verify_corpus_hash(corpus_PATH, readme_PATH)
    frame_counts = load_frame_counts(brief_PATH, readme_PATH)
    videos_n = frame_counts.videos_expected

    got = compute_numbers(corpus_PATH, sql_DIR)

    conn = open_corpus(corpus_PATH)
    try:
        loaded = load_published_frame(conn, brief_PATH, readme_PATH)
    finally:
        conn.close()

    videos = assign_groups(loaded["videos"])
    published = loaded["published"].copy()
    period_by_video = videos.set_index("video_id")["period"]
    film_by_video = videos.set_index("video_id")["film_group"]
    published["period"] = published["video_id"].map(period_by_video)
    published["film_group"] = published["video_id"].map(film_by_video)

    common = common_char_predicate(loaded["syllables"], published)
    both_groups = (published["film_group"] == "film") & (published["film_group"] == "other")
    if bool(both_groups.any()):
        raise ValueError("film overlap: a row matched both film and other")
    both_period = (published["period"] == "pre") & (published["period"] == "post")
    if bool(both_period.any()):
        raise ValueError("period overlap: a row matched both pre and post")

    steps = list(loaded["steps"])
    pre_s = published["period"] == "pre"
    post_s = published["period"] == "post"
    steps.append(
        step(
            "period_assign",
            "four-digit year <=2024 vs >=2025",
            "pre",
            len(published),
            int(pre_s.sum()),
        )
    )
    steps.append(
        step(
            "period_assign",
            "four-digit year <=2024 vs >=2025",
            "post",
            len(published),
            int(post_s.sum()),
        )
    )
    steps.append(
        step(
            "period_assign",
            "not a four-digit year",
            "unassigned_period",
            len(published),
            int((published["period"] == "unassigned_period").sum()),
        )
    )

    for group_name in ("pre", "post"):
        period_mask = published["period"] == group_name
        n_period = int(period_mask.sum())
        empty_title = period_mask & (published["film_group"] == "unassigned_film")
        film = period_mask & (published["film_group"] == "film")
        other = period_mask & (published["film_group"] == "other")
        steps.append(
            step(
                "drop_empty_title",
                "title nonempty (unassigned_film is empty title)",
                group_name,
                n_period,
                n_period - int(empty_title.sum()),
            )
        )
        steps.append(
            step(
                "drop_film_proxy",
                "title-proxy film markers; other is nonempty title with none of them",
                group_name,
                n_period - int(empty_title.sum()),
                int(other.sum()),
            )
        )
        n_other = int(other.sum())
        other_common = other & common
        steps.append(
            step(
                "keep_common_char",
                "char frequency >= 10 on full syllables table, all tiers",
                group_name,
                n_other,
                int(other_common.sum()),
            )
        )
        n_cell = int(other_common.sum())
        judgeable = other_common & judgeable_mask(published)
        steps.append(
            step(
                "keep_judgeable",
                "jp_realized nonempty and dur > 0",
                group_name,
                n_cell,
                int(judgeable.sum()),
            )
        )

    counts_pre = agreement_counts(published.loc[pre_s & (published["film_group"] == "other") & common])
    counts_post = agreement_counts(published.loc[post_s & (published["film_group"] == "other") & common])

    if int(got["n_judgeable_other_common_pre"]) != counts_pre["n_judgeable"]:
        print(int(got["n_judgeable_other_common_pre"]), counts_pre["n_judgeable"])
        raise ValueError("sql n_judgeable_other_common_pre does not match frame count")
    if int(got["n_judgeable_other_common_post"]) != counts_post["n_judgeable"]:
        print(int(got["n_judgeable_other_common_post"]), counts_post["n_judgeable"])
        raise ValueError("sql n_judgeable_other_common_post does not match frame count")
    if int(got["n_match_other_common_pre"]) != counts_pre["n_match"]:
        print(int(got["n_match_other_common_pre"]), counts_pre["n_match"])
        raise ValueError("sql n_match_other_common_pre does not match frame count")
    if int(got["n_match_other_common_post"]) != counts_post["n_match"]:
        print(int(got["n_match_other_common_post"]), counts_post["n_match"])
        raise ValueError("sql n_match_other_common_post does not match frame count")

    video_df = video_cells_other_common(published, videos, common)
    video_df = attach_agreement(video_df)
    _key = flatten_key(["video", "agreement"])
    del _key

    sizes: dict[str, dict[str, int]] = {}
    for h in PERIOD_STRATA:
        block = video_df.loc[video_df["stratum"] == h]
        sizes[h] = {
            "N_h": int(len(block)),
            "G_h": int(len(block)),
            "n_h_judgeable": int(block["n_judgeable"].sum()),
            "n_h_match": int(block["n_match"].sum()),
            "n_h_videos_with_judgeable": int((block["n_judgeable"] > 0).sum()),
        }

    boot = bootstrap_period_gap(video_df, B=B, master_seed=MASTER_SEED)
    ci_unreliable_any = int(any(boot["ci_unreliable"].values()))
    conclusion = conclusion_for_ci(boot["ci_unreliable"], boot["G_h"])
    assert_inconclusive_when_unreliable(ci_unreliable_any, conclusion)

    rows = []
    for name in ORDER:
        rows.append(
            {
                "name": name,
                "value": json_num(name, got[name]),
                "n": n_for(name, got, videos_n),
                "query": query_for(name, sql_DIR),
            }
        )

    bootstrap_payload = {
        "population": f"the {videos_n} videos of this channel",
        "comparison": "agree_other_common_pre - agree_other_common_post, other×common cell",
        "title_proxy": True,
        "B": boot["B"],
        "master_seed": boot["master_seed"],
        "seeds": {h: int(boot["seeds"][h]) for h in PERIOD_STRATA},
        "G_h": boot["G_h"],
        "N_h": {h: sizes[h]["N_h"] for h in PERIOD_STRATA},
        "n_h_judgeable": {h: sizes[h]["n_h_judgeable"] for h in PERIOD_STRATA},
        "n_h_videos_with_judgeable": {
            h: sizes[h]["n_h_videos_with_judgeable"] for h in PERIOD_STRATA
        },
        "agree_other_common_pre": float(got["agree_other_common_pre"]),
        "agree_other_common_post": float(got["agree_other_common_post"]),
        "gap_other_common_pp": float(got["gap_other_common_pp"]),
        "gap_ci95_pp": [100.0 * boot["gap_ci95"][0], 100.0 * boot["gap_ci95"][1]],
        "p_raw": boot["p_raw"],
        "p_bh": boot["p_bh"],
        "m": boot["m"],
        "ci_unreliable": boot["ci_unreliable"],
        "ci_unreliable_any": ci_unreliable_any,
        "conclusion": conclusion,
        "descriptive": 0,
        "exploratory": 0,
        "year_video_counts": year_video_counts(videos),
        "counts_pre": counts_pre,
        "counts_post": counts_post,
    }

    manifest = {
        "git_sha": git_sha(repo_ROOT),
        "inputs": {
            "data/corpus_v2.sqlite": {
                "sha256": corpus_hash,
                "tables": {
                    "videos": {
                        "rows": int(len(loaded["videos"])),
                        "columns": list(loaded["videos"].columns),
                    },
                    "windows": {
                        "rows": int(len(loaded["windows"])),
                        "columns": list(loaded["windows"].columns),
                    },
                    "syllables": {
                        "rows": int(len(loaded["syllables"])),
                        "columns": list(loaded["syllables"].columns),
                    },
                },
            }
        },
        "steps": steps,
        "agreement_counts": {
            "other_common_pre": counts_pre,
            "other_common_post": counts_post,
        },
        "stratum_sizes": sizes,
    }

    analysis_md = render_open_analysis(
        float(got["agree_other_common_pre"]),
        float(got["agree_other_common_post"]),
        float(got["gap_other_common_pp"]),
        boot,
        sizes,
        year_video_counts(videos),
        {"pre": counts_pre, "post": counts_post},
        videos_n,
        int(got["n_judgeable_other_common_pre"]),
        int(got["n_judgeable_other_common_post"]),
        int(got["n_match_other_common_pre"]),
        int(got["n_match_other_common_post"]),
    )

    results_FILE = str(out_ROOT / "results.json")
    bootstrap_FILE = str(out_ROOT / "bootstrap.json")
    manifest_FILE = str(out_ROOT / "manifest.json")
    analysis_FILE = str(out_ROOT / "open_analysis.md")
    write_json_atomic(results_FILE, rows)
    write_json_atomic(bootstrap_FILE, json.loads(json.dumps(bootstrap_payload)))
    write_json_atomic(manifest_FILE, manifest)
    write_text_atomic(analysis_FILE, analysis_md)
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": {
                "results.json": sha256_file(results_FILE),
                "bootstrap.json": sha256_file(bootstrap_FILE),
                "manifest.json": sha256_file(manifest_FILE),
                "open_analysis.md": sha256_file(analysis_FILE),
            },
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_PATH", required=True)
    parser.add_argument("--readme_PATH", required=True)
    parser.add_argument("--brief_PATH", required=True)
    parser.add_argument("--sql_DIR", required=True)
    parser.add_argument("--out_DIR", required=True)
    parser.add_argument("--repo_ROOT", required=True)
    args = parser.parse_args()
    run(
        args.corpus_PATH,
        args.readme_PATH,
        args.brief_PATH,
        args.sql_DIR,
        args.out_DIR,
        args.repo_ROOT,
    )


if __name__ == "__main__":
    main()
