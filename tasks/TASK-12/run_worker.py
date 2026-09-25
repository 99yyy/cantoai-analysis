"""TASK-12 worker: text-side G2P predictions, SQL replay, open analysis."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.status_io import sha256_file, write_json_atomic, write_status, write_text_atomic

CORPUS_FILE = ROOT / "data" / "corpus_v2.sqlite"
README_FILE = ROOT / "README.md"
TASK_DIR = ROOT / "tasks" / "TASK-12"
SQL_DIR = TASK_DIR / "sql"
PRED_DIR = TASK_DIR / "pred"
STATUS_FILE = TASK_DIR / "STATUS.json"
PIN = "2bd618ba8caf334548aab8ad6fcc54fdb899bfa3c09f02a16502e44032824f1f"
G2P_CODE_DIR = Path("/tmp/g2pmodels/g2pW-Cantonese")
G2P_MODEL_DIR = Path("/tmp/g2pmodels/G2PWModel-v2-onnx")
BERT_DIR = Path("/tmp/g2pmodels/bert-base-cantonese")
PYCANTOESE_REVISION = "3d729c01e53f6056cb1c6c527953837e9a106147"
G2PW_MODEL_REVISION = "2f435334357487f85d05429e2da1d6da93aafd2f"
G2PW_CODE_REVISION = "99f2d29cfd9cdd69c4fba9d8150060d596d3ca0d"
BERT_REVISION = "1d59d6ca8a09a96715f338d10d55bb180f223420"
MASTER_SEED = 20260920
STRATUM = "main"
B = 2000
SENT_FINAL_PUNCT = "。！？!?．…"
NUMBER_NAMES = (
    "n_multi_disagree",
    "n_tools_agree",
    "n_tj_match",
    "n_py_match",
    "n_g2pw_match",
    "n_default_match",
    "agree_tj_pm",
    "agree_py_pm",
    "agree_g2pw_pm",
    "agree_default_pm",
    "gap_tj_default_pm",
    "gap_py_default_pm",
    "gap_g2pw_default_pm",
)


def fail(message: str) -> None:
    print(message)
    raise SystemExit(1)


def sha256_path(path: Path) -> str:
    return sha256_file(str(path))


def readme_pin() -> str:
    for line in README_FILE.read_text(encoding="utf-8").splitlines():
        if "sha256:" in line:
            return line.split("`")[1]
    fail("README.md has no sha256 pin")
    return ""


def check_corpus_pin() -> str:
    digest = sha256_path(CORPUS_FILE)
    recorded = readme_pin()
    if digest != recorded or digest != PIN:
        print(digest)
        print(recorded)
        fail("corpus sha256 does not match README.md")
    return digest


def git_sha() -> str:
    out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
    return out.strip()


def git_clean() -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    return out.strip() == ""


def stratum_seed(master_seed: int, h: str) -> int:
    payload = f"{master_seed}:{h}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def norm(text: str | None) -> str:
    return (text or "").strip().casefold()


def require_frame(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {
        "videos": conn.execute("select count(*) from videos").fetchone()[0],
        "windows": conn.execute("select count(*) from windows").fetchone()[0],
        "syllables": conn.execute("select count(*) from syllables").fetchone()[0],
        "published": conn.execute(
            "select count(*) from syllables s inner join windows w on s.uid = w.uid "
            "where w.tier in ('A', 'B')"
        ).fetchone()[0],
    }
    expected = {
        "videos": 567,
        "windows": 4911,
        "syllables": 171867,
        "published": 164693,
    }
    for key, want in expected.items():
        got = counts[key]
        if got != want:
            print(got)
            print(want)
            fail(f"frame {key} count mismatch")
    return counts


def flatten_pycantonese(text: str) -> list[str]:
    import pycantonese

    pieces = pycantonese.characters_to_jyutping(text)
    readings: list[str] = []
    for piece, jp in pieces:
        if jp is None or str(jp).strip() == "":
            fail(f"pycantonese returned an empty reading for {piece!r}")
        tokens = str(jp).split()
        if len(piece) == 1:
            readings.append(tokens[0] if len(tokens) == 1 else str(jp).strip())
            continue
        if len(tokens) != len(piece):
            fail(f"pycantonese token count mismatch for {piece!r} -> {jp!r}")
        readings.extend(tokens)
    if len(readings) != len(text):
        fail(f"pycantonese length {len(readings)} != text length {len(text)}")
    return readings


def predict(windows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    import pycantonese

    sys.path.insert(0, str(G2P_CODE_DIR))
    from g2pw import G2PWConverter

    py_map: dict[str, str] = {}
    texts = []
    for window in windows:
        readings = flatten_pycantonese(window["text"])
        texts.append(window["text"])
        for syl_id, hyp in zip(window["ids"], readings):
            if hyp.strip() == "":
                fail(f"empty pycantonese hyp for {syl_id}")
            py_map[syl_id] = hyp
    print(f"pycantonese {pycantonese.__version__} windows {len(windows)}", flush=True)
    converter = G2PWConverter(
        model_dir=str(G2P_MODEL_DIR),
        model_source=str(BERT_DIR),
        use_cuda=False,
        batch_size=64,
        turnoff_tqdm=False,
    )
    g2_rows = converter(texts)
    g2_map: dict[str, str] = {}
    for window, readings in zip(windows, g2_rows):
        if len(readings) != len(window["text"]):
            fail(
                f"g2pw length {len(readings)} != text length {len(window['text'])} "
                f"uid {window['uid']}"
            )
        for syl_id, hyp in zip(window["ids"], readings):
            if hyp is None or str(hyp).strip() == "":
                fail(f"empty g2pw hyp for {syl_id}")
            g2_map[syl_id] = str(hyp)
    return py_map, g2_map


def write_jsonl(path: Path, mapping: dict[str, str]) -> None:
    lines = [
        json.dumps({"id": syl_id, "hyp": mapping[syl_id]}, ensure_ascii=False)
        for syl_id in sorted(mapping)
    ]
    write_text_atomic(str(path), "\n".join(lines) + "\n")


def load_windows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "select s.syl_id, s.uid, s.pos, s.char "
        "from syllables s inner join windows w on s.uid = w.uid "
        "where w.tier in ('A', 'B') "
        "order by s.uid, s.pos"
    ).fetchall()
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for syl_id, uid, pos, char in rows:
        if uid not in grouped:
            grouped[uid] = {"uid": uid, "ids": [], "chars": [], "pos": []}
            order.append(uid)
        grouped[uid]["ids"].append(syl_id)
        grouped[uid]["chars"].append(char)
        grouped[uid]["pos"].append(pos)
    windows = []
    for uid in order:
        item = grouped[uid]
        if item["pos"] != sorted(item["pos"]) or len(set(item["pos"])) != len(item["pos"]):
            fail(f"syllable pos is not strictly increasing for {uid}")
        item["text"] = "".join(item["chars"])
        windows.append(item)
    return windows


def ensure_predictions(conn: sqlite3.Connection, script_commit: str) -> None:
    py_file = PRED_DIR / "pycantonese.jsonl"
    g_file = PRED_DIR / "g2pw.jsonl"
    if py_file.exists() or g_file.exists():
        return
    windows = load_windows(conn)
    py_map, g2_map = predict(windows)
    if len(py_map) != 164693 or len(g2_map) != 164693:
        print(len(py_map))
        print(len(g2_map))
        fail("prediction row count is not the published syllable count")
    write_jsonl(py_file, py_map)
    write_jsonl(g_file, g2_map)
    cards = {
        "pycantonese": {
            "script_commit": script_commit,
            "model": "pycantonese",
            "model_revision": PYCANTOESE_REVISION,
            "decoding": {
                "package": "pycantonese",
                "version": "5.0.0",
                "function": "characters_to_jyutping",
                "input": "published window syllable characters in pos order",
                "device_note": "cpu",
            },
            "device": "cpu",
            "dirty": False,
        },
        "g2pw": {
            "script_commit": script_commit,
            "model": "Naozumi0512/g2pW-canto-20241206-bert-base",
            "model_revision": G2PW_MODEL_REVISION,
            "decoding": {
                "code": "Naozumi520/g2pW-Cantonese",
                "code_revision": G2PW_CODE_REVISION,
                "bert": "hon9kon9ize/bert-base-cantonese",
                "bert_revision": BERT_REVISION,
                "use_cuda": False,
                "batch_size": 64,
                "input": "published window syllable characters in pos order",
            },
            "device": "cpu",
            "dirty": False,
        },
    }
    for stem, payload in cards.items():
        write_json_atomic(str(PRED_DIR / f"{stem}.run.json"), payload)


def load_pred(conn: sqlite3.Connection) -> None:
    for stem in ("pycantonese", "g2pw"):
        path = PRED_DIR / f"{stem}.jsonl"
        conn.execute(f"drop table if exists pred_{stem}")
        conn.execute(
            f"create table pred_{stem} (id text primary key, hyp text not null)"
        )
        rows = []
        seen = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj["id"] in seen:
                fail(f"{stem} repeats id {obj['id']}")
            seen.add(obj["id"])
            if str(obj["hyp"]).strip() == "":
                fail(f"{stem} empty hyp {obj['id']}")
            rows.append((obj["id"], obj["hyp"]))
        conn.executemany(f"insert into pred_{stem} (id, hyp) values (?, ?)", rows)
    conn.commit()


def explain_sql(conn: sqlite3.Connection) -> None:
    import scripts.output_check as output_check

    for name in NUMBER_NAMES:
        path = SQL_DIR / f"{name}.sql"
        sql = path.read_text(encoding="utf-8")
        details = [
            " ".join(str(cell) for cell in row)
            for row in conn.execute(f"explain query plan {sql}")
        ]
        if not output_check.plan_touches_corpus(details, sql):
            fail(f"{name} explain misses a corpus table: {details}")


def replay_numbers(conn: sqlite3.Connection) -> dict[str, float]:
    values = {}
    for name in NUMBER_NAMES:
        sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
        first = conn.execute(sql).fetchall()
        second = conn.execute(sql).fetchall()
        if len(first) != 1 or len(first[0]) != 1 or first != second:
            fail(f"{name} did not replay one stable cell")
        value = first[0][0]
        if value is None:
            fail(f"{name} replayed NULL")
        values[name] = value
    if values["n_multi_disagree"] == 0:
        fail("n_multi_disagree is 0")
    return values


def fetch_published(conn: sqlite3.Connection) -> list[dict]:
    sql = (
        "select s.syl_id, s.video_id, s.char, s.dur, s.next_char, "
        "s.jp_ctx, s.jp_default, s.jp_realized, py.hyp, gw.hyp "
        "from syllables s "
        "inner join windows w on s.uid = w.uid "
        "inner join pred_pycantonese py on py.id = s.syl_id "
        "inner join pred_g2pw gw on gw.id = s.syl_id "
        "where w.tier in ('A', 'B')"
    )
    out = []
    for row in conn.execute(sql):
        item = {
            "syl_id": row[0],
            "video_id": row[1],
            "char": row[2],
            "dur": row[3],
            "next_char": row[4],
            "tj": norm(row[5]),
            "default": norm(row[6]),
            "realized": norm(row[7]),
            "py": norm(row[8]),
            "g2": norm(row[9]),
            "raw_realized": row[7],
            "raw_ctx": row[5],
            "raw_default": row[6],
            "raw_py": row[8],
            "raw_g2": row[9],
        }
        for raw in (row[5], row[6], row[7], row[8], row[9]):
            text = (raw or "").strip()
            if text.casefold() != text.lower():
                fail(f"casefold differs from lower for {text!r}")
        for key in ("tj", "default", "py", "g2"):
            if item[key] == "":
                fail(f"empty normalised reading {key} on {item['syl_id']}")
        out.append(item)
    if len(out) != 164693:
        print(len(out))
        print(164693)
        fail("published join count mismatch")
    return out


def is_judgeable(row: dict) -> bool:
    realized = (row["raw_realized"] or "").strip()
    return len(realized) > 0 and row["dur"] > 0


def tools_differ(row: dict) -> bool:
    return not (row["tj"] == row["py"] and row["tj"] == row["g2"] and row["py"] == row["g2"])


def agree_pm(rows: list[dict], key: str) -> float | None:
    if not rows:
        return None
    hits = sum(row[key] == row["realized"] for row in rows)
    return 1000.0 * hits / len(rows)


def pattern(row: dict) -> str:
    flags = (
        int(row["tj"] != row["py"]),
        int(row["tj"] != row["g2"]),
        int(row["py"] != row["g2"]),
    )
    return f"tj_ne_py={flags[0]},tj_ne_g2pw={flags[1]},py_ne_g2pw={flags[2]}"


def top_chars(rows: list[dict], k: int = 15) -> list[dict]:
    counts = Counter(row["char"] for row in rows)
    return [{"char": ch, "n": n} for ch, n in counts.most_common(k)]


def char_disagreement(rows: list[dict]) -> list[dict]:
    bucket: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        cell = bucket[row["char"]]
        cell[0] += 1
        cell[1] += int(row["tj"] != row["py"])
        cell[2] += int(row["tj"] != row["g2"])
        cell[3] += int(row["py"] != row["g2"])
    table = [
        {
            "char": ch,
            "n": cell[0],
            "tj_ne_py": cell[1],
            "tj_ne_g2pw": cell[2],
            "py_ne_g2pw": cell[3],
        }
        for ch, cell in bucket.items()
    ]
    table.sort(key=lambda item: (-item["n"], item["char"]))
    return table


def nei_subset(rows: list[dict]) -> dict:
    punct = set(SENT_FINAL_PUNCT)
    focus = [row for row in rows if row["char"] == "呢"]
    empty = 0
    final = 0
    nonfinal = []
    next_counts: Counter[str] = Counter()
    for row in focus:
        trimmed = (row["next_char"] or "").strip()
        next_counts[trimmed] += 1
        if len(trimmed) == 0:
            empty += 1
        elif trimmed in punct:
            final += 1
        else:
            nonfinal.append(row)
    return {
        "n_ne_judgeable_published": len(focus),
        "n_next_empty": empty,
        "n_sent_final": final,
        "n_nonfinal": len(nonfinal),
        "next_char_counts": [
            {"next_char": ch, "n": n} for ch, n in sorted(next_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "agree_tj_pm": agree_pm(nonfinal, "tj"),
        "agree_py_pm": agree_pm(nonfinal, "py"),
        "agree_g2pw_pm": agree_pm(nonfinal, "g2"),
        "agree_default_pm": agree_pm(nonfinal, "default"),
        "descriptive": 1,
    }


def distinct_report(rows: list[dict]) -> dict:
    columns = {
        "char": {row["char"] for row in rows},
        "tj": {row["tj"] for row in rows},
        "py": {row["py"] for row in rows},
        "g2pw": {row["g2"] for row in rows},
        "default": {row["default"] for row in rows},
        "realized": {row["realized"] for row in rows},
    }
    report = {}
    for name, values in columns.items():
        report[name] = {"distinct": len(values), "q7_constant": 1 if len(values) == 1 else 0}
    return report


def bootstrap(main_rows: list[dict], point: dict[str, float]) -> dict:
    per_video: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for row in main_rows:
        cell = per_video[row["video_id"]]
        cell[0] += 1
        cell[1] += int(row["tj"] == row["realized"])
        cell[2] += int(row["py"] == row["realized"])
        cell[3] += int(row["g2"] == row["realized"])
        cell[4] += int(row["default"] == row["realized"])
    videos = sorted(per_video)
    mat = np.array([per_video[vid] for vid in videos], dtype=np.int64)
    g_count = int(mat.shape[0])
    seed = stratum_seed(MASTER_SEED, STRATUM)
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.integers(0, g_count, size=(B, g_count))
    keys = ("tj", "py", "g2pw")
    gaps = {key: np.empty(B, dtype=np.float64) for key in keys}
    agrees = np.empty(B, dtype=np.float64)
    ratios = {key: np.empty(B, dtype=np.float64) for key in keys}
    incomparable = np.zeros(B, dtype=np.int8)
    for i in range(B):
        weights = np.bincount(draws[i], minlength=g_count).astype(np.float64)
        totals = weights @ mat
        denom = totals[0]
        agree_default = 1000.0 * totals[4] / denom
        agrees[i] = agree_default
        if agree_default == 0:
            incomparable[i] = 1
        for col, key in ((1, "tj"), (2, "py"), (3, "g2pw")):
            gap = 1000.0 * (totals[col] - totals[4]) / denom
            gaps[key][i] = gap
            ratios[key][i] = np.nan if agree_default == 0 else gap / agree_default
    unreliable = 1 if g_count < 10 else 0
    summary = {}
    for key, gap_name, agree_name in (
        ("tj", "gap_tj_default_pm", "agree_tj_pm"),
        ("py", "gap_py_default_pm", "agree_py_pm"),
        ("g2pw", "gap_g2pw_default_pm", "agree_g2pw_pm"),
    ):
        lo, hi = [float(x) for x in np.quantile(gaps[key], [0.025, 0.975])]
        point_gap = float(point[gap_name])
        point_default = float(point["agree_default_pm"])
        if point_default == 0:
            point_ratio = None
        else:
            point_ratio = point_gap / point_default
        usable = ratios[key][~np.isnan(ratios[key])]
        if usable.size:
            rlo, rhi = [float(x) for x in np.quantile(usable, [0.025, 0.975])]
        else:
            rlo, rhi = None, None
        gap_away = lo > 0 or hi < 0
        ratio_away = (
            rlo is not None and rhi is not None and (rlo > 0 or rhi < 0)
        )
        sign_flip = False
        if point_ratio is None:
            sign_flip = True
        elif point_gap == 0 or point_ratio == 0:
            sign_flip = (point_gap == 0) != (point_ratio == 0)
        else:
            sign_flip = (point_gap > 0) != (point_ratio > 0)
        conclusion_flip = sign_flip or (gap_away != ratio_away)
        if unreliable:
            conclusion = "inconclusive"
        elif gap_away and lo > 0:
            conclusion = "gap_above_0"
        elif gap_away and hi < 0:
            conclusion = "gap_below_0"
        else:
            conclusion = "consistent_with_0"
        summary[f"gap_{key}_default_ci"] = {
            "point_gap_pm": point_gap,
            "point_agree_pm": float(point[agree_name]),
            "point_agree_default_pm": point_default,
            "ci95": [lo, hi],
            "point_relative": point_ratio,
            "relative_ci95": [rlo, rhi],
            "n_incomparable_rounds": int(incomparable.sum()),
            "sign_flip": sign_flip,
            "conclusion_flip": conclusion_flip,
            "conclusion": conclusion,
            "ci_unreliable": unreliable,
            "G": g_count,
        }
    return {
        "master_seed": MASTER_SEED,
        "stratum": STRATUM,
        "stratum_seed": seed,
        "B": B,
        "G": g_count,
        "ci_unreliable": unreliable,
        "method": (
            "resample video_id with replacement; a cluster drawn k times "
            "contributes its main-set rows k times; recompute the global gap"
        ),
        "gaps": summary,
    }


def clause24(published: list[dict], main_rows: list[dict]) -> dict:
    n_total = len(published)
    empty = [row for row in published if len((row["raw_realized"] or "").strip()) == 0]
    dur0 = [row for row in published if row["dur"] <= 0]
    both = [
        row
        for row in published
        if len((row["raw_realized"] or "").strip()) == 0 and row["dur"] <= 0
    ]
    judgeable = [row for row in published if is_judgeable(row)]
    def matches(rows: list[dict]) -> dict[str, int]:
        return {
            "n_match_tj": sum(row["tj"] == row["realized"] for row in rows),
            "n_match_py": sum(row["py"] == row["realized"] for row in rows),
            "n_match_g2pw": sum(row["g2"] == row["realized"] for row in rows),
            "n_match_default": sum(row["default"] == row["realized"] for row in rows),
        }
    return {
        "published": {
            "n_total": n_total,
            "n_empty_realized": len(empty),
            "n_dur_le_0": len(dur0),
            "n_empty_and_dur_le_0": len(both),
            "n_judgeable": len(judgeable),
            **matches(judgeable),
        },
        "main": {
            "n_total": len(main_rows),
            "n_empty_realized": 0,
            "n_dur_le_0": 0,
            "n_empty_and_dur_le_0": 0,
            "n_judgeable": len(main_rows),
            **matches(main_rows),
        },
    }


def coverage(rows: list[dict], id_set: set[str], label: str) -> dict:
    ids = {row["syl_id"] for row in rows}
    missing = len(ids - id_set)
    if missing:
        print(missing)
        fail(f"{label} pred ids missing")
    return {"rows": len(rows), "ids": len(ids), "missing": 0}


def write_open_analysis(payload: dict) -> None:
    boot = payload["bootstrap"]
    lines = [
        "# TASK-12 开放分析",
        "",
        "总体是这个频道的 567 条视频。聚类停在 `video_id`。",
        "比较的是一致率：左侧读音与 `jp_realized` 经 trim 与 Unicode casefold 后整串相等。",
        "声学标签 `jp_realized` 来自词典侧，一致率可能被高估。",
        "`review_prior` 没有用来分层、过滤或加权。分子没有用 `jp_match`。",
        "",
        "## 头条",
        "",
        "只点名 `gap_tj_default_pm`、`gap_py_default_pm`、`gap_g2pw_default_pm`。",
        "每个 gap 单独相对 0 判断。不跨工具比较 gap 大小。",
        "",
    ]
    bits = []
    for key, label in (
        ("tj", "gap_tj_default_pm"),
        ("py", "gap_py_default_pm"),
        ("g2pw", "gap_g2pw_default_pm"),
    ):
        item = boot["gaps"][f"gap_{key}_default_ci"]
        lo, hi = item["ci95"]
        bits.append(
            f"{label} 点估计 {item['point_gap_pm']:.6f}，95% 区间 [{lo:.6f}, {hi:.6f}]，"
            f"结论 {item['conclusion']}"
        )
    lines.append("一句话：在主评测集上，" + "；".join(bits) + "。")
    lines.append("")
    lines.append("## 四个一致率与三个 gap")
    lines.append("")
    for name in (
        "agree_tj_pm",
        "agree_py_pm",
        "agree_g2pw_pm",
        "agree_default_pm",
        "gap_tj_default_pm",
        "gap_py_default_pm",
        "gap_g2pw_default_pm",
    ):
        lines.append(f"- `{name}` = {payload['values'][name]}")
    lines.append("")
    lines.append("## Q1 Q2 Q3")
    lines.append("")
    lines.append("Q1 不适用：主结果不是按序数切分的组间差，主集由文字工具两两相等性定义。")
    lines.append("Q2 不适用：主结果是同一子集上的一致率与配对差，不是两组行加权组间差。")
    lines.append("Q3 不适用：不是份额分解。gap 是定义差，不写「解释了」。")
    lines.append("")
    lines.append("## Q4 区间")
    lines.append("")
    lines.append(
        f"`master_seed` = {boot['master_seed']}。层 `h` = `{boot['stratum']}`。"
        f"层种子 `int(sha256(\"{boot['master_seed']}:{boot['stratum']}\").hexdigest()[:8], 16)`"
        f" = {boot['stratum_seed']}。只有这一层。"
    )
    lines.append(
        f"`B` = {boot['B']}。`G` = {boot['G']}。`ci_unreliable` = {boot['ci_unreliable']}。"
    )
    lines.append(boot["method"] + "。")
    lines.append("区间端点不进 `numbers`。")
    for key in ("tj", "py", "g2pw"):
        item = boot["gaps"][f"gap_{key}_default_ci"]
        lines.append(
            f"- `gap_{key}_default_ci` 点估计 gap {item['point_gap_pm']}，"
            f"对应 agree {item['point_agree_pm']}，基线 agree_default {item['point_agree_default_pm']}，"
            f"区间 {item['ci95']}。相对幅度点估计 {item['point_relative']}，"
            f"相对幅度区间 {item['relative_ci95']}，不可比轮数 {item['n_incomparable_rounds']}。"
            f"符号翻转 {item['sign_flip']}。结论翻转 {item['conclusion_flip']}。"
        )
    lines.append("相对幅度每轮用该轮重算的 gap 除以该轮重算的 agree_default；分母为 0 的轮标不可比，不进入相对幅度区间。")
    lines.append("")
    lines.append("## Q5")
    lines.append("")
    lines.append(
        "漏掉本应不同却被标成相同的行，主集会偏向更容易见到文字侧差异的子集，"
        "gap 的绝对值可能偏大。把噪声差纳入主集，gap 会被稀释。"
    )
    lines.append(
        f"两侧规模：`n_multi_disagree` = {payload['values']['n_multi_disagree']}，"
        f"`n_tools_agree` = {payload['values']['n_tools_agree']}。"
    )
    lines.append("")
    lines.append("## Q7")
    lines.append("")
    lines.append("主集两两分歧模式：")
    for item in payload["patterns_main"]:
        lines.append(f"- {item['pattern']}: {item['n']}")
    lines.append("对照侧两两分歧模式（应全为 0 对不等）：")
    for item in payload["patterns_control"]:
        lines.append(f"- {item['pattern']}: {item['n']}")
    lines.append("主集 `char` 顶频：")
    for item in payload["top_main"]:
        lines.append(f"- {item['char']}: {item['n']}")
    lines.append("对照侧 `char` 顶频：")
    for item in payload["top_control"]:
        lines.append(f"- {item['char']}: {item['n']}")
    lines.append("框内依赖列 distinct：")
    for name, item in payload["distinct"].items():
        flag = f" q7_constant=1" if item["q7_constant"] else ""
        lines.append(f"- {name}: distinct={item['distinct']}{flag}")
    nei = payload["nei"]
    lines.append(
        f"「呢」在发布集可判定行上 {nei['n_ne_judgeable_published']} 行："
        f"next 为空 {nei['n_next_empty']}，句末标点 {nei['n_sent_final']}，"
        f"非句末 {nei['n_nonfinal']}。判定只用 `next_char`。"
    )
    lines.append("非句末「呢」一致率（descriptive=1）：")
    for key in ("agree_tj_pm", "agree_py_pm", "agree_g2pw_pm", "agree_default_pm"):
        lines.append(f"- {key} = {nei[key]}")
    lines.append(
        f"pred 覆盖：主集 missing {payload['coverage']['main']['missing']}，"
        f"对照侧 missing {payload['coverage']['control']['missing']}。"
        "缺行会在写结果前退出非零。"
    )
    lines.append("")
    lines.append("## 契约第 24 条计数")
    lines.append("")
    lines.append("分子是左侧与 `jp_realized` 整串相等，不是 `jp_match`。")
    lines.append(json.dumps(payload["clause24"], ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("## 描述性：词典侧 ctx 与 default 不同的子集")
    lines.append("")
    lines.append("descriptive=1。发布集 ∩ 可判定 ∩（规范化后 `jp_ctx` ≠ `jp_default`）。不进头条。")
    task11 = payload["task11"]
    lines.append(f"行数 {task11['n']}。")
    for key in ("agree_tj_pm", "agree_py_pm", "agree_g2pw_pm", "agree_default_pm"):
        lines.append(f"- {key} = {task11[key]}")
    lines.append("")
    lines.append("## 逐字分歧表")
    lines.append("")
    lines.append("descriptive=1。主集上按 `char` 汇总三工具两两不等次数。全表在 `manifest.json` 的 `char_disagreement`。")
    lines.append("行数最多的 20 个字：")
    for item in payload["char_disagreement"][:20]:
        lines.append(
            f"- {item['char']}: n={item['n']} tj≠py={item['tj_ne_py']} "
            f"tj≠g2pw={item['tj_ne_g2pw']} py≠g2pw={item['py_ne_g2pw']}"
        )
    lines.append("")
    write_text_atomic(str(TASK_DIR / "open_analysis.md"), "\n".join(lines) + "\n")


def column_sets(conn: sqlite3.Connection) -> dict[str, list[str]]:
    out = {}
    for table in ("videos", "windows", "syllables", "runs"):
        out[table] = [row[1] for row in conn.execute(f"pragma table_info({table})")]
    return out


def main() -> None:
    digest = check_corpus_pin()
    script_commit = git_sha()
    pred_ready = all(
        (PRED_DIR / name).is_file()
        for name in (
            "pycantonese.jsonl",
            "g2pw.jsonl",
            "pycantonese.run.json",
            "g2pw.run.json",
        )
    )
    if not pred_ready and not git_clean():
        fail("working tree is dirty; predictions require a committed script")
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    write_status(str(STATUS_FILE), {"status": "running"})
    src = sqlite3.connect(f"file:{CORPUS_FILE}?mode=ro", uri=True)
    frame = require_frame(src)
    empty = src.execute(
        "select count(*) from syllables s inner join windows w on s.uid = w.uid "
        "where w.tier in ('A', 'B') and length(trim(coalesce(s.jp_realized, ''))) > 0 "
        "and s.dur > 0 and ("
        "s.jp_ctx is null or length(trim(s.jp_ctx)) = 0 or "
        "s.jp_default is null or length(trim(s.jp_default)) = 0)"
    ).fetchone()[0]
    if empty:
        print(empty)
        fail("judgeable published row has an empty jp_ctx or jp_default")
    ensure_predictions(src, script_commit)
    tmp_db = Path("/tmp/task12_worker.sqlite")
    if tmp_db.exists():
        tmp_db.unlink()
    src.close()
    subprocess.check_call(["cp", str(CORPUS_FILE), str(tmp_db)])
    conn = sqlite3.connect(tmp_db)
    load_pred(conn)
    explain_sql(conn)
    values = replay_numbers(conn)
    published = fetch_published(conn)
    judgeable = []
    for row in published:
        if not is_judgeable(row):
            continue
        if row["raw_ctx"] is None or row["raw_default"] is None:
            fail("judgeable row has NULL dictionary column")
        if norm(row["raw_ctx"]) == "" or norm(row["raw_default"]) == "":
            fail("judgeable row has empty dictionary column")
        if norm(row["tj"]) != row["tj"].lower() or norm(row["py"]) != row["py"].lower():
            fail("casefold and lower differ; SQL lower() would not implement casefold")
        judgeable.append(row)
    main_rows = [row for row in judgeable if tools_differ(row)]
    control_rows = [row for row in judgeable if not tools_differ(row)]
    if len(main_rows) + len(control_rows) != len(judgeable):
        fail("judgeable rows are not partitioned")
    if len(main_rows) != int(values["n_multi_disagree"]):
        print(len(main_rows))
        print(values["n_multi_disagree"])
        fail("python main-set count does not match SQL")
    if len(control_rows) != int(values["n_tools_agree"]):
        print(len(control_rows))
        print(values["n_tools_agree"])
        fail("python control-set count does not match SQL")
    py_ids = {row[0] for row in conn.execute("select id from pred_pycantonese")}
    g_ids = {row[0] for row in conn.execute("select id from pred_g2pw")}
    cov = {
        "main": {
            "pycantonese": coverage(main_rows, py_ids, "main pycantonese"),
            "g2pw": coverage(main_rows, g_ids, "main g2pw"),
            "missing": 0,
        },
        "control": {
            "pycantonese": coverage(control_rows, py_ids, "control pycantonese"),
            "g2pw": coverage(control_rows, g_ids, "control g2pw"),
            "missing": 0,
        },
    }
    patterns_main = Counter(pattern(row) for row in main_rows)
    patterns_control = Counter(pattern(row) for row in control_rows)
    if any(key != "tj_ne_py=0,tj_ne_g2pw=0,py_ne_g2pw=0" and n for key, n in patterns_control.items()):
        fail("control side has a tool mismatch")
    boot = bootstrap(main_rows, values)
    counts24 = clause24(published, main_rows)
    task11_rows = [row for row in judgeable if row["tj"] != row["default"]]
    char_table = char_disagreement(main_rows)
    n_main = int(values["n_multi_disagree"])
    n_control = int(values["n_tools_agree"])
    results = []
    for name in NUMBER_NAMES:
        if name == "n_tools_agree":
            n_value = n_control
        elif name == "n_multi_disagree":
            n_value = n_main
        else:
            n_value = n_main
        value = values[name]
        if name.startswith("n_"):
            value = int(value)
        results.append(
            {
                "name": name,
                "value": value,
                "n": n_value,
                "query": f"tasks/TASK-12/sql/{name}.sql",
            }
        )
    write_json_atomic(str(TASK_DIR / "results.json"), results)
    write_json_atomic(str(TASK_DIR / "bootstrap.json"), boot)
    head = script_commit
    manifest = {
        "git_sha": head,
        "corpus_sha256": digest,
        "sent_final_punct": list(SENT_FINAL_PUNCT),
        "normalization": "trim then Unicode casefold; SQL replay uses lower(trim()) because these readings are ASCII jyutping",
        "packages": {
            "pycantonese": {
                "version": "5.0.0",
                "model_revision": PYCANTOESE_REVISION,
            },
            "g2pw": {
                "model": "Naozumi0512/g2pW-canto-20241206-bert-base",
                "model_revision": G2PW_MODEL_REVISION,
                "code_revision": G2PW_CODE_REVISION,
                "bert_revision": BERT_REVISION,
            },
        },
        "inputs": {
            "corpus": {
                "path": "data/corpus_v2.sqlite",
                "sha256": digest,
                "rows": frame,
                "columns": column_sets(conn),
                "git_sha": head,
            },
            "pred_pycantonese": {
                "path": "tasks/TASK-12/pred/pycantonese.jsonl",
                "sha256": sha256_path(PRED_DIR / "pycantonese.jsonl"),
                "rows": len(py_ids),
                "columns": ["id", "hyp"],
                "git_sha": head,
            },
            "pred_g2pw": {
                "path": "tasks/TASK-12/pred/g2pw.jsonl",
                "sha256": sha256_path(PRED_DIR / "g2pw.jsonl"),
                "rows": len(g_ids),
                "columns": ["id", "hyp"],
                "git_sha": head,
            },
        },
        "steps": [
            {
                "step": "tier_filter",
                "rule": "windows.tier IN ('A','B')",
                "group": "published",
                "rows_before": frame["syllables"],
                "rows_after": frame["published"],
            },
            {
                "step": "judgeable",
                "rule": "trim(jp_realized) non-empty AND dur > 0",
                "group": "judgeable",
                "rows_before": frame["published"],
                "rows_after": len(judgeable),
            },
            {
                "step": "main_set",
                "rule": "at least one normalised tool pair differs",
                "group": "main",
                "rows_before": len(judgeable),
                "rows_after": len(main_rows),
            },
            {
                "step": "control_set",
                "rule": "three normalised tool readings equal",
                "group": "control",
                "rows_before": len(judgeable),
                "rows_after": len(control_rows),
            },
        ],
        "unassigned_judgeable": 0,
        "both_main_and_control": 0,
        "clause24": counts24,
        "q7_patterns_main": [
            {"pattern": key, "n": n} for key, n in sorted(patterns_main.items())
        ],
        "q7_patterns_control": [
            {"pattern": key, "n": n} for key, n in sorted(patterns_control.items())
        ],
        "q7_top_char_main": top_chars(main_rows),
        "q7_top_char_control": top_chars(control_rows),
        "q7_distinct": distinct_report(published),
        "q7_nei": nei_subset(judgeable),
        "q7_pred_coverage": cov,
        "task11_subset": {
            "descriptive": 1,
            "n": len(task11_rows),
            "agree_tj_pm": agree_pm(task11_rows, "tj"),
            "agree_py_pm": agree_pm(task11_rows, "py"),
            "agree_g2pw_pm": agree_pm(task11_rows, "g2"),
            "agree_default_pm": agree_pm(task11_rows, "default"),
        },
        "char_disagreement": char_table,
        "bootstrap_summary": boot,
    }
    write_json_atomic(str(TASK_DIR / "manifest.json"), manifest)
    write_open_analysis(
        {
            "values": {row["name"]: row["value"] for row in results},
            "bootstrap": boot,
            "patterns_main": manifest["q7_patterns_main"],
            "patterns_control": manifest["q7_patterns_control"],
            "top_main": manifest["q7_top_char_main"],
            "top_control": manifest["q7_top_char_control"],
            "distinct": manifest["q7_distinct"],
            "nei": manifest["q7_nei"],
            "coverage": cov,
            "clause24": counts24,
            "task11": manifest["task11_subset"],
            "char_disagreement": char_table,
        }
    )
    outputs = {}
    for path in (
        TASK_DIR / "results.json",
        TASK_DIR / "manifest.json",
        TASK_DIR / "bootstrap.json",
        TASK_DIR / "open_analysis.md",
        PRED_DIR / "pycantonese.jsonl",
        PRED_DIR / "g2pw.jsonl",
        PRED_DIR / "pycantonese.run.json",
        PRED_DIR / "g2pw.run.json",
    ):
        outputs[path.name] = sha256_path(path)
    write_status(str(STATUS_FILE), {"status": "complete", "outputs": outputs})
    conn.close()
    print("complete", flush=True)


if __name__ == "__main__":
    main()
