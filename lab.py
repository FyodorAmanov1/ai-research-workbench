"""A deterministic retrieval baseline; corpus text is data, never instructions."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

CORPUS = [
    {"id": "qae", "title": "Quantum Amplitude Estimation", "url": "https://arxiv.org/abs/quant-ph/0005055",
     "text": "Amplitude estimation uses a quantum oracle to estimate probabilities. Total costs must include state preparation and oracle calls."},
    {"id": "qaoa", "title": "A Quantum Approximate Optimization Algorithm", "url": "https://arxiv.org/abs/1411.4028",
     "text": "QAOA alternates cost and mixer unitaries to optimize a combinatorial objective. Constraint feasibility and classical comparisons matter."},
    {"id": "mc", "title": "Monte Carlo Methods in Financial Engineering", "url": "https://doi.org/10.1007/978-0-387-21617-1",
     "text": "Monte Carlo estimates payoff expectations. Independent samples support standard errors and confidence intervals. Antithetic pairs are correlated."},
    {"id": "ridge", "title": "Ridge Regression: Biased Estimation for Nonorthogonal Problems", "url": "https://doi.org/10.1080/00401706.1970.10488634",
     "text": "Ridge regression regularizes squared loss with a penalty on coefficients. Chronological validation for temporal data avoids future leakage."},
]
CASES = [
    {"question": "How do amplitude estimation oracle and state preparation costs enter the benchmark?", "expected": "qae"},
    {"question": "Why measure QAOA constraint feasibility?", "expected": "qaoa"},
    {"question": "How should Monte Carlo confidence intervals handle antithetic pairs?", "expected": "mc"},
    {"question": "What does ridge regression regularize?", "expected": "ridge"},
]


def tokens(text):
    stopwords = {"the", "a", "an", "and", "of", "to", "in", "for", "how", "do", "does", "what", "is"}
    return Counter(t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in stopwords)


def retrieve(question, k=2, corpus=None):
    if not question.strip() or k < 1:
        raise ValueError("Nonempty question and positive k required")
    corpus = CORPUS if corpus is None else corpus
    query = tokens(question)
    scored = []
    for document in corpus:
        terms = tokens(document["title"] + " " + document["text"])
        score = sum(min(count, terms[word]) for word, count in query.items())
        if score:
            scored.append({**document, "score": score})
    return sorted(scored, key=lambda x: (-x["score"], x["id"]))[:k]


def answer(question):
    hits = retrieve(question)
    if not hits:
        return {"status": "abstained", "answer": "No supporting corpus entry found.", "citations": []}
    best = hits[0]
    return {"status": "retrieved", "answer": best["text"],
            "citations": [{"id": best["id"], "url": best["url"]}]}


def experiment():
    from src.confirmation import experiment as confirmation_experiment
    from src.comparison import experiment as comparison_experiment

    outcomes = [{"question": c["question"], "expected": c["expected"],
                 "retrieved": (retrieve(c["question"], k=1) or [{"id": None}])[0]["id"]} for c in CASES]
    correct = sum(row["expected"] == row["retrieved"] for row in outcomes)
    return {"project": "ai-research-workbench", "seed": None,
            "metrics": {"retrieval_top1_accuracy": correct / len(outcomes), "evaluation_cases": outcomes,
                        "unknown_query_abstained": answer("volcanology tectonics")['status'] == "abstained",
                        "frozen_retrieval_confirmation": confirmation_experiment(),
                        "compatible_experiment_comparisons": comparison_experiment()},
            "provenance": {"data": "Four original short source descriptions and four authored evaluation questions",
                           "confirmation": "Frozen ten-record artifact registry and 30 new source-aware authored questions; protocol and question hashes are recorded in frozen_retrieval_confirmation.",
                           "comparisons": "Saved registry metrics and reviewed case-specific dataset, evaluation protocol and quantity contracts; fingerprints and seven measured probes are recorded in compatible_experiment_comparisons.",
                           "sources": [{"id": d["id"], "url": d["url"]} for d in CORPUS]},
            "limitations": ["Small development fixture, not a held-out evaluation or verified full-paper retrieval.",
                            "Confirmation source recall and retrieval-based false support use separate denominators; authored questions do not estimate population accuracy or entailment.",
                            "Compatible comparisons describe saved synthetic point estimates; reviewed dataset identities are not independently revalidated raw-data hashes and no statistical significance is inferred.",
                            "Extractive keyword baseline; no live LLM is called by this benchmark.",
                            "Evidence export is separate from any external model-provider integration."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--question")
    args = parser.parse_args()
    payload = answer(args.question) if args.question else experiment()
    result = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result)
