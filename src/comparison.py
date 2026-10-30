"""Conservative comparison of registered metrics under reviewed evidence contracts."""

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from .evidence import load_registry
except ImportError:
    from evidence import load_registry

ROOT = Path(__file__).resolve().parents[1]


def load_inputs(root=ROOT):
    root = Path(root)
    contracts = json.loads((root / "docs/comparison-contracts.json").read_text(encoding="utf-8"))
    path = root / "docs/registry.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != contracts["registry_sha256"]:
        raise ValueError("Comparison registry fingerprint mismatch; review contracts before reuse")
    return load_registry(path), contracts


def compare_metrics(registry, contracts, left_source, left_metric, right_source, right_metric):
    """Return left minus right only after exact compatibility checks; never convert units.

    Contracts describe evaluation conditions, not identical model training algorithms.
    Empty unit strings require an explicit reviewed quantity ID. Missing metadata fails closed.
    """
    def reject(code, reason):
        return {"accepted": False, "code": code, "reason": reason}

    resolved = []
    for side, source, label in (("Left", left_source, left_metric), ("Right", right_source, right_metric)):
        documents = [d for d in registry["documents"] if d["id"] == source]
        if len(documents) != 1:
            return reject("unknown_source" if not documents else "ambiguous_source", f"{side}: source ID must identify exactly one record")
        document = documents[0]
        metrics = [m for m in document.get("metrics", []) if m["label"] == label]
        if len(metrics) != 1:
            return reject("unknown_metric" if not metrics else "ambiguous_metric", f"{side}: metric label must identify exactly one registered metric")
        item = metrics[0]
        value = item.get("value")
        if type(value) not in (int, float) or not math.isfinite(value):
            return reject("non_numeric", f"{side}: metric must be a finite number (booleans excluded)")
        if "unit" not in item or not isinstance(item["unit"], str):
            return reject("missing_unit", f"{side}: explicit unit string required")
        resolved.append((document, item))
    if resolved[0][1]["unit"] != resolved[1][1]["unit"]:
        return reject("unit_mismatch", "Unit mismatch: exact strings required; no implicit conversion")
    evidence = []
    for document, item in resolved:
        entries = [c for c in contracts.get("metrics", []) if c.get("source_id") == document["id"] and c.get("label") == item["label"]]
        if len(entries) != 1:
            return reject("missing_metadata", "Exactly one reviewed comparison contract is required for each metric")
        entry = entries[0]
        for field in ("dataset_id", "protocol_id", "quantity_id"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                return reject("missing_metadata", f"Missing comparison metadata: {field}")
        if (entry.get("artifact_sha256") != document.get("artifact_sha256")
                or entry.get("sha256") != document.get("sha256")
                or entry.get("value") != item["value"] or entry.get("unit") != item["unit"]):
            return reject("stale_contract", "Comparison contract does not match the recorded metric and source fingerprints")
        evidence.append({**entry, "url": document["url"]})
    for field, code, name in (("dataset_id", "dataset_mismatch", "Dataset"), ("protocol_id", "protocol_mismatch", "Protocol"), ("quantity_id", "quantity_mismatch", "Quantity")):
        if evidence[0][field] != evidence[1][field]:
            return reject(code, f"{name} mismatch: {evidence[0][field]} versus {evidence[1][field]}")
    difference = resolved[0][1]["value"] - resolved[1][1]["value"]
    if not math.isfinite(difference):
        return reject("non_finite_difference", "Difference exceeds finite numeric range")
    return {"accepted": True, "code": "compatible", "reason": "Units, dataset, evaluation protocol and quantity match",
            "difference": difference, "operation": "left minus right", "unit": evidence[0]["unit"],
            "left": evidence[0], "right": evidence[1]}


def experiment(root=ROOT):
    registry, contracts = load_inputs(root)
    stable = "statistical-learning-lab:stationary"
    shift = "statistical-learning-lab:shift"
    risk = "quantum-estimation-lab:risk-1"
    probes = [
        ("Stable: expanding versus frozen MAE", stable, "Expanding ridge MAE", stable, "Frozen ridge MAE", "compatible"),
        ("Shift: expanding versus frozen MAE", shift, "Expanding ridge MAE", shift, "Frozen ridge MAE", "compatible"),
        ("Cross-regime MAE", stable, "Frozen ridge MAE", shift, "Frozen ridge MAE", "dataset_mismatch"),
        ("Nominal target versus observed coverage", stable, "Nominal interval coverage", stable, "Observed test coverage", "protocol_mismatch"),
        ("MAE versus coverage", stable, "Frozen ridge MAE", stable, "Observed test coverage", "unit_mismatch"),
        ("VaR versus expected shortfall", risk, "99% value at risk", risk, "99% expected shortfall", "quantity_mismatch"),
        ("Unreviewed dimensionless quantities", "quantum-estimation-lab:amplitude", "Logical qubits", "quantum-estimation-lab:amplitude", "Oracle preparation calls", "missing_metadata"),
    ]
    rows = []
    for name, ls, lm, rs, rm, expected in probes:
        result = compare_metrics(registry, contracts, ls, lm, rs, rm)
        left = next(m for d in registry["documents"] if d["id"] == ls for m in d["metrics"] if m["label"] == lm)
        right = next(m for d in registry["documents"] if d["id"] == rs for m in d["metrics"] if m["label"] == rm)
        rows.append({"name": name, "left_source": ls, "left_metric": lm, "right_source": rs, "right_metric": rm,
                     "expected_code": expected, "result": result,
                     "unit_only_baseline_accepted": left["unit"] == right["unit"]})
    return {"question": "Does expanding ridge reduce recorded test MAE against frozen ridge under matching evaluation conditions?",
            "registry_sha256": contracts["registry_sha256"],
            "contracts_sha256": hashlib.sha256((Path(root) / "docs/comparison-contracts.json").read_bytes()).hexdigest(),
            "summary": {"probes": len(rows), "decisions_matching_specification": sum(r["result"]["code"] == r["expected_code"] for r in rows),
                        "accepted": sum(r["result"]["accepted"] for r in rows),
                        "incompatible_accepted": sum(r["result"]["accepted"] and r["expected_code"] != "compatible" for r in rows),
                        "unit_only_incompatible_accepted": sum(r["unit_only_baseline_accepted"] and r["expected_code"] != "compatible" for r in rows)},
            "rows": rows,
            "limitations": ["Authored contract probes, not population accuracy. Curated identities are review assertions over a saved synthetic artifact, not independently verified raw-data hashes.",
                            "Differences describe saved point estimates only; no uncertainty, significance, causal effect or real-market performance is inferred.",
                            "An empty source unit remains empty; quantity IDs disambiguate it without inventing physical units. Unreviewed metrics are rejected."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--left-source")
    parser.add_argument("--left-metric")
    parser.add_argument("--right-source")
    parser.add_argument("--right-metric")
    args = parser.parse_args()
    selection = [args.left_source, args.left_metric, args.right_source, args.right_metric]
    if any(selection) and not all(selection):
        parser.error("A comparison requires both source IDs and both metric labels")
    payload = compare_metrics(*load_inputs(), *selection) if all(selection) else experiment()
    output = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
