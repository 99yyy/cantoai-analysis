"""Explicit pre/post and film/other predicates; neither group is the other's complement."""

from __future__ import annotations

import pandas as pd

FILM_MARKERS = (
    "粵劇",
    "任劍輝",
    "芳艷芬",
    "李小龍",
    "林鳳",
    "吳楚帆",
    "石堅",
    "謝賢",
    "新馬師曾",
    "白雪仙",
)


def _year4(upload_date: pd.Series) -> pd.Series:
    return upload_date.astype(str).str.slice(0, 4)


def period_masks(upload_date: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    year = _year4(upload_date)
    four = year.str.fullmatch(r"[0-9]{4}").fillna(False)
    pre = four & (year <= "2024")
    post = four & (year >= "2025")
    assert_no_period_overlap(pre, post)
    unassigned = ~(pre | post)
    return pre, post, unassigned


def assert_no_period_overlap(pre: pd.Series, post: pd.Series) -> None:
    if bool((pre & post).any()):
        raise ValueError("period overlap: a row matched both pre and post")


def _title_nonempty(title: pd.Series) -> pd.Series:
    as_str = title.fillna("").astype(str)
    return title.notna() & (as_str != "")


def film_masks(title: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    nonempty = _title_nonempty(title)
    as_str = title.fillna("").astype(str)
    has_marker = pd.Series(False, index=title.index)
    lacks_marker = pd.Series(True, index=title.index)
    for marker in FILM_MARKERS:
        present = as_str.str.contains(marker, regex=False)
        has_marker = has_marker | present
        lacks_marker = lacks_marker & ~present
    film = nonempty & has_marker
    other = nonempty & lacks_marker
    assert_no_film_overlap(film, other)
    unassigned = ~nonempty
    return film, other, unassigned


def assert_no_film_overlap(film: pd.Series, other: pd.Series) -> None:
    if bool((film & other).any()):
        raise ValueError("film overlap: a row matched both film and other")


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    pre, post, unassigned_period = period_masks(out["upload_date"])
    film, other, unassigned_film = film_masks(out["title"])
    period = pd.Series("unassigned_period", index=out.index)
    period.loc[pre] = "pre"
    period.loc[post] = "post"
    film_g = pd.Series("unassigned_film", index=out.index)
    film_g.loc[film] = "film"
    film_g.loc[other] = "other"
    out["period"] = period
    out["film_group"] = film_g
    out.attrs["n_unassigned_period"] = int(unassigned_period.sum())
    out.attrs["n_unassigned_film"] = int(unassigned_film.sum())
    out.attrs["n_period_pre"] = int(pre.sum())
    out.attrs["n_period_post"] = int(post.sum())
    out.attrs["n_film"] = int(film.sum())
    out.attrs["n_other"] = int(other.sum())
    return out
