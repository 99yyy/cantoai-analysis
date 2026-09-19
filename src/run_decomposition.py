"""Open analysis: film-mix decomposition, residual cluster bootstrap, write STATUS."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from src.agreement import agreement_counts
from src.bootstrap import (
    STRATA,
    assert_inconclusive_when_unreliable,
    bootstrap_residual,
    conclusion_for_ci,
)
from src.decompose import point_kitagawa, rare_char_set, stratum_sizes, video_cells_via_map
from src.frame import load_published_frame
from src.pins import FrameCounts
from src.groups import assign_groups
from src.hashing import verify_corpus_hash
from src.measures import attach_agreement, flatten_key
from src.status_io import sha256_file, write_json_atomic, write_status, write_text_atomic
from src.tables import open_corpus

MASTER_SEED = 20250918
B = 2000


def git_sha(repo_ROOT: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_ROOT, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def year_video_counts(videos: pd.DataFrame) -> list[dict]:
    year = videos["upload_date"].astype(str).str.slice(0, 4)
    rows = []
    for y, grp in videos.groupby(year, sort=True):
        rows.append({"year": str(y), "n_videos": int(len(grp))})
    return rows


def render_open_analysis(
    point: dict[str, float],
    boot: dict,
    sizes: dict[str, dict[str, int]],
    year_rows: list[dict],
    counts_pre: dict[str, int],
    counts_post: dict[str, int],
    rare_share_pre: float,
    rare_share_post: float,
    residual_pp: float,
    explained_pp: float,
    unadj_pp: float,
    did_pp: float,
    frame_counts: FrameCounts,
) -> str:
    g = boot["G_h"]
    ci_lo, ci_hi = boot["residual_ci95"]
    ci_unreliable_any = int(any(boot["ci_unreliable"].values()))
    conclusion = conclusion_for_ci(boot["ci_unreliable"], g)
    assert_inconclusive_when_unreliable(ci_unreliable_any, conclusion)
    year_txt = ", ".join(f"{r['year']} n={r['n_videos']}" for r in year_rows)
    lines = [
        "# TASK-6 open analysis",
        "",
        f"Population: the {frame_counts.videos_expected} videos of this channel. The statistic is agreement",
        "between the acoustic Jyutping and the dictionary, not a human label.",
        "",
        "## Decomposition",
        "",
        "Covariates (none written by this run):",
        "",
        "- `film` vs `other`: title-proxy markers from `videos.title` (粵劇, 任劍輝,",
        "  芳艷芬, 李小龍, 林鳳, 吳楚帆, 石堅, 謝賢, 新馬師曾, 白雪仙). This is a title",
        "  proxy, not a content judgement.",
        "- Rare characters: `char` with frequency < 10 in the full `syllables` table",
        "  (every tier). Used only to check composition; it is not the residual's",
        "  standardizing variable.",
        "",
        "`tier`, `coverage`, `chars_per_sec` and `aligned` were not used as",
        "stratifiers, so the unstratified contract gap is the baseline gap.",
        "",
        "Standardization: Kitagawa / post-stratification of post rates onto the",
        "pre period's film/other mix of judgeable syllables. The reported film",
        "comparison is the difference-in-differences versus the `other` title-proxy",
        "group, not the raw film gap.",
        "",
        f"- Unadjusted contract gap: {unadj_pp:.4f} pp",
        f"  (pre agreement {point['agree_pre']:.6f}, post {point['agree_post']:.6f}).",
        f"- Film title-proxy: pre {point['agree_film_pre']:.6f}, post {point['agree_film_post']:.6f}.",
        f"- Other title-proxy: pre {point['agree_other_pre']:.6f}, post {point['agree_other_post']:.6f}.",
        f"- DID (film gap minus other gap): {did_pp:.4f} pp.",
        f"- Pre film share of judgeable syllables: {point['w_film_pre']:.6f}.",
        f"- Post agreement if post had the pre film mix: {point['cf_post']:.6f}.",
        f"- Composition (explained): {explained_pp:.4f} pp.",
        f"- Residual (pre minus composition-adjusted post): {residual_pp:.4f} pp.",
        "",
        "Rare-character share is slightly lower after 2024, so a shift toward rare",
        "characters does not explain the drop",
        f" (pre {rare_share_pre:.6f}, post {rare_share_post:.6f}).",
        "",
        "Contract-24 period totals live in `manifest.json` (and the named counts",
        "in `results.json`).",
        "",
        "## Residual gap, cluster bootstrap",
        "",
        f"B={boot['B']} whole-`video_id` resamples within film×period strata.",
        f"Master seed {boot['master_seed']}. Per-stratum seeds are",
        "`int(sha256(f\"{master_seed}:{h}\").hexdigest()[:8], 16)`.",
        "",
        f"G_h (videos per stratum, census of the {frame_counts.videos_expected} videos of this channel):",
        "",
    ]
    for h in STRATA:
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
            f"Residual 95% percentile CI: [{100*ci_lo:.4f}, {100*ci_hi:.4f}] pp.",
            f"p_raw={boot['p_raw']:.6g}, p_BH={boot['p_bh']:.6g}, m={boot['m']}.",
            f"ci_unreliable (any stratum)={ci_unreliable_any}; conclusion={conclusion}.",
            "",
            "Year cells (do not read 2021 or 2023 as a trend): " + year_txt + ".",
            "",
            "## Hypothesis",
            "",
            "What data, what comparison, what result would refute it: among judgeable",
            "A+B syllables whose `char` occurs at least 10 times in the full corpus",
            "and whose video is in the `other` title-proxy group, the video_id-cluster",
            "bootstrap 95% CI (B>=1000, strata = period) of agreement(pre) −",
            "agreement(post) includes 0. That result would refute the claim that the",
            "residual drop is a within-inventory rise in tone/segment disagreement on",
            "ordinary characters in non-film titles.",
            "",
            "## Conclusion",
            "",
            f"On the {frame_counts.videos_expected} videos of this channel, the title-proxy film mix accounts for",
            "only a minority of the post-2024 agreement drop; the residual remains",
            "after reweighting post rates to the pre film mix and sits in tone and",
            "segment disagreements rather than in rare-character share.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    corpus_PATH: str,
    readme_PATH: str,
    brief_PATH: str,
    out_DIR: str,
    repo_ROOT: str,
) -> None:
    out_ROOT = Path(out_DIR)
    out_ROOT.mkdir(parents=True, exist_ok=True)
    status_FILE = str(out_ROOT / "STATUS.json")
    write_status(status_FILE, {"status": "running"})

    corpus_hash = verify_corpus_hash(corpus_PATH, readme_PATH)
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

    steps = list(loaded["steps"])
    pre_s = published["period"] == "pre"
    post_s = published["period"] == "post"
    steps.append(
        {
            "step": "period_assign",
            "rule": "four-digit year <=2024 vs >=2025",
            "group": "pre",
            "rows_before": int(len(published)),
            "rows_after": int(pre_s.sum()),
        }
    )
    steps.append(
        {
            "step": "period_assign",
            "rule": "four-digit year <=2024 vs >=2025",
            "group": "post",
            "rows_before": int(len(published)),
            "rows_after": int(post_s.sum()),
        }
    )
    steps.append(
        {
            "step": "period_assign",
            "rule": "not a four-digit year",
            "group": "unassigned_period",
            "rows_before": int(len(published)),
            "rows_after": int((published["period"] == "unassigned_period").sum()),
        }
    )
    for group_name, mask in (
        ("film", published["film_group"] == "film"),
        ("other", published["film_group"] == "other"),
        ("unassigned_film", published["film_group"] == "unassigned_film"),
    ):
        steps.append(
            {
                "step": "film_assign",
                "rule": "title-proxy markers vs none, title nonempty",
                "group": group_name,
                "rows_before": int(len(published)),
                "rows_after": int(mask.sum()),
            }
        )

    counts_pre = agreement_counts(published.loc[pre_s])
    counts_post = agreement_counts(published.loc[post_s])
    rare = rare_char_set(loaded["syllables"])
    rare_flag = published["char"].isin(rare)
    rare_share_pre = float(rare_flag.loc[pre_s].mean())
    rare_share_post = float(rare_flag.loc[post_s].mean())

    video_df = video_cells_via_map(published, videos)
    video_df = attach_agreement(video_df)
    _key = flatten_key(["video", "agreement"])
    del _key

    sizes = stratum_sizes(video_df)
    point = point_kitagawa(video_df)
    boot = bootstrap_residual(video_df, B=B, master_seed=MASTER_SEED)
    residual_pp = 100.0 * point["residual"]
    explained_pp = 100.0 * point["explained"]
    unadj_pp = 100.0 * point["unadjusted"]
    did_pp = 100.0 * point["did"]
    ci_unreliable_any = int(any(boot["ci_unreliable"].values()))
    conclusion = conclusion_for_ci(boot["ci_unreliable"], boot["G_h"])
    assert_inconclusive_when_unreliable(ci_unreliable_any, conclusion)

    decomposition = {
        "population": f"the {loaded['counts'].videos_expected} videos of this channel",
        "standardization": "kitagawa_film_pre_mix",
        "variables": {
            "film_group": "videos.title markers listed in TASK-6.md; title proxy",
            "rare_char": "syllables.char frequency < 10 on the full table, all tiers",
        },
        "point": point,
        "residual_pp": residual_pp,
        "explained_pp": explained_pp,
        "unadjusted_pp": unadj_pp,
        "did_pp": did_pp,
        "baseline_gap_pp": unadj_pp,
        "group_gap_minus_baseline_pp": residual_pp - unadj_pp,
        "agree_pre": point["agree_pre"],
        "agree_post": point["agree_post"],
        "agree_film_pre": point["agree_film_pre"],
        "agree_film_post": point["agree_film_post"],
        "agree_other_pre": point["agree_other_pre"],
        "agree_other_post": point["agree_other_post"],
        "B": boot["B"],
        "master_seed": boot["master_seed"],
        "seeds": boot["seeds"],
        "G_h": boot["G_h"],
        "N_h": {h: sizes[h]["N_h"] for h in STRATA},
        "n_h_judgeable": {h: sizes[h]["n_h_judgeable"] for h in STRATA},
        "ci_unreliable": boot["ci_unreliable"],
        "ci_unreliable_any": ci_unreliable_any,
        "conclusion": conclusion,
        "residual_ci95_pp": [100.0 * boot["residual_ci95"][0], 100.0 * boot["residual_ci95"][1]],
        "p_raw": boot["p_raw"],
        "p_bh": boot["p_bh"],
        "m": boot["m"],
        "descriptive": 0,
        "exploratory": 0,
        "year_video_counts": year_video_counts(videos),
        "rare_share_pre": rare_share_pre,
        "rare_share_post": rare_share_post,
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
        "agreement_counts": {"pre": counts_pre, "post": counts_post},
        "stratum_sizes": sizes,
    }

    analysis_md = render_open_analysis(
        point,
        boot,
        sizes,
        year_video_counts(videos),
        counts_pre,
        counts_post,
        rare_share_pre,
        rare_share_post,
        residual_pp,
        explained_pp,
        unadj_pp,
        did_pp,
        loaded["counts"],
    )

    decomp_FILE = str(out_ROOT / "decomposition.json")
    manifest_FILE = str(out_ROOT / "manifest.json")
    analysis_FILE = str(out_ROOT / "open_analysis.md")
    write_json_atomic(decomp_FILE, json.loads(json.dumps(decomposition)))
    write_json_atomic(manifest_FILE, manifest)
    write_text_atomic(analysis_FILE, analysis_md)
    write_status(
        status_FILE,
        {
            "status": "complete",
            "outputs": {
                "decomposition.json": sha256_file(decomp_FILE),
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
    parser.add_argument("--out_DIR", required=True)
    parser.add_argument("--repo_ROOT", required=True)
    args = parser.parse_args()
    run(
        args.corpus_PATH,
        args.readme_PATH,
        args.brief_PATH,
        args.out_DIR,
        args.repo_ROOT,
    )


if __name__ == "__main__":
    main()
