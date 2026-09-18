"""Fixture equivalent of corpus common.tier_of (C7 + boiler/simp)."""

def _get(w, k, default=None):
    if isinstance(w, dict):
        return w.get(k, default)
    if hasattr(w, "keys"):
        try:
            if k in w.keys():
                return w[k]
        except Exception:
            pass
    return getattr(w, k, default)


def tier_of(w):
    lang = _get(w, "lang")
    try:
        flag_sing = int(_get(w, "flag_sing") or 0)
    except (TypeError, ValueError):
        flag_sing = 0
    try:
        cps = float(_get(w, "chars_per_sec") or 0.0)
    except (TypeError, ValueError):
        cps = 0.0
    cov = _get(w, "coverage")
    try:
        coverage = float(cov) if cov is not None else 1.0
    except (TypeError, ValueError):
        coverage = 1.0
    ir = _get(w, "in_range")
    try:
        in_range = int(ir) if ir is not None else 1
    except (TypeError, ValueError):
        in_range = 1
    if lang != "yue" or flag_sing == 1 or cps > 8 or coverage < 0.2 or in_range == 0:
        return "C"
    try:
        boiler = int(_get(w, "flag_boiler") or 0)
    except (TypeError, ValueError):
        boiler = 0
    try:
        simp = int(_get(w, "flag_simp") or 0)
    except (TypeError, ValueError):
        simp = 0
    if boiler or simp:
        return "B"
    return "A"
