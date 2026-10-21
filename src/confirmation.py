"""Evaluate a sealed question set against frozen retrieval, without fitting rules."""

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .evidence import load_registry, retrieve, tokens
except ImportError:
    from evidence import load_registry, retrieve, tokens

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "experiments/AI01-freeze.json"
QUESTIONS = "experiments/AI01-questions.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_freeze(root=ROOT):
    root = Path(root)
    seal = json.loads((root / "experiments/AI01-seal.json").read_text(encoding="utf-8"))
    for name in (FREEZE, QUESTIONS):
        if digest(root / name) != seal[name]:
            raise ValueError(f"Sealed protocol or questions changed: {name}; use a new protocol")
    manifest = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Frozen input changed: {name}; use a new protocol")
    registry = load_registry(root / "docs/registry.json")
    if len(registry["documents"]) != 10 or [d["id"] for d in registry["documents"]] != manifest["source_ids"]:
        raise ValueError("Frozen registry must retain its ten source IDs and order")
    return manifest, registry


def overlap_retrieve(question, registry, k=3):
    """Unweighted unique-term overlap with the frozen BM25 fields and tokenizer."""
    query = set(tokens(question))
    hits = []
    for document in registry["documents"]:
        score = len(query & set(tokens(document["title"] + " " + document["text"])))
        if score > 0:
            hits.append({**document, "score": score})
    return sorted(hits, key=lambda d: (-d["score"], d["id"]))[:k]


def summarize(rows):
    """Keep recall denominators separate from unsupported-query outcomes."""
    answerable = [r for r in rows if r["expected_sources"]]
    unsupported = [r for r in rows if not r["expected_sources"]]
    result = {
        "answerable_count": len(answerable),
        "unanswerable_count": len(unsupported),
        "source_recall": {
            str(k): {
                "hits": sum(bool(set(r["expected_sources"]) & set(r["retrieved_ids"][:k])) for r in answerable),
                "total": len(answerable),
            } for k in (1, 3)
        },
        "false_support": {
            "count": sum(bool(r["retrieved_ids"]) for r in unsupported),
            "total": len(unsupported),
        },
        "empty_retrieval": {
            "answerable": sum(not r["retrieved_ids"] for r in answerable),
            "unanswerable": sum(not r["retrieved_ids"] for r in unsupported),
        },
        "strata": {},
    }
    for value in result["source_recall"].values():
        value["rate"] = value["hits"] / value["total"] if value["total"] else None
    value = result["false_support"]
    value["rate"] = value["count"] / value["total"] if value["total"] else None
    for stratum in ("answerable", "unanswerable", "misleading_overlap"):
        subset = [r for r in rows if r["stratum"] == stratum]
        result["strata"][stratum] = {
            "count": len(subset),
            "retrieved": sum(bool(r["retrieved_ids"]) for r in subset),
            "empty": sum(not r["retrieved_ids"] for r in subset),
        }
    return result


def experiment(root=ROOT):
    root = Path(root)
    manifest, registry = validate_freeze(root)
    fixture = json.loads((root / QUESTIONS).read_text(encoding="utf-8"))
    questions = fixture["questions"]
    known = set(manifest["source_ids"])
    if fixture["protocol_id"] != manifest["protocol_id"] or len(questions) < 20:
        raise ValueError("Confirmation questions do not match the frozen protocol")
    if len({q["id"] for q in questions}) != len(questions) or len({q["question"] for q in questions}) != len(questions):
        raise ValueError("Duplicate confirmation question")
    for q in questions:
        if not q["question"].strip() or not q["rationale"] or not set(q["expected_sources"]) <= known:
            raise ValueError("Invalid confirmation label")
        if q["stratum"] not in manifest["evaluation"]["strata"] or bool(q["expected_sources"]) != (q["stratum"] == "answerable"):
            raise ValueError("Question stratum contradicts source label")
    methods = {}
    for name, retriever in (("bm25", retrieve), ("term_overlap", overlap_retrieve)):
        rows = []
        for q in questions:
            hits = retriever(q["question"], registry, 3)
            ids = [h["id"] for h in hits]
            rows.append({**q, "retrieved_ids": ids,
                         "outcome": ("source_found" if set(ids) & set(q["expected_sources"]) else "source_missed")
                         if q["expected_sources"] else ("false_support" if ids else "empty_retrieval")})
        methods[name] = {"summary": summarize(rows), "rows": rows}
    return {
        "protocol_id": manifest["protocol_id"],
        "freeze_sha256": digest(root / FREEZE),
        "questions_sha256": digest(root / QUESTIONS),
        "frozen_files": manifest["files"],
        "question_count": len(questions),
        "definitions": manifest["evaluation"],
        "methods": methods,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/AI01-confirmation.json")
    args = parser.parse_args()
    result = experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({name: data["summary"] for name, data in result["methods"].items()}, indent=2))
