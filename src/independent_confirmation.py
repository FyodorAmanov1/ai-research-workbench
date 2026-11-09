"""Second sealed confirmation wave; no retrieval fitting or source refresh."""

import argparse
import json
from pathlib import Path

try:
    from .confirmation import digest, overlap_retrieve, summarize
    from .evidence import load_registry, retrieve
except ImportError:
    from confirmation import digest, overlap_retrieve, summarize
    from evidence import load_registry, retrieve

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "experiments/AI04-freeze.json"
QUESTIONS = "experiments/AI04-questions.json"
SEAL = "experiments/AI04-seal.json"


def validate_freeze(root=ROOT):
    root = Path(root)
    seal = json.loads((root / SEAL).read_text(encoding="utf-8"))
    for name in (FREEZE, QUESTIONS):
        if digest(root / name) != seal[name]:
            raise ValueError(f"Sealed input changed: {name}; use a new protocol")
    manifest = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Frozen input changed: {name}; use a new protocol")
    registry = load_registry(root / "docs/registry.json")
    if [d["id"] for d in registry["documents"]] != manifest["source_ids"]:
        raise ValueError("Frozen source IDs changed")
    return manifest, registry


def summarize_with_misses(rows):
    """Partition each answerable cutoff into hit, wrong source, or empty."""
    result = summarize(rows)
    answerable = [r for r in rows if r["expected_sources"]]
    result["source_misses"] = {}
    for k in (1, 3):
        empty = sum(not r["retrieved_ids"][:k] for r in answerable)
        wrong = sum(bool(r["retrieved_ids"][:k]) and not
                    bool(set(r["expected_sources"]) & set(r["retrieved_ids"][:k]))
                    for r in answerable)
        total = len(answerable)
        result["source_misses"][str(k)] = {
            "count": empty + wrong, "total": total,
            "rate": (empty + wrong) / total if total else None,
            "empty": empty, "wrong_source": wrong,
        }
    return result


def validate_questions(fixture, manifest, registry, prior_questions):
    questions = fixture["questions"]
    if fixture["protocol_id"] != manifest["protocol_id"]:
        raise ValueError("Question protocol mismatch")
    texts = [q["question"].strip().casefold() for q in questions]
    if (len({q["id"] for q in questions}) != len(questions)
            or len(set(texts)) != len(texts) or set(texts) & prior_questions):
        raise ValueError("Duplicate or reused confirmation question")
    documents = {d["id"]: d for d in registry["documents"]}
    counts = {s: 0 for s in manifest["question_plan"]}
    for q in questions:
        stratum = q["stratum"]
        sources = q["expected_sources"]
        if (stratum not in counts or not q["question"].strip() or not q["rationale"].strip()
                or len(sources) != len(set(sources)) or not set(sources) <= documents.keys()
                or bool(sources) != (stratum == "answerable")):
            raise ValueError("Invalid question label or stratum")
        # Anchors make answerable labels inspectable against the frozen evidence.
        if sources and (set(q["anchors"]) != set(sources) or any(
                not q["anchors"][s] or q["anchors"][s] not in documents[s]["text"]
                for s in sources)):
            raise ValueError("Answerable label lacks an exact source anchor")
        counts[stratum] += 1
    if counts != manifest["question_plan"]:
        raise ValueError("Question strata differ from the frozen plan")
    for source in documents:
        if sum(source in q["expected_sources"] for q in questions) != 2:
            raise ValueError("Each frozen source requires two answerable questions")
    return questions


def experiment(root=ROOT):
    root = Path(root)
    manifest, registry = validate_freeze(root)
    fixture = json.loads((root / QUESTIONS).read_text(encoding="utf-8"))
    prior = json.loads((root / "experiments/AI01-questions.json").read_text(encoding="utf-8"))
    questions = validate_questions(fixture, manifest, registry,
                                   {q["question"].strip().casefold() for q in prior["questions"]})
    methods = {}
    for name, retriever in (("bm25", retrieve), ("term_overlap", overlap_retrieve)):
        rows = []
        for q in questions:
            ids = [d["id"] for d in retriever(q["question"], registry, 3)]
            ranks = [i + 1 for i, source in enumerate(ids) if source in q["expected_sources"]]
            outcome = (("source_found" if ranks else "wrong_source" if ids else "empty_miss")
                       if q["expected_sources"] else ("false_support" if ids else "empty_unsupported"))
            rows.append({**q, "retrieved_ids": ids, "first_expected_rank": min(ranks) if ranks else None,
                         "outcome": outcome})
        methods[name] = {"summary": summarize_with_misses(rows), "rows": rows}
    return {
        "protocol_id": manifest["protocol_id"], "freeze_sha256": digest(root / FREEZE),
        "questions_sha256": digest(root / QUESTIONS), "frozen_files": manifest["files"],
        "question_count": len(questions), "definitions": manifest["evaluation"], "methods": methods,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/AI04-confirmation.json")
    args = parser.parse_args()
    result = experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({name: data["summary"] for name, data in result["methods"].items()}, indent=2))
