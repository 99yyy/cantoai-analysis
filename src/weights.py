"""Population-level stratum weights w_h = N_h / n_h_judgeable."""

from __future__ import annotations

import numpy as np


def stratum_weights(N_h: np.ndarray, n_h_judgeable: np.ndarray) -> np.ndarray:
    return np.asarray(N_h, dtype=float) / np.asarray(n_h_judgeable, dtype=float)


def assert_stratum_weights(w: np.ndarray, N_h: np.ndarray, n_h_judgeable: np.ndarray) -> None:
    w = np.asarray(w, dtype=float)
    N_h = np.asarray(N_h, dtype=float)
    n_h_judgeable = np.asarray(n_h_judgeable, dtype=float)
    mass = float(np.dot(w, n_h_judgeable))
    total = float(np.sum(N_h))
    if abs(mass - total) > 1e-6:
        print(mass, total)
        raise ValueError("stratum weights do not equal N_h divided by n_h_judgeable")
