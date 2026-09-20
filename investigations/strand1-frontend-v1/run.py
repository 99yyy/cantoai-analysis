#!/usr/bin/env python3
"""
Context-aware Chinese→Jyutping v1 (trigram/unigram rules over ToJyutping jp_ctx).

Opponent: ToJyutping via corpus jp_ctx (optionally spot-checked with pip ToJyutping).
Label evidence: ONLY acoustic model jp_realized.
Strongest allowed claim: on these rows I beat ToJyutping at predicting realized reading.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "corpus_v2.sqlite"
README_PATH = REPO_ROOT / "README.md"
EXPECTED_SHA256 = "2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f"
OUT_DIR = Path(__file__).resolve().parent
_README_SHA = re.compile(r"sha256:\s*`?([0-9a-f]{64})`?")

# Hyperparams
TRAIN_PCT = 70  # video_id hash % 100 < TRAIN_PCT → train
TRIGRAM_MIN_SUPPORT = 3
UNIGRAM_MIN_SUPPORT = 8
UNIGRAM_MIN_ALT_FRAC = 0.55  # among cases where realized≠default for this char on train
# Only learn rules that predict a change from default (the interesting case),
# or that reinforce keeping default when ctx already changed? We start from jp_ctx
# and only override when a learned rule fires → predicted reading.

JUDGE_SQL = """
SELECT
  s.syl_id, s.video_id, s.uid, s.pos, s.char,
  s.prev_char, s.next_char,
  s.jp_default, s.jp_ctx, s.jp_realized, s.dur, s.tier, s.n_cand,
  w.text_clean
FROM syllables s
JOIN windows w ON s.uid = w.uid
WHERE s.tier IN ('A','B')
  AND s.jp_realized IS NOT NULL AND s.dur > 0
  AND s.jp_ctx IS NOT NULL AND s.jp_default IS NOT NULL
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def readme_sha256(readme_PATH: Path) -> str:
    text = readme_PATH.read_text(encoding="utf-8")
    match = _README_SHA.search(text)
    if match is None:
        print("README.md records no sha256 for the corpus")
        raise SystemExit(1)
    return match.group(1)


def pin_corpus_or_exit(corpus_PATH: Path, readme_PATH: Path) -> str:
    """Compare the sqlite file to README.md and the v1 pin; print both on mismatch."""
    got = sha256_file(corpus_PATH)
    want_readme = readme_sha256(readme_PATH)
    if got != EXPECTED_SHA256 or got != want_readme:
        print(got)
        print(EXPECTED_SHA256)
        print(want_readme)
        raise SystemExit(1)
    return got


def video_split(video_id: str) -> str:
    h = int(hashlib.md5(video_id.encode("utf-8")).hexdigest(), 16) % 100
    return "train" if h < TRAIN_PCT else "eval"


def strip_tone(jp: str | None) -> str | None:
    if jp is None:
        return None
    return re.sub(r"[1-6]$", "", jp)


def load_rows(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(JUDGE_SQL)]
    return rows


