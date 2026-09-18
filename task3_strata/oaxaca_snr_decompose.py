#!/usr/bin/env python3
"""Kitagawa–Oaxaca two-fold SNR-bin decomposition: film − contemporary.

Reads agreement_by_snr.csv (or recomputes syllable shares from a SQLite corpus
if --db is given together with quality/multilabel). Writes oaxaca_snr.csv and
asserts that |rate + composition − Δ| < 1e-9 on the proportion scale.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1e-9
SNR_ORDER = ["<5", "5-10", "10-15", "15-20", ">20"]
SNR_BIN_EXPR = """
CASE
  WHEN q.snr_db < 5 THEN '<5'
  WHEN q.snr_db < 10 THEN '5-10'
  WHEN q.snr_db < 15 THEN '10-15'
  WHEN q.snr_db < 20 THEN '15-20'
  ELSE '>20'
END
"""


def load_from_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    need = {"subset", "bin", "n_syllables", "agree_syl"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"agreement_by_snr.csv missing columns: {sorted(missing)}")
    return df


def load_shares_from_db(
    db_path: Path,
    quality_path: Path,
    multilabel_path: Path,
) -> pd.DataFrame:
    """Optional path: recompute per-bin n_syllables + agree_syl from corpus."""
    quality = pd.read_csv(quality_path)
    if "window_id" not in quality.columns:
        raise SystemExit("quality CSV must contain window_id")
    multilabel = pd.read_csv(multilabel_path)
    film_ids = set(multilabel.loc[multilabel.get("film_flag", 0) == 1, "video_id"].astype(str))
    cont_ids = set(
        multilabel.loc[multilabel.get("contemporary_only", 0) == 1, "video_id"].astype(str)
    )

    conn = sqlite3.connect(str(db_path))
    # Minimal join: windows + quality SNR + syllable jp_match
    q = quality[["window_id", "snr_db"]].copy()
    q["window_id"] = q["window_id"].astype(str)
    q.to_sql("_tmp_quality", conn, if_exists="replace", index=False)

    sql = f"""
    SELECT
      CAST(w.video_id AS TEXT) AS video_id,
      {SNR_BIN_EXPR} AS bin,
      CASE WHEN s.jp_match IN ('exact_default', 'exact_alt') THEN 1.0 ELSE 0.0 END AS agree
    FROM syllables s
    JOIN windows w ON w.uid = s.uid
    JOIN _tmp_quality q ON q.window_id = CAST(w.uid AS TEXT)
    WHERE w.tier IN ('A', 'B')
      AND q.snr_db IS NOT NULL
    """
    try:
        raw = pd.read_sql_query(sql, conn)
    finally:
        conn.execute("DROP TABLE IF EXISTS _tmp_quality")
        conn.close()

    rows = []
    for subset, ids in (("film", film_ids), ("contemporary", cont_ids)):
        sub = raw[raw["video_id"].isin(ids)]
        for b, g in sub.groupby("bin"):
            rows.append(
                {
                    "subset": subset,
                    "bin": b,
                    "n_syllables": int(len(g)),
                    "agree_syl": float(g["agree"].mean()) if len(g) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def pivot_bins(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    film = df[df["subset"] == "film"].set_index("bin")
    cont = df[df["subset"] == "contemporary"].set_index("bin")
    for name, part in (("film", film), ("contemporary", cont)):
        missing = [b for b in SNR_ORDER if b not in part.index]
        if missing:
            raise SystemExit(f"{name} missing SNR bins: {missing}")
    film = film.loc[SNR_ORDER]
    cont = cont.loc[SNR_ORDER]
    return film, cont


def decompose(film: pd.DataFrame, cont: pd.DataFrame) -> pd.DataFrame:
    nf = film["n_syllables"].to_numpy(dtype=float)
    nc = cont["n_syllables"].to_numpy(dtype=float)
    rf = film["agree_syl"].to_numpy(dtype=float)
    rc = cont["agree_syl"].to_numpy(dtype=float)

    wf = nf / nf.sum()
    wc = nc / nc.sum()
    Rf = float(np.dot(wf, rf))
    Rc = float(np.dot(wc, rc))
    delta = Rf - Rc

    # Two-fold: film weights as rate-effect reference
    #   rate = Σ wf (rf − rc);  composition = Σ rc (wf − wc)
    rate_film_w = float(np.dot(wf, rf - rc))
    comp_film_w = float(np.dot(rc, wf - wc))
    sum_film_w = rate_film_w + comp_film_w

    # Two-fold: contemporary weights as rate-effect reference
    #   rate = Σ wc (rf − rc);  composition = Σ rf (wf − wc)
    rate_cont_w = float(np.dot(wc, rf - rc))
    comp_cont_w = float(np.dot(rf, wf - wc))
    sum_cont_w = rate_cont_w + comp_cont_w

    for label, s in (("film_w", sum_film_w), ("cont_w", sum_cont_w)):
        err = abs(s - delta)
        if err >= EPS:
            raise AssertionError(
                f"Oaxaca identity failed ({label}): |{s} − {delta}| = {err} >= {EPS}"
            )

    rows = [
        {
            "scheme": "film_weights_rate_ref",
            "description": "rate=Σ wf(rf−rc); composition=Σ rc(wf−wc); primary",
            "Rf": Rf,
            "Rc": Rc,
            "delta": delta,
            "rate_effect": rate_film_w,
            "composition_effect": comp_film_w,
            "rate_plus_composition": sum_film_w,
            "delta_pp": delta * 100,
            "rate_effect_pp": rate_film_w * 100,
            "composition_effect_pp": comp_film_w * 100,
            "is_primary": True,
        },
        {
            "scheme": "contemporary_weights_rate_ref",
            "description": "rate=Σ wc(rf−rc); composition=Σ rf(wf−wc); contrast",
            "Rf": Rf,
            "Rc": Rc,
            "delta": delta,
            "rate_effect": rate_cont_w,
            "composition_effect": comp_cont_w,
            "rate_plus_composition": sum_cont_w,
            "delta_pp": delta * 100,
            "rate_effect_pp": rate_cont_w * 100,
            "composition_effect_pp": comp_cont_w * 100,
            "is_primary": False,
        },
    ]

    # Per-bin detail for primary scheme (film weights)
    detail_rows = []
    for i, b in enumerate(SNR_ORDER):
        detail_rows.append(
            {
                "scheme": "film_weights_rate_ref_by_bin",
                "bin": b,
                "wf": wf[i],
                "wc": wc[i],
                "rf": rf[i],
                "rc": rc[i],
                "rate_contrib": wf[i] * (rf[i] - rc[i]),
                "comp_contrib": rc[i] * (wf[i] - wc[i]),
            }
        )

    out = pd.DataFrame(rows)
    detail = pd.DataFrame(detail_rows)
    return out, detail, delta, Rf, Rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).resolve().parent / "agreement_by_snr.csv",
        help="Path to agreement_by_snr.csv",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "oaxaca_snr.csv",
        help="Output CSV path",
    )
    ap.add_argument("--db", type=Path, default=None, help="Optional corpus SQLite")
    ap.add_argument("--quality", type=Path, default=None, help="Optional window_quality.csv")
    ap.add_argument(
        "--multilabel",
        type=Path,
        default=None,
        help="Optional video_multilabel_flags.csv",
    )
    args = ap.parse_args()

    if args.db is not None:
        if args.quality is None or args.multilabel is None:
            raise SystemExit("--db requires --quality and --multilabel")
        df = load_shares_from_db(args.db, args.quality, args.multilabel)
    else:
        df = load_from_csv(args.csv)

    film, cont = pivot_bins(df)
    summary, detail, delta, Rf, Rc = decompose(film, cont)

    # Write summary + empty separator style: summary first, then by-bin
    # Keep a single flat CSV: summary schemes only (clean for README);
    # also write by-bin as extra rows with NaN on unused cols for audit.
    summary_out = summary.copy()
    # Attach identity check column
    summary_out["abs_sum_minus_delta"] = (
        summary_out["rate_plus_composition"] - summary_out["delta"]
    ).abs()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.to_csv(args.out, index=False)

    detail_path = args.out.with_name(args.out.stem + "_by_bin.csv")
    detail.to_csv(detail_path, index=False)

    print("=== Kitagawa–Oaxaca SNR (film − contemporary) ===")
    print(f"Rf={Rf:.6f}  Rc={Rc:.6f}  Δ={delta:.6f} ({delta*100:.4f} pp)")
    print()
    for _, r in summary_out.iterrows():
        tag = "PRIMARY" if r["is_primary"] else "contrast"
        print(f"[{tag}] {r['scheme']}")
        print(f"  {r['description']}")
        print(
            f"  rate={r['rate_effect']:.6f} ({r['rate_effect_pp']:.4f} pp)  "
            f"composition={r['composition_effect']:.6f} ({r['composition_effect_pp']:.4f} pp)  "
            f"sum={r['rate_plus_composition']:.6f}"
        )
        print(f"  |sum−Δ|={r['abs_sum_minus_delta']:.2e}  (assert < {EPS})")
        print()
    print(f"wrote {args.out}")
    print(f"wrote {detail_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
