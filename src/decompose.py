"""Film-mix Kitagawa decomposition of the pre/post agreement gap."""

from __future__ import annotations

import pandas as pd

from src.bootstrap import STRATA, kitagawa_from_stratum_sums, video_stratum


def rare_char_set(syllables: pd.DataFrame) -> set[str]:
    counts = syllables.groupby("char").size()
    return set(counts[counts < 10].index.tolist())


def video_cells_via_map(published: pd.DataFrame, videos: pd.DataFrame) -> pd.DataFrame:
    """Aggregate judgeable counts to video_id without a DataFrame join."""
    realized = published["jp_realized"].fillna("").astype(str)
    judgeable = published["jp_realized"].notna() & (realized != "") & (published["dur"] > 0)
    match = judgeable & published["jp_match"].isin(("exact_default", "exact_alt"))
    n_j = published.loc[judgeable].groupby("video_id").size().to_dict()
    n_m = published.loc[match].groupby("video_id").size().to_dict()
    assigned = videos["period"].isin(("pre", "post")) & videos["film_group"].isin(
        ("film", "other")
    )
    base = videos.loc[assigned, ["video_id", "period", "film_group"]].copy()
    video_ids = base["video_id"].tolist()
    base["n_judgeable"] = [int(n_j[v]) if v in n_j else 0 for v in video_ids]
    base["n_match"] = [int(n_m[v]) if v in n_m else 0 for v in video_ids]
    base["stratum"] = [
        video_stratum(fg, p) for fg, p in zip(base["film_group"], base["period"])
    ]
    return base.reset_index(drop=True)


def point_kitagawa(videos: pd.DataFrame) -> dict[str, float]:
    sums: dict[str, tuple[float, float]] = {}
    for h in STRATA:
        block = videos.loc[videos["stratum"] == h]
        sums[h] = (
            float(block["n_judgeable"].sum()),
            float(block["n_match"].sum()),
        )
    return kitagawa_from_stratum_sums(sums)


def stratum_sizes(videos: pd.DataFrame) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for h in STRATA:
        block = videos.loc[videos["stratum"] == h]
        out[h] = {
            "N_h": int(len(block)),
            "G_h": int(len(block)),
            "n_h_judgeable": int(block["n_judgeable"].sum()),
            "n_h_match": int(block["n_match"].sum()),
            "n_h_videos_with_judgeable": int((block["n_judgeable"] > 0).sum()),
        }
    return out
