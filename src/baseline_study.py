"""Development-first comparison followed by a separately sealed confirmation."""

import argparse
import json
from pathlib import Path

try:
    from .confirmation import digest
    from .evidence import load_registry
    from .independent_confirmation import summarize_with_misses
    from .retrieval_baselines import METHODS
except ImportError:
    from confirmation import digest
    from evidence import load_registry
    from independent_confirmation import summarize_with_misses
    from retrieval_baselines import METHODS

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = "experiments/AI06-development.json"
DEV_RESULT = "results/AI06-development.json"
FREEZE = "experiments/AI06-freeze.json"
QUESTIONS = "experiments/AI06-questions.json"
SEAL = "experiments/AI06-seal.json"
SELECTION_RULE = "Maximize development source recall@1, then recall@3, then minimize false support count; ties prefer bm25, tfidf, keyword_overlap in that order."


def evaluate(questions, registry):
    methods = {}
    for name, retriever in METHODS.items():
        rows = []
        for q in questions:
            hits = retriever(q["question"], registry, 3)
            ids = [h["id"] for h in hits]
            ranks = [i + 1 for i, source in enumerate(ids) if source in q["expected_sources"]]
            rows.append({**q, "retrieved_ids": ids,
                         "scores": [round(h["score"], 10) for h in hits],
                         "first_expected_rank": min(ranks) if ranks else None,
                         "outcome": (("source_found" if ranks else "wrong_source" if ids else "empty_miss")
                                     if q["expected_sources"] else
                                     ("false_support" if ids else "empty_unsupported"))})
        methods[name] = {"summary": summarize_with_misses(rows), "rows": rows}
    return methods


def select_method(methods):
    def key(name):
        s = methods[name]["summary"]
        return (-s["source_recall"]["1"]["hits"], -s["source_recall"]["3"]["hits"],
                s["false_support"]["count"], list(METHODS).index(name))
    return min(methods, key=key)


def development(root=ROOT):
    root = Path(root)
    registry = load_registry(root / "docs/registry.json")
    questions = json.loads((root / DEVELOPMENT).read_text(encoding="utf-8"))["questions"]
    methods = evaluate(questions, registry)
    return {"phase": "development", "registry_sha256": digest(root / "docs/registry.json"),
            "questions_sha256": digest(root / DEVELOPMENT), "selection_rule": SELECTION_RULE,
            "selected_method": select_method(methods), "question_count": len(questions), "methods": methods}


def validate_freeze(root=ROOT):
    root = Path(root)
    seal = json.loads((root / SEAL).read_text(encoding="utf-8"))
    for name in (FREEZE, QUESTIONS):
        if digest(root / name) != seal[name]:
            raise ValueError(f"Sealed input changed: {name}")
    manifest = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    required = {"docs/registry.json", "src/evidence.py", "src/confirmation.py",
                "src/independent_confirmation.py", "src/retrieval_baselines.py",
                "src/baseline_study.py", DEVELOPMENT, DEV_RESULT,
                "experiments/AI01-questions.json", "experiments/AI04-questions.json"}
    if set(manifest["files"]) != required:
        raise ValueError("Frozen input coverage changed")
    for name, expected in manifest["files"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    dev = development(root)
    saved = json.loads((root / DEV_RESULT).read_text(encoding="utf-8"))
    if dev != saved or manifest["selected_method"] != dev["selected_method"]:
        raise ValueError("Development result or selection does not reproduce")
    return manifest, load_registry(root / "docs/registry.json"), dev


def validate_questions(fixture, manifest, registry, prior):
    questions = fixture["questions"]
    if fixture["protocol_id"] != manifest["protocol_id"]:
        raise ValueError("Question protocol mismatch")
    texts = [q["question"].strip().casefold() for q in questions]
    if (len(set(texts)) != len(texts) or set(texts) & prior
            or len({q["id"] for q in questions}) != len(questions)):
        raise ValueError("Duplicate or reused confirmation question")
    documents = {d["id"]: d for d in registry["documents"]}
    counts = dict.fromkeys(manifest["question_plan"], 0)
    for q in questions:
        sources = q["expected_sources"]
        if (q["stratum"] not in counts or not q["question"].strip() or not q["rationale"].strip()
                or len(set(sources)) != len(sources) or not set(sources) <= documents.keys()
                or bool(sources) != (q["stratum"] == "answerable")):
            raise ValueError("Invalid source label or stratum")
        if set(q["anchors"]) != set(sources) or any(
                not q["anchors"][s] or q["anchors"][s] not in documents[s]["text"] for s in sources):
            raise ValueError("Invalid source anchor")
        counts[q["stratum"]] += 1
    if counts != manifest["question_plan"]:
        raise ValueError("Question strata differ from frozen plan")
    if any(sum(s in q["expected_sources"] for q in questions) != 1 for s in documents):
        raise ValueError("Each source needs one confirmation question")
    return questions


def experiment(root=ROOT):
    root = Path(root)
    manifest, registry, dev = validate_freeze(root)
    prior = set()
    for name in (DEVELOPMENT, "experiments/AI01-questions.json", "experiments/AI04-questions.json"):
        fixture = json.loads((root / name).read_text(encoding="utf-8"))
        prior.update(q["question"].strip().casefold() for q in fixture["questions"])
    fixture = json.loads((root / QUESTIONS).read_text(encoding="utf-8"))
    questions = validate_questions(fixture, manifest, registry, prior)
    return {"protocol_id": manifest["protocol_id"], "question": manifest["question"],
            "freeze_sha256": digest(root / FREEZE), "questions_sha256": digest(root / QUESTIONS),
            "frozen_files": manifest["files"], "rules": manifest["rules"],
            "selected_method": dev["selected_method"], "selection_rule": SELECTION_RULE,
            "development": dev,
            "confirmation": {"phase": "confirmation", "question_count": len(questions),
                             "methods": evaluate(questions, registry)},
            "limitations": manifest["limitations"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true", help="Evaluate development only; never read confirmation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = development() if args.development else experiment()
    target = args.output or ROOT / (DEV_RESULT if args.development else "results/AI06-baselines.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"selected_method": result["selected_method"],
                      "summaries": {n: d["summary"] for n, d in
                                    (result["methods"] if args.development else result["confirmation"]["methods"]).items()}}, indent=2))


if __name__ == "__main__":
    main()
