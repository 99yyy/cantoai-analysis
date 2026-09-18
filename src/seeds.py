"""Per-stratum bootstrap seeds (clause 14)."""

from __future__ import annotations

import hashlib

SEED_CONSTRUCTION = (
    "per-stratum seed must equal int(sha256(master_seed:h)[:8], 16)"
)
SEEDS_NOT_DISTINCT = "per-stratum seeds must be pairwise distinct"


def stratum_seed(master_seed: int, h: str) -> int:
    payload = f"{master_seed}:{h}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def assert_stratum_seeds(master_seed: int, seeds: dict[str, int]) -> None:
    values = list(seeds.values())
    if len(values) != len(set(values)):
        raise ValueError(SEEDS_NOT_DISTINCT)
    for h, observed in seeds.items():
        expected = int(
            hashlib.sha256(f"{master_seed}:{h}".encode("utf-8")).hexdigest()[:8],
            16,
        )
        if observed != expected:
            raise ValueError(SEED_CONSTRUCTION)
