#!/usr/bin/env python3
"""CantoAI CER evaluator v1.0.0: standard library only; no model/data fetching."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import unicodedata

VERSION = "1.0.0"
SCHEMA = "cantoai-evaluation-v1"
UNCERTAINTY_MARKERS = ("[听不清]", "[聽不清]", "[聽唔清]")
RAW_POLICY = {"version": "nfc-lineendings-codepoints-v1", "unicode_version": unicodedata.unidata_version,
              "unicode": "NFC", "line_endings": "CRLF and bare CR become LF",
              "unit": "Unicode code point", "casefold": False, "opencc": False,
              "whitespace_removal": False, "punctuation_removal": False}
SECONDARY_POLICY = {**RAW_POLICY, "version": "nfc-unicode-punctuation-whitespace-v1",
                    "whitespace_removal": "str.isspace()", "punctuation_removal": "Unicode category starts with P"}


class EvaluationError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise EvaluationError(message)


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_sha():
    return sha(Path(__file__).read_bytes())


def unique_object(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, f"duplicate JSON key: {k}")
        result[k] = v
    return result


def decode(data, label):
    try:
        return json.loads(data, object_pairs_hook=unique_object,
                          parse_constant=lambda x: (_ for _ in ()).throw(EvaluationError(f"invalid number: {x}")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"invalid UTF-8 JSON in {label}: {exc}") from exc


def read_file(path):
    path = Path(path)
    data = path.read_bytes()
    return data, {"name": path.name, "sha256": sha(data), "bytes": len(data)}


def read_json(path):
    data, meta = read_file(path)
    return decode(data, path), meta


def read_jsonl(path):
    data, meta = read_file(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationError(f"invalid UTF-8 in {path}") from exc
    rows = []
    # JSONL physical lines are LF-delimited; Unicode U+2028 can occur in JSON text.
    for n, line in enumerate(text.split("\n"), 1):
        if line.strip():
            row = decode(line, f"{path}:{n}")
            require(isinstance(row, dict), f"{path}:{n} must be an object")
            rows.append(row)
    require(rows, f"empty JSONL: {path}")
    return rows, meta


def keys(obj, required, optional=()):
    require(isinstance(obj, dict), "expected JSON object")
    require(set(required) <= set(obj), f"missing fields: {sorted(set(required) - set(obj))}")
    require(set(obj) <= set(required) | set(optional), f"unknown fields: {sorted(set(obj) - set(required) - set(optional))}")


def string(value, label, empty=False):
    require(isinstance(value, str) and (empty or bool(value.strip())), f"{label} must be a string" + ("" if empty else " with non-whitespace content"))
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), f"{label} contains an unpaired surrogate")
    return value


def unique_strings(value, label, nonempty=True):
    require(isinstance(value, list) and (value or not nonempty), f"{label} must be a list" + (" with at least one item" if nonempty else ""))
    for x in value:
        string(x, label)
    require(len(value) == len(set(value)), f"duplicate {label}")
    return value


def validate_config(config):
    keys(config, ("schema_version", "split", "systems", "baseline", "oracle_candidates", "secondary_filter", "bootstrap"))
    require(config["schema_version"] == SCHEMA, "unsupported configuration schema")
    require(config["split"] in ("dev", "test"), "split must be dev or test")
    systems = unique_strings(config["systems"], "systems")
    require(config["baseline"] in systems, "baseline must be a configured system")
    candidates = unique_strings(config["oracle_candidates"], "oracle_candidates", nonempty=False)
    require(set(candidates) <= set(systems), "oracle candidates must be configured systems")
    require(config["secondary_filter"] in ("off", "unicode-punctuation-whitespace-v1"), "unsupported secondary_filter")
    b = config["bootstrap"]
    keys(b, ("iterations", "seed"))
    require(type(b["iterations"]) is int and b["iterations"] in (0, 1000), "bootstrap iterations must be 0 or 1000")
    require(type(b["seed"]) is int, "bootstrap seed must be an integer")
    return config


def validate_reservation(reservation):
    keys(reservation, ("schema_version", "utterance_ids", "source_groups", "declaration"))
    require(reservation["schema_version"] == "cantoai-dev-reservation-v1", "unsupported dev reservation schema")
    unique_strings(reservation["utterance_ids"], "reserved utterance_ids")
    unique_strings(reservation["source_groups"], "reserved source_groups")
    string(reservation["declaration"], "dev reservation declaration")
    return reservation


def policy_hashes(config):
    result = {"raw": sha(canonical(RAW_POLICY))}
    if config["secondary_filter"] != "off":
        result["secondary"] = sha(canonical(SECONDARY_POLICY))
    return result


def normalize(text, secondary=False):
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if secondary:
        text = "".join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith("P"))
    return text


def edit_counts(reference, hypothesis):
    """Exact Levenshtein; traceback tie order: match, substitution, deletion, insertion."""
    n, m = len(reference), len(hypothesis)
    d = [list(range(m + 1))]
    for i, r in enumerate(reference, 1):
        row = [i]
        for j, h in enumerate(hypothesis, 1):
            row.append(min(d[i - 1][j - 1] + (r != h), d[i - 1][j] + 1, row[j - 1] + 1))
        d.append(row)
    i, j = n, m
    s = de = ins = 0
    while i or j:
        if i and j and reference[i - 1] == hypothesis[j - 1] and d[i][j] == d[i - 1][j - 1]:
            i -= 1; j -= 1
        elif i and j and d[i][j] == d[i - 1][j - 1] + 1:
            s += 1; i -= 1; j -= 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            de += 1; i -= 1
        else:
            ins += 1; j -= 1
    return {"N": n, "S": s, "D": de, "I": ins, "E": s + de + ins}


def total(rows):
    counts = {key: sum(r[key] for r in rows) for key in ("N", "S", "D", "I", "E")}
    counts["CER"] = counts["E"] / counts["N"] if counts["N"] else None
    return counts


def paired(base, other, original_base, original_other, normalized_base, normalized_other):
    require(len(base) == len(other), "internal pairing length mismatch")
    n = sum(r["N"] for r in base)
    deltas = [o["E"] - b["E"] for b, o in zip(base, other)]
    changed_exact = [i for i in range(len(base)) if original_base[i] != original_other[i]]
    changed = [i for i in range(len(base)) if normalized_base[i] != normalized_other[i]]
    changed_n = sum(base[i]["N"] for i in changed)
    fixed = sum(-x for x in deltas if x < 0)
    introduced = sum(x for x in deltas if x > 0)
    return {"delta_E_system_minus_baseline": sum(deltas), "delta_CER_system_minus_baseline": sum(deltas) / n,
            "delta_CER_percentage_points": 100 * sum(deltas) / n,
            "improved_utterances": sum(x < 0 for x in deltas), "worsened_utterances": sum(x > 0 for x in deltas),
            "equal_error_utterances": sum(x == 0 for x in deltas),
            "fixed_errors_by_utterance_total": fixed, "introduced_errors_by_utterance_total": introduced,
            "net_fixed_minus_introduced": fixed - introduced,
            "error_change_definition": "Reductions/increases in each utterance's minimum edit distance, not tracked character-level repairs.",
            "changed_text_coverage": {"scored_utterances": len(base), "exact_text_changed": len(changed_exact),
                                      "normalized_text_changed": len(changed), "utterance_fraction": len(changed) / len(base),
                                      "reference_characters": changed_n, "reference_character_fraction": changed_n / n,
                                      "baseline_on_changed": total([base[i] for i in changed]),
                                      "system_on_changed": total([other[i] for i in changed])}}


def quantile(values, p):
    values = sorted(values)
    x = (len(values) - 1) * p
    a = int(x)
    return values[a] + (values[min(a + 1, len(values) - 1)] - values[a]) * (x - a)


def bootstrap(rows_by_system, groups, baseline, iterations, seed):
    """Paired source-group resampling. Every system gets identical group draws."""
    names = list(rows_by_system)
    grouped = {name: defaultdict(lambda: [0, 0]) for name in names}
    for name in names:
        for group, row in zip(groups, rows_by_system[name]):
            grouped[name][group][0] += row["E"]
            grouped[name][group][1] += row["N"]
    clusters = sorted(set(groups))
    warnings = ["Exploratory pilot CI; source_group resampling does not establish speaker independence or population representativeness."]
    if len(clusters) < 20:
        warnings.append("Fewer than 20 source groups: confidence intervals can be unstable and should not support confirmatory claims.")
    out = {"unit": "source_group", "n_clusters": len(clusters), "requested_iterations": iterations,
           "seed": seed, "method": "paired percentile 95%; linear interpolation", "warnings": warnings,
           "valid_iterations": 0, "zero_denominator_iterations": 0, "systems": {}}
    if len(clusters) < 2:
        out["warnings"].append("Fewer than 2 source groups: no confidence interval computed.")
        return out
    rng = random.Random(seed)
    values = {name: {"CER": [], "delta_CER_system_minus_baseline": []} for name in names}
    for _ in range(iterations):
        draw = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        den = sum(grouped[baseline][g][1] for g in draw)
        if not den:
            out["zero_denominator_iterations"] += 1
            continue
        baseline_rate = sum(grouped[baseline][g][0] for g in draw) / den
        for name in names:
            rate = sum(grouped[name][g][0] for g in draw) / den
            values[name]["CER"].append(rate)
            values[name]["delta_CER_system_minus_baseline"].append(rate - baseline_rate)
        out["valid_iterations"] += 1
    if out["zero_denominator_iterations"]:
        out["warnings"].append("Zero-reference-character draws omitted without replacement draws; intervals are conditional on positive denominators.")
    for name in names:
        out["systems"][name] = {metric + "_95CI": [quantile(v, .025), quantile(v, .975)] if v else None for metric, v in values[name].items()}
    return out


def create_freeze(config_path, reservation_path, output, declaration):
    require(declaration, "freeze requires --declare-before-test-exposure")
    config, cmeta = read_json(config_path)
    validate_config(config)
    require(config["split"] == "test", "freeze is only for the test split")
    reservation, rmeta = read_json(reservation_path)
    validate_reservation(reservation)
    payload = {"schema_version": "cantoai-test-freeze-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
               "declaration": "Operator declares this configuration was frozen before exposure to test predictions or scores.",
               "declaration_is_not_independently_verified": True, "config": config,
               "config_sha256": sha(canonical(config)), "config_file_sha256": cmeta["sha256"],
               "source_sha256": source_sha(), "dev_reservation_sha256": rmeta["sha256"],
               "policy_hashes": policy_hashes(config), "harness_version": VERSION}
    with Path(output).open("x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    return payload


def evaluate(gold_path, predictions_path, metadata_path, config_path, out_dir,
             exclusions_path=None, reservation_path=None, freeze_path=None, synthetic=False):
    """Reads explicit inputs only. No writing until all validation and scoring pass."""
    out = Path(out_dir)
    require(not out.exists(), f"output directory already exists: {out}")
    config, cm = read_json(config_path)
    validate_config(config)
    gold_rows, gm = read_jsonl(gold_path)
    pred_rows, pm = read_jsonl(predictions_path)
    metadata, mm = read_json(metadata_path)
    inputs = {"gold": gm, "predictions": pm, "metadata": mm, "config": cm}
    keys(metadata, ("schema_version", "annotation_version", "reference_origin", "origin_declaration", "gold_sha256"))
    require(metadata["schema_version"] == "cantoai-gold-metadata-v1", "unsupported gold metadata schema")
    string(metadata["annotation_version"], "annotation_version")
    string(metadata["origin_declaration"], "origin_declaration")
    require(metadata["gold_sha256"] == gm["sha256"], "gold checksum mismatch")
    expected_origin = "synthetic_fixture_not_human" if synthetic else "human_verified"
    require(metadata["reference_origin"] == expected_origin, f"reference_origin must explicitly be {expected_origin}; never inferred")
    reservation = None
    if reservation_path:
        reservation, rm = read_json(reservation_path)
        validate_reservation(reservation)
        inputs["dev_reservation"] = rm
    if config["split"] == "test":
        require(reservation is not None, "test requires --dev-reservation")
        require(freeze_path is not None, "test requires --freeze")
        frozen, fm = read_json(freeze_path)
        inputs["freeze"] = fm
        require(isinstance(frozen, dict), "freeze must be an object")
        require(frozen.get("schema_version") == "cantoai-test-freeze-v1", "invalid freeze schema")
        require(frozen.get("config_sha256") == sha(canonical(config)) and frozen.get("config") == config, "test config changed after freeze")
        require(frozen.get("source_sha256") == source_sha(), "evaluator source changed after freeze")
        require(frozen.get("dev_reservation_sha256") == inputs["dev_reservation"]["sha256"], "dev reservation changed after freeze")
        require(frozen.get("policy_hashes") == policy_hashes(config), "normalization policy changed after freeze")
        require(frozen.get("declaration") == "Operator declares this configuration was frozen before exposure to test predictions or scores.", "missing pre-test-exposure freeze declaration")
    else:
        require(freeze_path is None, "do not provide test freeze for a dev run")
    gold = {}
    for row in gold_rows:
        keys(row, ("utterance_id", "source_group", "reference", "reference_status", "split", "annotation_version"))
        uid = string(row["utterance_id"], "utterance_id")
        require(uid not in gold, f"duplicate gold utterance_id: {uid}")
        string(row["source_group"], "source_group")
        string(row["reference"], "reference", empty=True)
        require(row["annotation_version"] == metadata["annotation_version"], f"annotation version mismatch: {uid}")
        require(row["split"] == config["split"], f"gold split mismatch: {uid}; one split per run")
        require(row["reference_status"] != "pending", f"pending reference rejected: {uid}")
        allowed_status = "synthetic_fixture" if synthetic else "human_verified"
        require(row["reference_status"] in (allowed_status, "unscorable"), f"invalid reference_status for this mode: {uid}")
        if row["reference_status"] != "unscorable":
            require(not any(marker in row["reference"] for marker in UNCERTAINTY_MARKERS), f"uncertainty marker in scorable reference: {uid}; explicitly mark unscorable")
        if config["split"] == "test":
            require(uid not in reservation["utterance_ids"], f"dev/test utterance overlap: {uid}")
            require(row["source_group"] not in reservation["source_groups"], f"dev/test source_group overlap: {row['source_group']}")
        elif reservation is not None:
            require(uid in reservation["utterance_ids"], f"dev utterance absent from reservation: {uid}")
            require(row["source_group"] in reservation["source_groups"], f"dev source_group absent from reservation: {row['source_group']}")
        gold[uid] = row
    exclusion = {"schema_version": "cantoai-exclusions-v1", "excluded": []}
    if exclusions_path:
        exclusion, em = read_json(exclusions_path)
        inputs["exclusions"] = em
        keys(exclusion, ("schema_version", "excluded"))
        require(exclusion["schema_version"] == "cantoai-exclusions-v1", "unsupported exclusions schema")
        require(isinstance(exclusion["excluded"], list), "excluded must be a list")
    excluded = {}
    for item in exclusion["excluded"]:
        keys(item, ("utterance_id", "reason"))
        uid = string(item["utterance_id"], "exclusion utterance_id")
        string(item["reason"], "exclusion reason")
        require(uid not in excluded, f"duplicate exclusion: {uid}")
        excluded[uid] = item["reason"]
    unscorable = {u for u, row in gold.items() if row["reference_status"] == "unscorable"}
    require(set(excluded) == unscorable, "exclusions must exactly match unscorable IDs; no exclusions of verified/pending/unknown IDs")
    pred = {system: {} for system in config["systems"]}
    for row in pred_rows:
        keys(row, ("utterance_id", "system", "text"))
        uid = string(row["utterance_id"], "prediction utterance_id")
        system = string(row["system"], "prediction system")
        require(system in pred, f"unexpected system: {system}")
        require(uid not in pred[system], f"duplicate prediction pair: {system}/{uid}")
        pred[system][uid] = string(row["text"], "prediction text", empty=True)
    for system in config["systems"]:
        missing, extra = set(gold) - set(pred[system]), set(pred[system]) - set(gold)
        require(not missing and not extra, f"UID coverage mismatch for {system}: missing={sorted(missing)}, extra={sorted(extra)}; missing is not an empty hypothesis")
    ids = sorted(set(gold) - set(excluded))
    require(ids, "no scorable utterances remain")
    report = {"schema_version": SCHEMA, "harness_version": VERSION,
              "run_kind": "SYNTHETIC FIXTURE ONLY - NO EMPIRICAL RESULT" if synthetic else "human_gold_evaluation",
              "provenance_limit": "Human status is an explicit operator declaration, not independently verified by software.",
              "coverage": {"gold_utterances": len(gold), "scored_utterances": len(ids), "excluded_utterances": len(excluded),
                           "scored_utterance_fraction": len(ids) / len(gold),
                           "all_systems_exact_full_gold_UID_coverage": True,
                           "prediction_counts": {s: len(pred[s]) for s in pred},
                           "excluded": [{"utterance_id": u, "source_group": gold[u]["source_group"], "reason": excluded[u]} for u in sorted(excluded)],
                           "by_source_group": {}},
              "notes": ["CER is aggregate (S+D+I)/aggregate reference characters; not mean utterance CER; can exceed 1.",
                        "Empty reference rows contribute insertions; an aggregate denominator of zero is an error.",
                        "No traditional/simplified conversion, Cantonese spelling mapping, casefolding, English removal, or digit removal.",
                        "Excluded utterances still require explicit predictions for every system; excluded text is never scored."],
              "metrics": {}}
    for group in sorted({row["source_group"] for row in gold.values()}):
        all_group = [u for u in gold if gold[u]["source_group"] == group]
        report["coverage"]["by_source_group"][group] = {"total": len(all_group), "scored": sum(u not in excluded for u in all_group), "excluded": sum(u in excluded for u in all_group)}
    per_utterance = []
    for metric in (["raw", "secondary"] if config["secondary_filter"] != "off" else ["raw"]):
        secondary = metric == "secondary"
        refs = [normalize(gold[u]["reference"], secondary) for u in ids]
        require(sum(map(len, refs)) > 0, f"aggregate reference denominator N=0 for {metric}")
        texts = {s: [pred[s][u] for u in ids] for s in config["systems"]}
        norm = {s: [normalize(t, secondary) for t in texts[s]] for s in texts}
        rows = {s: [edit_counts(r, h) for r, h in zip(refs, norm[s])] for s in norm}
        for s in rows:
            for i, u in enumerate(ids):
                row = rows[s][i]
                per_utterance.append({"metric": metric, "system": s, "utterance_id": u,
                                      "source_group": gold[u]["source_group"], **row,
                                      "CER": row["E"] / row["N"] if row["N"] else None})
        base = config["baseline"]
        result = {"policy": SECONDARY_POLICY if secondary else RAW_POLICY,
                  "policy_sha256": policy_hashes(config)[metric], "systems": {s: total(rows[s]) for s in rows},
                  "baseline": base, "paired_to_baseline": {s: paired(rows[base], rows[s], texts[base], texts[s], norm[base], norm[s]) for s in rows}}
        if config["oracle_candidates"]:
            candidates = config["oracle_candidates"]
            # min preserves configured candidate order on ties. No outside candidates.
            selected = [min(candidates, key=lambda s: rows[s][i]["E"]) for i in range(len(ids))]
            oracle_rows = [rows[s][i] for i, s in enumerate(selected)]
            result["same_candidate_oracle"] = {"label": "NON-DEPLOYABLE DIAGNOSTIC: selects using gold reference",
                                               "candidate_order_and_tie_break": candidates, "aggregate": total(oracle_rows),
                                               "selected_counts": dict(Counter(selected)),
                                               "selections": [{"utterance_id": u, "system": s} for u, s in zip(ids, selected)],
                                               "delta_CER_oracle_minus_baseline": total(oracle_rows)["CER"] - total(rows[base])["CER"]}
        if config["bootstrap"]["iterations"]:
            result["source_group_bootstrap"] = bootstrap(rows, [gold[u]["source_group"] for u in ids], base, **config["bootstrap"])
        report["metrics"][metric] = result
    manifest = {"schema_version": "cantoai-run-manifest-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "harness_version": VERSION, "source_sha256": source_sha(), "python_version": platform.python_version(),
                "unicode_version": unicodedata.unidata_version, "input_files": inputs,
                "config_canonical_sha256": sha(canonical(config)), "normalization_policy_hashes": policy_hashes(config),
                "synthetic_mode": synthetic, "split": config["split"],
                "freeze_verified": config["split"] == "test", "freeze_timing_is_operator_attestation_only": True,
                "input_access": "Read-only. No transcript text included in outputs. No network operations."}
    out.mkdir(parents=True, exist_ok=False)
    def write_json(name, obj):
        with (out / name).open("x", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
    write_json("report.json", report)
    write_json("config.json", config)
    write_json("gold_metadata.json", metadata)
    write_json("exclusions.json", exclusion)
    if reservation is not None:
        write_json("dev_reservation.json", reservation)
    if freeze_path:
        write_json("test_freeze.json", frozen)
    with (out / "per_utterance.jsonl").open("x", encoding="utf-8") as f:
        for row in per_utterance:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    with (out / "evaluator_source.py").open("xb") as f:
        f.write(Path(__file__).read_bytes())
    manifest["output_files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    # manifest intentionally does not contain a self-referential checksum.
    write_json("manifest.json", manifest)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=VERSION)
    commands = p.add_subparsers(dest="command", required=True)
    f = commands.add_parser("freeze", help="Freeze test settings before test exposure; reads no gold or predictions")
    f.add_argument("--config", required=True)
    f.add_argument("--dev-reservation", required=True)
    f.add_argument("--output", required=True)
    f.add_argument("--declare-before-test-exposure", action="store_true")
    r = commands.add_parser("run", help="Evaluate explicit local inputs")
    for arg in ("gold", "predictions", "metadata", "config", "out"):
        r.add_argument("--" + arg, required=True)
    for arg in ("exclusions", "dev-reservation", "freeze"):
        r.add_argument("--" + arg)
    r.add_argument("--synthetic", action="store_true", help="Synthetic fixtures only; never a human-gold run")
    args = p.parse_args(argv)
    try:
        if args.command == "freeze":
            create_freeze(args.config, args.dev_reservation, args.output, args.declare_before_test_exposure)
            print("Test configuration frozen. Timing is an operator attestation, not independently verified.")
        else:
            report = evaluate(args.gold, args.predictions, args.metadata, args.config, args.out,
                              args.exclusions, args.dev_reservation, args.freeze, args.synthetic)
            print(report["run_kind"])
            print(f"Wrote validated evaluation to {args.out}")
        return 0
    except (EvaluationError, OSError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
