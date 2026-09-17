#!/usr/bin/env python3
"""Unit tests for jyutping onset/coda/tone parsing (task-brief requirement)."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jyutping import parse_coda, parse_initial, parse_tone  # noqa: E402


class TestParseInitial(unittest.TestCase):
    def test_n_not_ng(self):
        self.assertEqual(parse_initial("naa4"), "n-")
        self.assertEqual(parse_initial("nei5"), "n-")

    def test_ng_before_n(self):
        self.assertEqual(parse_initial("ngaa5"), "ng-")
        self.assertEqual(parse_initial("ngo5"), "ng-")

    def test_l(self):
        self.assertEqual(parse_initial("lei5"), "l-")
        self.assertEqual(parse_initial("laa1"), "l-")

    def test_gw_kw_before_g_k(self):
        self.assertEqual(parse_initial("gwok3"), "gw-/kw-")
        self.assertEqual(parse_initial("kwan1"), "gw-/kw-")
        self.assertEqual(parse_initial("gaa1"), "g-/k-")
        self.assertEqual(parse_initial("kei4"), "g-/k-")

    def test_zero_vowel_and_glide(self):
        self.assertEqual(parse_initial("aa3"), "zero")
        self.assertEqual(parse_initial("jyu6"), "zero")
        self.assertEqual(parse_initial("wai6"), "zero")
        self.assertEqual(parse_initial("o1"), "zero")

    def test_other(self):
        self.assertEqual(parse_initial("baa1"), "other")
        self.assertEqual(parse_initial("si1"), "other")
        self.assertEqual(parse_initial("zung1"), "other")
        self.assertEqual(parse_initial("haa6"), "other")

    def test_missing(self):
        self.assertEqual(parse_initial(None), "other")
        self.assertEqual(parse_initial(""), "other")


class TestParseCoda(unittest.TestCase):
    def test_n_not_ng(self):
        self.assertEqual(parse_coda("san1"), "-n")
        self.assertEqual(parse_coda("tin1"), "-n")

    def test_ng_before_n(self):
        self.assertEqual(parse_coda("saang1"), "-ng")
        self.assertEqual(parse_coda("zung1"), "-ng")

    def test_stops(self):
        self.assertEqual(parse_coda("saat3"), "-t")
        self.assertEqual(parse_coda("baak3"), "-k")
        self.assertEqual(parse_coda("sap6"), "-p")

    def test_m_and_open(self):
        self.assertEqual(parse_coda("sam1"), "-m")
        self.assertEqual(parse_coda("si1"), "open")
        self.assertEqual(parse_coda("hou2"), "open")
        self.assertEqual(parse_coda("jyu5"), "open")

    def test_missing(self):
        self.assertEqual(parse_coda(None), "open")
        self.assertEqual(parse_coda(""), "open")


class TestParseTone(unittest.TestCase):
    def test_tones_1_to_6(self):
        for t in range(1, 7):
            self.assertEqual(parse_tone(f"si{t}"), t)

    def test_missing(self):
        self.assertEqual(parse_tone("si"), 0)
        self.assertEqual(parse_tone(None), 0)
        self.assertEqual(parse_tone(""), 0)


if __name__ == "__main__":
    unittest.main()