def assign_splits(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Split by video_id; then ensure no text_clean appears in both.
    Strategy: any text_clean that appears in both → move ALL copies to train
    (drop from eval). Report counts.
    """
    for r in rows:
        r["split"] = video_split(r["video_id"])

    train_texts = {r["text_clean"] for r in rows if r["split"] == "train" and r["text_clean"]}
    eval_texts = {r["text_clean"] for r in rows if r["split"] == "eval" and r["text_clean"]}
    overlap = train_texts & eval_texts

    # Move overlapping text_clean rows from eval → train
    moved = 0
    for r in rows:
        if r["split"] == "eval" and r["text_clean"] in overlap:
            r["split"] = "train"
            moved += 1

    train = [r for r in rows if r["split"] == "train"]
    eval_ = [r for r in rows if r["split"] == "eval"]

    # Verify no text_clean overlap
    t_set = {r["text_clean"] for r in train if r["text_clean"]}
    e_set = {r["text_clean"] for r in eval_ if r["text_clean"]}
    assert not (t_set & e_set), "text_clean leak remains"

    stats = {
        "n_judgeable": len(rows),
        "n_videos_total": len({r["video_id"] for r in rows}),
        "n_videos_train_hash": len({r["video_id"] for r in rows if video_split(r["video_id"]) == "train"}),
        "n_videos_eval_hash": len({r["video_id"] for r in rows if video_split(r["video_id"]) == "eval"}),
        "n_overlap_text_clean": len(overlap),
        "n_rows_moved_eval_to_train": moved,
        "n_train": len(train),
        "n_eval": len(eval_),
        "n_videos_train_final": len({r["video_id"] for r in train}),
        "n_videos_eval_final": len({r["video_id"] for r in eval_}),
        "n_text_clean_train": len(t_set),
        "n_text_clean_eval": len(e_set),
    }
    return train, eval_, stats


def learn_rules(train: list[dict]) -> dict:
    """
    Lift-gated contextual overrides over ToJyutping jp_ctx.

    For each pattern (trigram left-char-right; bigrams left-char / char-right):
      majority jp_realized must have frac≥0.5, support≥k, beat jp_ctx accuracy
      on the same train rows, and differ from the majority jp_ctx (else no-op).

    No bare unigram alts — too many false changes given ~18% base rate.
    """
    patterns = {
        "tri": defaultdict(lambda: {"real": Counter(), "ctx_ok": 0, "ctx": Counter(), "n": 0}),
        "bi_l": defaultdict(lambda: {"real": Counter(), "ctx_ok": 0, "ctx": Counter(), "n": 0}),
        "bi_r": defaultdict(lambda: {"real": Counter(), "ctx_ok": 0, "ctx": Counter(), "n": 0}),
    }

    def bump(bucket, key, r):
        b = bucket[key]
        b["real"][r["jp_realized"]] += 1
        b["ctx"][r["jp_ctx"]] += 1
        b["n"] += 1
        if r["jp_ctx"] == r["jp_realized"]:
            b["ctx_ok"] += 1

    for r in train:
        left = r["prev_char"] or ""
        right = r["next_char"] or ""
        ch = r["char"]
        bump(patterns["tri"], (left, ch, right), r)
        bump(patterns["bi_l"], (left, ch), r)
        bump(patterns["bi_r"], (ch, right), r)

    def select(bucket, min_support):
        out = {}
        for key, b in bucket.items():
            if b["n"] < min_support:
                continue
            pred, pred_n = b["real"].most_common(1)[0]
            if pred_n / b["n"] < 0.5:
                continue
            if pred_n <= b["ctx_ok"]:
                continue
            ctx_maj, _ = b["ctx"].most_common(1)[0]
            if pred == ctx_maj:
                continue
            out[key] = {
                "pred": pred,
                "support": b["n"],
                "pred_n": pred_n,
                "frac": round(pred_n / b["n"], 4),
                "ctx_correct": b["ctx_ok"],
                "lift": pred_n - b["ctx_ok"],
            }
        return out

    trigrams = select(patterns["tri"], TRIGRAM_MIN_SUPPORT)
    # Bigrams need higher support (less specific)
    bigrams_l = select(patterns["bi_l"], max(TRIGRAM_MIN_SUPPORT * 2, 6))
    bigrams_r = select(patterns["bi_r"], max(TRIGRAM_MIN_SUPPORT * 2, 6))

    return {
        "trigrams": trigrams,
        "bigrams_l": bigrams_l,
        "bigrams_r": bigrams_r,
        "unigrams": {},  # disabled in v1 refined
    }


def predict_row(r: dict, rules: dict) -> str:
    """Start from jp_ctx; override with most-specific lift-gated rule that differs."""
    left = r["prev_char"] or ""
    right = r["next_char"] or ""
    ch = r["char"]
    for key, table in (
        ((left, ch, right), rules["trigrams"]),
        ((left, ch), rules["bigrams_l"]),
        ((ch, right), rules["bigrams_r"]),
    ):
        hit = table.get(key)
        if hit is not None and hit["pred"] != r["jp_ctx"]:
            return hit["pred"]
    return r["jp_ctx"]


def outcome_label(pred: str, ctx: str, realized: str) -> str:
    """Among rows where we care about win/lose when pred≠ctx."""
    if pred == ctx:
        if pred == realized:
            return "same_both_right"
        return "same_both_wrong"
    # pred ≠ ctx
    pred_ok = pred == realized
    ctx_ok = ctx == realized
    if pred_ok and not ctx_ok:
        return "true_win"
    if ctx_ok and not pred_ok:
        return "true_lose"
    if pred_ok and ctx_ok:
        return "tie_both_right"  # shouldn't happen if pred≠ctx and both==realized
    return "tie_both_wrong"


def metrics_bundle(eval_rows: list[dict], preds: list[str]) -> dict:
    assert len(eval_rows) == len(preds)
    n = len(eval_rows)

    def em(subset_idx):
        if not subset_idx:
            return {"n": 0, "pred": None, "ctx": None, "delta": None}
        correct_pred = sum(1 for i in subset_idx if preds[i] == eval_rows[i]["jp_realized"])
        correct_ctx = sum(1 for i in subset_idx if eval_rows[i]["jp_ctx"] == eval_rows[i]["jp_realized"])
        return {
            "n": len(subset_idx),
            "pred_exact": round(correct_pred / len(subset_idx), 6),
            "ctx_exact": round(correct_ctx / len(subset_idx), 6),
            "delta_pred_minus_ctx": round((correct_pred - correct_ctx) / len(subset_idx), 6),
        }

    all_idx = list(range(n))
    ctx_def_idx = [i for i in all_idx if eval_rows[i]["jp_ctx"] == eval_rows[i]["jp_default"]]
    ctx_ne_idx = [i for i in all_idx if eval_rows[i]["jp_ctx"] != eval_rows[i]["jp_default"]]
    should_change_idx = [i for i in all_idx if eval_rows[i]["jp_realized"] != eval_rows[i]["jp_default"]]
    should_not_idx = [i for i in all_idx if eval_rows[i]["jp_realized"] == eval_rows[i]["jp_default"]]

    # A: exact-match stratified
    A = {
        "all_judgeable_eval": em(all_idx),
        "among_ctx_eq_default": em(ctx_def_idx),
        "among_ctx_ne_default": em(ctx_ne_idx),
        "among_should_change": em(should_change_idx),
        "among_should_not": em(should_not_idx),
    }

    # B: binary "change from default?" among ctx=default
    # pred_change = pred≠default; realized_change = realized≠default
    tp = fp = fn = tn = 0
    for i in ctx_def_idx:
        r = eval_rows[i]
        pred_change = preds[i] != r["jp_default"]
        real_change = r["jp_realized"] != r["jp_default"]
        if pred_change and real_change:
            tp += 1
        elif pred_change and not real_change:
            fp += 1
        elif not pred_change and real_change:
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    base_rate = (tp + fn) / len(ctx_def_idx) if ctx_def_idx else 0.0
    # always-predict-change baseline: precision=base_rate, recall=1, F1=2p/(1+p)
    always_p = base_rate
    always_r = 1.0
    always_f1 = 2 * always_p * always_r / (always_p + always_r) if (always_p + always_r) else 0.0
    # always-predict-no-change: precision undef/0, recall=0, F1=0
    B = {
        "n_ctx_eq_default": len(ctx_def_idx),
        "base_rate_realized_ne_default": round(base_rate, 6),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(prec, 6),
        "recall": round(rec, 6),
        "f1": round(f1, 6),
        "always_predict_change_baseline": {
            "precision": round(always_p, 6),
            "recall": always_r,
            "f1": round(always_f1, 6),
        },
    }

    # C: wins among pred≠ctx
    outcomes = Counter()
    tone_only_wins = 0
    segment_wins = 0
    for i in all_idx:
        r = eval_rows[i]
        oc = outcome_label(preds[i], r["jp_ctx"], r["jp_realized"])
        outcomes[oc] += 1
        if oc == "true_win":
            if strip_tone(preds[i]) == strip_tone(r["jp_ctx"]):
                tone_only_wins += 1
            else:
                segment_wins += 1

    n_diff = sum(outcomes[k] for k in ("true_win", "true_lose", "tie_both_wrong", "tie_both_right"))
    C = {
        "n_pred_ne_ctx": n_diff,
        "true_win": outcomes["true_win"],
        "true_lose": outcomes["true_lose"],
        "tie_both_wrong": outcomes["tie_both_wrong"],
        "tie_both_right": outcomes["tie_both_right"],
        "same_both_right": outcomes["same_both_right"],
        "same_both_wrong": outcomes["same_both_wrong"],
        "true_win_rate_among_diff": round(outcomes["true_win"] / n_diff, 6) if n_diff else None,
        "true_lose_rate_among_diff": round(outcomes["true_lose"] / n_diff, 6) if n_diff else None,
    }

    # D: tone vs segment among true wins
    D = {
        "true_win_tone_only": tone_only_wins,
        "true_win_segment_diff": segment_wins,
    }

    return {"A_exact_match": A, "B_change_decision": B, "C_win_lose_tie": C, "D_tone_vs_segment": D}


def spot_check_tojyutping(eval_rows: list[dict], n: int = 20) -> dict:
    try:
        import ToJyutping  # type: ignore
    except ImportError:
        return {"ok": False, "note": "ToJyutping not importable in this interpreter"}

    # Spot-check: for a few uids, reconstruct jp from text_clean / chars and compare to jp_ctx
    checked = 0
    agree = 0
    disagree_examples = []
    # Group by uid
    by_uid: dict[str, list] = defaultdict(list)
    for r in eval_rows:
        by_uid[r["uid"]].append(r)
    for uid, group in by_uid.items():
        if checked >= n:
            break
        group = sorted(group, key=lambda x: x["pos"])
        text = "".join(g["char"] for g in group)
        try:
            lst = ToJyutping.get_jyutping_list(text)
        except Exception as e:
            return {"ok": False, "note": f"ToJyutping call failed: {e}"}
        # get_jyutping_list returns list of (char, jp) possibly with multi-char?
        # Flatten: typically one per char
        if len(lst) != len(group):
            # try per-char
            for g in group:
                if checked >= n:
                    break
                try:
                    jp = ToJyutping.get_jyutping_list(g["char"])
                    pkg = jp[0][1] if jp else None
                except Exception:
                    pkg = None
                checked += 1
                if pkg == g["jp_ctx"]:
                    agree += 1
                else:
                    disagree_examples.append(
                        {"char": g["char"], "jp_ctx": g["jp_ctx"], "pkg": pkg}
                    )
            continue
        for g, (ch, jp) in zip(group, lst):
            if checked >= n:
                break
            checked += 1
            # jp may be None for non-han
            if jp == g["jp_ctx"]:
                agree += 1
            else:
                disagree_examples.append(
                    {"char": g["char"], "jp_ctx": g["jp_ctx"], "pkg": jp, "uid": uid}
                )
    return {
        "ok": True,
        "checked": checked,
        "agree": agree,
        "disagree": checked - agree,
        "examples_disagree": disagree_examples[:5],
        "note": "jp_ctx treated as ToJyutping; package spot-check for sanity",
    }


def write_predictions_csv(path: Path, eval_rows: list[dict], preds: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "video_id",
                "char",
                "jp_default",
                "jp_ctx",
                "jp_realized",
                "pred",
                "outcome",
            ]
        )
        for r, p in zip(eval_rows, preds):
            oc = outcome_label(p, r["jp_ctx"], r["jp_realized"])
            w.writerow(
                [
                    r["video_id"],
                    r["char"],
                    r["jp_default"],
                    r["jp_ctx"],
                    r["jp_realized"],
                    p,
                    oc,
                ]
            )


def write_comparison_md(path: Path, metrics: dict, split_stats: dict, rules: dict) -> None:
    C = metrics["C_win_lose_tie"]
    A = metrics["A_exact_match"]
    B = metrics["B_change_decision"]
    D = metrics["D_tone_vs_segment"]
    lines = []
    lines.append("# Win / Lose / Tie vs ToJyutping (jp_ctx)")
    lines.append("")
    lines.append("Label evidence is **only** the acoustic model (`jp_realized`).")
    lines.append(
        'Strongest claim: **"on these rows I beat ToJyutping at predicting realized reading"** — not "my reading is correct".'
    )
    lines.append("")
    lines.append("## Split")
    lines.append("")
    lines.append("| item | count |")
    lines.append("|---|---|")
    for k, v in split_stats.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append(
        f"Rules: {len(rules['trigrams'])} trigrams (support≥{TRIGRAM_MIN_SUPPORT}), "
        f"{len(rules.get('bigrams_l', {}))} left-bigrams, {len(rules.get('bigrams_r', {}))} right-bigrams "
        f"(lift-gated over jp_ctx; unigrams disabled)."
    )
    lines.append("")
    lines.append("## C. Among rows where pred ≠ jp_ctx")
    lines.append("")
    lines.append("| outcome | n | meaning |")
    lines.append("|---|---|---|")
    lines.append(f"| **true_win** | {C['true_win']} | pred==realized and jp_ctx!=realized |")
    lines.append(f"| **true_lose** | {C['true_lose']} | jp_ctx==realized and pred!=realized |")
    lines.append(f"| tie_both_wrong | {C['tie_both_wrong']} | pred≠realized and ctx≠realized |")
    lines.append(f"| tie_both_right | {C['tie_both_right']} | (rare if pred≠ctx) |")
    lines.append(f"| **n_pred_ne_ctx** | {C['n_pred_ne_ctx']} | total overrides |")
    lines.append("")
    lines.append("### Also: rows left unchanged (pred == jp_ctx)")
    lines.append("")
    lines.append("| outcome | n |")
    lines.append("|---|---|")
    lines.append(f"| same_both_right | {C['same_both_right']} |")
    lines.append(f"| same_both_wrong | {C['same_both_wrong']} |")
    lines.append("")
    lines.append("## A. Exact-match vs jp_realized")
    lines.append("")
    lines.append("| stratum | n | pred EM | ToJyutping (ctx) EM | Δ |")
    lines.append("|---|---|---|---|---|")
    for name, key in [
        ("all judgeable eval", "all_judgeable_eval"),
        ("ctx = default", "among_ctx_eq_default"),
        ("ctx ≠ default", "among_ctx_ne_default"),
        ("should change (realized≠default)", "among_should_change"),
        ("should not (realized=default)", "among_should_not"),
    ]:
        s = A[key]
        lines.append(
            f"| {name} | {s['n']} | {s['pred_exact']} | {s['ctx_exact']} | {s['delta_pred_minus_ctx']} |"
        )
    lines.append("")
    lines.append("## B. Binary “change from default?” (among ctx=default)")
    lines.append("")
    lines.append(f"- Base rate (realized≠default | ctx=default): **{B['base_rate_realized_ne_default']}**")
    lines.append(f"- Precision / Recall / F1: **{B['precision']}** / **{B['recall']}** / **{B['f1']}**")
    lines.append(
        f"- Always-predict-change baseline F1: **{B['always_predict_change_baseline']['f1']}** "
        f"(P={B['always_predict_change_baseline']['precision']}, R=1)"
    )
    lines.append(f"- Confusion: TP={B['tp']} FP={B['fp']} FN={B['fn']} TN={B['tn']}")
    lines.append("")
    lines.append("## D. Tone-only vs segment among true wins")
    lines.append("")
    lines.append(f"- Tone-only wins: {D['true_win_tone_only']}")
    lines.append(f"- Segment-different wins: {D['true_win_segment_diff']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(
    path: Path,
    metrics: dict,
    split_stats: dict,
    rules: dict,
    spot: dict,
    recommendation: str,
    reason: str,
) -> None:
    B = metrics["B_change_decision"]
    C = metrics["C_win_lose_tie"]
    A = metrics["A_exact_match"]
    lines = []
    lines.append("# frontend-strand1 v1 — context-aware Jyutping vs ToJyutping")
    lines.append("")
    lines.append("## Hard limit (do not soften)")
    lines.append("")
    lines.append(
        "on these rows I beat ToJyutping at predicting realized reading"
        " — NOT “my reading is correct”. Label evidence is ONLY the acoustic model (`jp_realized`)."
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        "1. Judgeable rows: `tier IN ('A','B') AND jp_realized IS NOT NULL AND dur>0 "
        "AND jp_ctx IS NOT NULL AND jp_default IS NOT NULL`."
    )
    lines.append(
        f"2. Split videos ~{TRAIN_PCT}/{100-TRAIN_PCT} train/eval by `md5(video_id) % 100`; "
        "any `text_clean` appearing in both → all copies moved to train."
    )
    lines.append(
        f"3. On train, learn lift-gated `(left,char,right)` / bigram → majority `jp_realized` "
        f"(support≥{TRIGRAM_MIN_SUPPORT}, majority must beat keeping `jp_ctx` on that pattern)."
    )
    lines.append(
        "4. Inference: start from `jp_ctx` (ToJyutping); if a trigram rule fires, use it; "
        "else if ctx==default and a unigram alt rule fires, use it; else keep `jp_ctx`."
    )
    lines.append(
        "5. Opponent is ToJyutping (`jp_ctx`), not “always default”."
    )
    lines.append("")
    lines.append("## Corpus")
    lines.append("")
    lines.append(f"- Path: `{CORPUS_PATH}`")
    lines.append(f"- sha256: `{EXPECTED_SHA256}` (verified)")
    lines.append("- SQLite DB was **not** modified.")
    lines.append("")
    lines.append("## ToJyutping package")
    lines.append("")
    if spot.get("ok"):
        lines.append(
            f"Spot-check (optional ToJyutping package): {spot['agree']}/{spot['checked']} "
            f"agree with `jp_ctx` (disagree={spot['disagree']}). Eval still uses `jp_ctx` from DB."
        )
    else:
        lines.append(
            f"Package spot-check note: {spot.get('note', 'n/a')}. Eval uses `jp_ctx` from DB."
        )
    lines.append("")
    lines.append("## Headline numbers (eval)")
    lines.append("")
    lines.append(
        f"- Base rate among ctx=default judgeable eval: "
        f"**{B['base_rate_realized_ne_default']:.1%}** realized≠default"
    )
    lines.append(
        f"- Change-decision F1 (among ctx=default): **{B['f1']:.4f}** "
        f"(P={B['precision']:.4f}, R={B['recall']:.4f}); "
        f"always-change baseline F1={B['always_predict_change_baseline']['f1']:.4f}"
    )
    all_em = A["all_judgeable_eval"]
    lines.append(
        f"- Exact-match all eval: pred **{all_em['pred_exact']:.4f}** vs ctx **{all_em['ctx_exact']:.4f}** "
        f"(Δ={all_em['delta_pred_minus_ctx']:+.4f})"
    )
    lines.append(
        f"- Overrides pred≠ctx: true_win={C['true_win']}, true_lose={C['true_lose']}, "
        f"tie_both_wrong={C['tie_both_wrong']} (n_diff={C['n_pred_ne_ctx']})"
    )
    lines.append(
        f"- Rules learned: {len(rules['trigrams'])} trigrams, "
        f"{len(rules.get('bigrams_l', {}))}+{len(rules.get('bigrams_r', {}))} bigrams; "
        f"train={split_stats['n_train']}, eval={split_stats['n_eval']}"
    )
    lines.append("")
    lines.append("## Continue or not?")
    lines.append("")
    lines.append(f"**{recommendation}** — {reason}")
    lines.append("")
    lines.append("## Repro")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 investigations/strand1-frontend-v1/run.py --check")
    lines.append("```")
    lines.append("")
    lines.append("Optional: `pip install -r investigations/strand1-frontend-v1/requirements.txt` for the ToJyutping spot-check. Eval still uses `jp_ctx` from the DB.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def decide(metrics: dict) -> tuple[str, str]:
    """Few-metric go/no-go. Accuracy alone is misleading under ~18% base rate."""
    B = metrics["B_change_decision"]
    C = metrics["C_win_lose_tie"]
    A = metrics["A_exact_match"]
    f1 = B["f1"]
    base_f1 = B["always_predict_change_baseline"]["f1"]
    delta = A["all_judgeable_eval"]["delta_pred_minus_ctx"]
    wins, loses = C["true_win"], C["true_lose"]
    n_diff = C["n_pred_ne_ctx"]
    # Primary: do overrides beat ToJyutping, and does overall EM vs realized improve?
    # Secondary: change-F1 vs always-change (always-change destroys EM; F1 alone is not decisive).
    if wins > loses and delta > 0.01 and n_diff >= 200 and wins >= loses * 1.5:
        return (
            "CONTINUE (weakly)",
            f"Overrides win {wins}>{loses}, EM Δ={delta:+.4f}; change-F1 {f1:.3f} "
            f"(always-change F1={base_f1:.3f} is not the product goal).",
        )
    if wins > loses and delta > 0 and n_diff >= 100:
        return (
            "DO NOT CONTINUE",
            f"Directionally positive (win {wins}>lose {loses}, EM Δ={delta:+.4f}) but "
            f"effect size too small on this corpus to justify a product line.",
        )
    return (
        "DO NOT CONTINUE",
        f"F1={f1:.3f}, win/lose={wins}/{loses}, EM Δ={delta:+.4f} — not worth continuing.",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Reproduce strand-1 frontend v1 metrics against data/corpus_v2.sqlite (read-only)."
    )
    ap.add_argument("--corpus-path", dest="corpus_PATH")
    ap.add_argument("--readme-path", dest="readme_PATH")
    ap.add_argument("--out-dir", dest="out_DIR")
    ap.add_argument(
        "--write-predictions",
        action="store_true",
        help="Write predictions_eval.csv (omit from git if the file is large; regenerate with this flag).",
    )
    ap.add_argument(
        "--write-generated-readme",
        action="store_true",
        help="Overwrite README.md with the generated sandbox README. Default is off so the human README stays.",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Compare computed numbers to the committed metrics.json (ignores tojyutping_spot_check).",
    )
    return ap.parse_args(argv)


def metrics_core(payload: dict) -> dict:
    """Headline numbers used to confirm a rerun; spot-check is optional ToJyutping."""
    return {
        "corpus_sha256": payload["corpus_sha256"],
        "base_rate_ctx_default_all_judgeable": payload["base_rate_ctx_default_all_judgeable"],
        "base_rate_ctx_default_n": payload["base_rate_ctx_default_n"],
        "base_rate_should_change_n": payload["base_rate_should_change_n"],
        "split": payload["split"],
        "rules": payload["rules"],
        "metrics": payload["metrics"],
        "recommendation": payload["recommendation"],
        "recommendation_reason": payload["recommendation_reason"],
        "claim_limit": payload["claim_limit"],
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    corpus_PATH = Path(args.corpus_PATH) if args.corpus_PATH else CORPUS_PATH
    readme_PATH = Path(args.readme_PATH) if args.readme_PATH else README_PATH
    out_DIR = Path(args.out_DIR) if args.out_DIR else OUT_DIR
    out_DIR.mkdir(parents=True, exist_ok=True)

    digest = pin_corpus_or_exit(corpus_PATH, readme_PATH)

    conn = sqlite3.connect(f"file:{corpus_PATH}?mode=ro", uri=True)
    rows = load_rows(conn)
    conn.close()

    train, eval_rows, split_stats = assign_splits(rows)

    # Eval set composition check
    n_sc = sum(1 for r in eval_rows if r["jp_realized"] != r["jp_default"])
    n_sn = sum(1 for r in eval_rows if r["jp_realized"] == r["jp_default"])
    split_stats["eval_should_change"] = n_sc
    split_stats["eval_should_not"] = n_sn
    assert n_sc > 0 and n_sn > 0, "eval must include both should-change and should-not"

    rules = learn_rules(train)
    preds = [predict_row(r, rules) for r in eval_rows]
    metrics = metrics_bundle(eval_rows, preds)

    # Full-corpus base rate (all judgeable, not just eval) for reporting
    n_ctx_def_all = sum(1 for r in rows if r["jp_ctx"] == r["jp_default"])
    n_sc_ctx_def_all = sum(
        1 for r in rows if r["jp_ctx"] == r["jp_default"] and r["jp_realized"] != r["jp_default"]
    )
    base_rate_all = n_sc_ctx_def_all / n_ctx_def_all if n_ctx_def_all else 0.0

    spot = spot_check_tojyutping(eval_rows, n=30)

    recommendation, reason = decide(metrics)

    # Serialize rules for metrics (trigram keys as strings)
    def key_join(k):
        return "|".join("" if x is None else str(x) for x in (k if isinstance(k, tuple) else (k,)))

    rules_ser = {
        "trigrams": {key_join(k): v for k, v in rules["trigrams"].items()},
        "bigrams_l": {key_join(k): v for k, v in rules["bigrams_l"].items()},
        "bigrams_r": {key_join(k): v for k, v in rules["bigrams_r"].items()},
        "unigrams": rules.get("unigrams", {}),
        "n_trigrams": len(rules["trigrams"]),
        "n_bigrams_l": len(rules["bigrams_l"]),
        "n_bigrams_r": len(rules["bigrams_r"]),
        "n_unigrams": len(rules.get("unigrams", {})),
        "hyperparams": {
            "TRAIN_PCT": TRAIN_PCT,
            "TRIGRAM_MIN_SUPPORT": TRIGRAM_MIN_SUPPORT,
            "UNIGRAM_MIN_SUPPORT": UNIGRAM_MIN_SUPPORT,
            "UNIGRAM_MIN_ALT_FRAC": UNIGRAM_MIN_ALT_FRAC,
            "note": "v1 refined: lift-gated tri+bi; unigrams disabled",
        },
    }

    out = {
        "corpus_sha256": digest,
        "base_rate_ctx_default_all_judgeable": round(base_rate_all, 6),
        "base_rate_ctx_default_n": n_ctx_def_all,
        "base_rate_should_change_n": n_sc_ctx_def_all,
        "split": split_stats,
        "rules": {
            "n_trigrams": rules_ser["n_trigrams"],
            "n_bigrams_l": rules_ser["n_bigrams_l"],
            "n_bigrams_r": rules_ser["n_bigrams_r"],
            "n_unigrams": rules_ser["n_unigrams"],
            "hyperparams": rules_ser["hyperparams"],
        },
        "metrics": metrics,
        "tojyutping_spot_check": spot,
        "recommendation": recommendation,
        "recommendation_reason": reason,
        "claim_limit": (
            "on these rows I beat ToJyutping at predicting realized reading"
        ),
    }

    snapshot_DIR = Path(__file__).resolve().parent
    committed_metrics_FILE = snapshot_DIR / "metrics.json"
    if args.check or committed_metrics_FILE.is_file():
        committed = json.loads(committed_metrics_FILE.read_text(encoding="utf-8"))
        if metrics_core(committed) != metrics_core(out):
            print("ABORT: rerun core metrics do not match committed metrics.json")
            print(json.dumps(metrics_core(out), ensure_ascii=False, indent=2, sort_keys=True))
            print(json.dumps(metrics_core(committed), ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(1)
        print("check: core metrics match committed metrics.json")

    in_place = out_DIR.resolve() == snapshot_DIR.resolve()
    if in_place and committed_metrics_FILE.is_file():
        print("kept committed metrics.json / rules.json / comparison.md (v1 snapshot)")
    else:
        (out_DIR / "metrics.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (out_DIR / "rules.json").write_text(
            json.dumps(rules_ser, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_comparison_md(out_DIR / "comparison.md", metrics, split_stats, rules)

    if args.write_predictions:
        write_predictions_csv(out_DIR / "predictions_eval.csv", eval_rows, preds)
    if args.write_generated_readme:
        write_readme(out_DIR / "README.md", metrics, split_stats, rules, spot, recommendation, reason)

    print("=== DONE ===")
    print("base_rate_all", round(base_rate_all, 6))
    print("eval base_rate", metrics["B_change_decision"]["base_rate_realized_ne_default"])
    print("F1", metrics["B_change_decision"]["f1"])
    print("EM delta", metrics["A_exact_match"]["all_judgeable_eval"]["delta_pred_minus_ctx"])
    print("true_win/lose", metrics["C_win_lose_tie"]["true_win"], metrics["C_win_lose_tie"]["true_lose"])
    print(recommendation, "—", reason)
    print("artifacts:", out_DIR)


if __name__ == "__main__":
    main(sys.argv[1:])
