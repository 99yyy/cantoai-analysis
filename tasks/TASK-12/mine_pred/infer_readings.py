"""Verifier-side CPU readings for PyCantonese and g2pW-Cantonese.

One published window is one character string: syllables ordered by pos,
concatenated. That string is what both tools see, so each syllable lines
up with one character. A tool that returns no reading is stored as the
non-empty token NO_READING; an empty hyp is rejected by the gate, and a
missing id would drop the syllable out of the join.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

NO_READING = "∅"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        sys.exit(f"missing required environment variable {name}")
    return value


def window_rows(conn: sqlite3.Connection) -> list[tuple[str, list[tuple[str, str]]]]:
    windows = [
        row[0]
        for row in conn.execute(
            "SELECT uid FROM windows WHERE tier IN ('A', 'B') ORDER BY uid"
        )
    ]
    grouped: list[tuple[str, list[tuple[str, str]]]] = []
    for uid in windows:
        syls = conn.execute(
            "SELECT syl_id, char FROM syllables WHERE uid = ? ORDER BY pos, syl_id",
            (uid,),
        ).fetchall()
        grouped.append((uid, [(sid, ch) for sid, ch in syls]))
    return grouped


def expand_pycantonese(text: str) -> list[str]:
    import pycantonese

    pairs = pycantonese.characters_to_jyutping(text)
    rebuilt = "".join(word for word, _jp in pairs)
    if rebuilt != text:
        sys.exit(f"pycantonese segmentation did not rebuild the window text")
    out: list[str] = []
    for word, jp in pairs:
        if jp is None:
            out.extend([NO_READING] * len(word))
            continue
        parts = jp.split()
        if len(parts) != len(word):
            for ch in word:
                one = pycantonese.characters_to_jyutping([ch])
                if len(one) != 1 or one[0][0] != ch or one[0][1] is None:
                    out.append(NO_READING)
                else:
                    syls = one[0][1].split()
                    out.append(syls[0] if len(syls) == 1 else NO_READING)
            continue
        out.extend(parts)
    if len(out) != len(text):
        sys.exit("pycantonese expansion length does not match the window")
    return out


def atomic_jsonl(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for sid, hyp in rows:
                if hyp.strip() == "":
                    sys.exit(f"refusing empty hyp for {sid}")
                fh.write(json.dumps({"id": sid, "hyp": hyp}, ensure_ascii=False))
                fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def main() -> None:
    corpus_path = require_env("CORPUS_PATH")
    g2pw_model_dir = require_env("G2PW_MODEL_DIR")
    bert_dir = require_env("BERT_DIR")
    out_dir = Path(require_env("OUT_DIR"))
    conn = sqlite3.connect(corpus_path)
    grouped = window_rows(conn)
    conn.close()
    texts = ["".join(ch for _sid, ch in syls) for _uid, syls in grouped]
    py_rows: list[tuple[str, str]] = []
    none_py = 0
    for text, (_uid, syls) in zip(texts, grouped):
        readings = expand_pycantonese(text)
        if len(readings) != len(syls):
            sys.exit("pycantonese readings do not match syllable count")
        for (sid, _ch), hyp in zip(syls, readings):
            if hyp == NO_READING:
                none_py += 1
            py_rows.append((sid, hyp))
    sys.path.insert(0, require_env("G2PW_REPO"))
    from g2pw import G2PWConverter

    conv = G2PWConverter(
        model_dir=g2pw_model_dir,
        model_source=bert_dir,
        use_cuda=False,
        batch_size=64,
        turnoff_tqdm=True,
    )
    g2_rows: list[tuple[str, str]] = []
    none_g2 = 0
    batch = 200
    for start in range(0, len(texts), batch):
        chunk = texts[start : start + batch]
        predicted = conv(chunk)
        if len(predicted) != len(chunk):
            sys.exit("g2pw returned a different number of sentences")
        for sent, row, (_uid, syls) in zip(
            chunk, predicted, grouped[start : start + batch]
        ):
            if len(row) != len(sent) or len(row) != len(syls):
                sys.exit("g2pw alignment length does not match the window")
            for (sid, _ch), hyp in zip(syls, row):
                if hyp is None or str(hyp).strip() == "":
                    none_g2 += 1
                    hyp = NO_READING
                g2_rows.append((sid, str(hyp)))
        print(f"g2pw {min(start + batch, len(texts))}/{len(texts)}", flush=True)
    py_rows.sort(key=lambda r: r[0])
    g2_rows.sort(key=lambda r: r[0])
    if len(py_rows) != len({i for i, _ in py_rows}) or len(g2_rows) != len(
        {i for i, _ in g2_rows}
    ):
        sys.exit("duplicate syllable id in predictions")
    if [i for i, _ in py_rows] != [i for i, _ in g2_rows]:
        sys.exit("pycantonese and g2pw id sets differ")
    atomic_jsonl(out_dir / "pycantonese.jsonl", py_rows)
    atomic_jsonl(out_dir / "g2pw.jsonl", g2_rows)
    print(f"rows {len(py_rows)} none_py {none_py} none_g2 {none_g2}")


if __name__ == "__main__":
    main()
