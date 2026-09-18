"""Flatten nested keys with a separator that cannot appear in a segment."""

from __future__ import annotations

from typing import Any

FLATTEN_SEPARATOR_IN_KEY = "flatten separator must not occur inside a key segment"
DUPLICATE_OUTPUT = "duplicate output column or key"

SEP = "\x1f"


def flatten(obj: Any, prefix: str = "", sep: str = SEP) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                key = str(key)
            if sep in key:
                raise ValueError(FLATTEN_SEPARATOR_IN_KEY)
            next_prefix = f"{prefix}{sep}{key}" if prefix else key
            for inner_k, inner_v in flatten(value, next_prefix, sep).items():
                if inner_k in out:
                    raise ValueError(DUPLICATE_OUTPUT)
                out[inner_k] = inner_v
        return out
    if not prefix:
        return {}
    return {prefix: obj}
