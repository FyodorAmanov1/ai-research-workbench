"""Measure exact lookup and lexical retrieval on explicit selector fixtures."""
import argparse
import json
from pathlib import Path

try:
    from .structured_query import QueryTool, ROOT, sha256
    from .evidence import retrieve
except ImportError:
    from structured_query import QueryTool, ROOT, sha256
    from evidence import retrieve


def experiment():
    raw = (ROOT / "docs/registry.json").read_bytes()
    fixture_raw = (ROOT / "experiments/AI05-queries.json").read_bytes()
    tool, registry = QueryTool(raw), json.loads(raw)
    rows = []
    for probe in json.loads(fixture_raw)["probes"]:
        result = tool.execute(probe["query"])
        correct = result["code"] == probe["expected_code"]
        if "expected_value" in probe:
            correct = correct and len(result.get("data", [])) == 1 and result["data"][0]["value"] == probe["expected_value"]
        if "expected_count" in probe:
            correct = correct and len(result.get("data", [])) == probe["expected_count"]
        baseline = retrieve(probe["baseline"], registry, 3)
        rows.append({**probe, "result": result, "matches_specification": correct,
                     "bm25_source_ids": [d["id"] for d in baseline]})
    known = [r for r in rows if r["expected_code"] == "ok"]
    unknown = [r for r in rows if r["expected_code"] != "ok"]
    return {"question": "Can exact selectors return saved metrics, preserve zero and negative findings, and distinguish absent measurements from related records?",
            "registry_sha256": sha256(raw), "fixtures_sha256": sha256(fixture_raw),
            "summary": {"probes": len(rows), "matching_specification": sum(r["matches_specification"] for r in rows),
                        "known_requests": len(known), "known_requests_correct": sum(r["matches_specification"] for r in known),
                        "unknown_requests": len(unknown), "explicit_unknown_errors": sum(r["result"]["code"].startswith("unknown_") for r in unknown),
                        "unknown_values_returned": sum("data" in r["result"] for r in unknown),
                        "bm25_nonempty_on_unknown": sum(bool(r["bm25_source_ids"]) for r in unknown),
                        "bm25_empty_on_unknown": sum(not r["bm25_source_ids"] for r in unknown)},
            "rows": rows,
            "limitations": ["Twelve source-aware authored regression probes; no independent user sample, natural-language parsing or population accuracy estimate.",
                            "Exact selectors require known identities and labels. BM25 receives authored lexical renderings, returns related records and does not promise typed answers; nonempty unsupported retrieval is a risk proxy, not generated falsehood.",
                            "Saved synthetic studies only. Unknown means absent from this snapshot, not absent everywhere. Registry and record hashes detect drift; original artifact hashes are inherited, not authenticated or verified against remote bytes.",
                            "No model, API, latency, infrastructure cost or scientific superiority is measured. Exact lookup does not establish scientific validity or comparison compatibility."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/AI05-queries.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(experiment(), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
