"""Reproduce retrieval diagnostics and typed-claim checks on the public study registry."""

from pathlib import Path
import numpy as np

try:
    from .common import finalize, metric
    from .evidence import load_registry, retrieve, answer, validate_claim, context
except ImportError:
    from common import finalize, metric
    from evidence import load_registry, retrieve, answer, validate_claim, context

# Authored regression questions, intentionally separate from source descriptions. Not a research-grade held-out benchmark.
QUESTIONS = [
    ("tail exposure option book", "quantum-estimation-lab:risk-1"),
    ("stressed annual volatility derivatives", "quantum-estimation-lab:risk-1.8"),
    ("Grover oracle preparation calls", "quantum-estimation-lab:amplitude"),
    ("exactly three holdings turnover", "quantum-optimization-lab:allocation"),
    ("fermionic electron double occupancy", "quantum-optimization-lab:electrons"),
    ("informed flow latency", "market-microstructure-lab:adverse"),
    ("directional market inventory", "market-microstructure-lab:trend"),
    ("balanced flow cancellations", "market-microstructure-lab:balanced"),
    ("volatility regime break coverage", "statistical-learning-lab:shift"),
    ("stable regime chronological calibration", "statistical-learning-lab:stationary"),
    ("volcanology tectonic magma", None),
    ("medieval manuscript paleography", None),
    ("quantum portfolio guaranteed profit tomorrow", None),
]


def experiment():
    registry = load_registry(Path(__file__).resolve().parents[1] / "docs/registry.json")
    rows = []
    top1 = top3 = 0
    known = {d["id"] for d in registry["documents"]}
    assert all(e is None or e in known for _, e in QUESTIONS), (
        "Evaluation label references unknown evidence"
    )
    for query, expected in QUESTIONS:
        hits = retrieve(query, registry, 3)
        ids = [h["id"] for h in hits]
        first = ids[0] if ids else None
        top1 += first == expected
        top3 += (expected in ids) if expected else not ids
        rows.append(
            [query, expected or "ABSTAIN", first or "ABSTAIN", first == expected]
        )
    source = next(d for d in registry["documents"] if d.get("metrics"))
    m = next(m for m in source["metrics"] if isinstance(m["value"], (int, float)))
    probes = [
        (
            "Correct value and unit",
            source["id"],
            m["label"],
            m["value"],
            m.get("unit", ""),
            True,
        ),
        (
            "Changed numeric value",
            source["id"],
            m["label"],
            m["value"] + 100,
            m.get("unit", ""),
            False,
        ),
        ("Wrong unit", source["id"], m["label"], m["value"], "bananas", False),
        (
            "Unknown evidence",
            "missing",
            m["label"],
            m["value"],
            m.get("unit", ""),
            False,
        ),
        (
            "Unknown label",
            source["id"],
            "unreported profit",
            m["value"],
            m.get("unit", ""),
            False,
        ),
    ]
    probe_rows = []
    for name, s, label, value, unit, expected in probes:
        outcome = validate_claim(registry, s, label, value, unit)
        assert outcome["accepted"] == expected
        probe_rows.append([name, outcome["accepted"], outcome["reason"]])
    bounded = context("quantum portfolio risk", registry, 8000)
    assert len(bounded) <= 8000
    source_count = len(registry["documents"])
    retrieval = {
        "id": "evidence",
        "label": "Evidence explorer",
        "kicker": "AI INTEGRATION / TRACEABLE RESEARCH RECORDS",
        "title": "Ask a question. Follow the evidence.",
        "description": "Search actual experiment records across four public research projects. Every result carries its source URL, content digest, measured metrics and limitations. No model or API is called by this offline explorer.",
        "metrics": [
            metric("Public experiment records", source_count),
            metric(
                "Top-1 authored regression accuracy", 100 * top1 / len(QUESTIONS), "%"
            ),
            metric(
                "Top-3 authored regression accuracy", 100 * top3 / len(QUESTIONS), "%"
            ),
            metric(
                "Unsupported-topic abstentions",
                sum(
                    answer(q, registry)["status"] == "abstained"
                    for q, e in QUESTIONS
                    if e is None
                ),
            ),
        ],
        "charts": [
            {
                "title": "Rank sensitivity · authored question set",
                "x": [1, 2, 3],
                "xlabel": "Maximum retrieved evidence records",
                "series": [
                    {
                        "name": "Expected source recall / %",
                        "values": [
                            100
                            * sum(
                                (
                                    (e in [d["id"] for d in retrieve(q, registry, k)])
                                    if e
                                    else not retrieve(q, registry, k)
                                )
                                for q, e in QUESTIONS
                            )
                            / len(QUESTIONS)
                            for k in [1, 2, 3]
                        ],
                    }
                ],
            }
        ],
        "table": {
            "columns": [
                "Question",
                "Expected source",
                "Top result",
                "Correct at rank 1",
            ],
            "rows": rows,
        },
        "method": [
            "A portable JSON registry snapshots public study artifacts. Each record contains source repository, experiment ID, source-artifact SHA-256, content SHA-256, typed metrics, methods and limitations.",
            "BM25 term weighting (k₁=1.2, b=0.75) ranks original experiment records. Ties use source ID. Empty lexical support causes abstention; scores are relevance weights, not confidence probabilities.",
            "The browser performs the same deterministic retrieval locally. Python provides an extractive answer interface and a bounded JSON context adapter for an already running model session. Neither path creates a model session or spends tokens.",
        ],
        "limitations": [
            "Thirteen authored regression questions are small development fixtures, not an independent held-out benchmark. Failed queries remain in the table.",
            "The guaranteed-profit question deliberately shares corpus terms but has no supporting answer: BM25 retrieves anyway. Empty-lexical-support abstention does not detect semantic false support. No semantic answer correctness or hallucination rate is estimated.",
            "Snapshots can become stale. Source artifact digests identify exactly which local public report was ingested; re-ingestion is explicit. Registry hashes detect accidental edits, not a malicious party able to rewrite both data and hashes.",
        ],
        "reproduce": 'python src/evidence.py --query "fermionic double occupancy"',
    }
    claims = {
        "id": "claims",
        "label": "Claim audit & integration",
        "kicker": "TYPED METRICS / BOUNDED CONTEXT",
        "title": "Check the number before it becomes a claim.",
        "description": "A numeric claim must name an existing experiment, a recorded metric, its exact unit and a matching value. Export source-labelled context into an existing AI workflow without launching another agent.",
        "metrics": [
            metric("Claim probes matching specification", len(probe_rows)),
            metric("Rejected invalid claims", 4),
            metric("Exported context size", len(bounded), "chars"),
            metric("Additional model sessions", 0),
        ],
        "charts": [],
        "table": {"columns": ["Probe", "Accepted", "Reason"], "rows": probe_rows},
        "method": [
            "Claim validation uses exact source IDs and metric labels, exact unit strings and numeric isclose tolerance 10⁻⁶ relative / 10⁻⁸ absolute. It never changes units implicitly.",
            "Source text is serialized as JSON evidence under a data-only header. Context export is capped at 8,000 characters by default and accepts a bounded 500–32,000-character setting. Complete records are included; records are not silently truncated.",
            "Controller integration uses the same existing daily Codex session, medium effort and cumulative 20-minute cap. This adapter is opt-in input preparation, not a second autonomous worker.",
        ],
        "limitations": [
            "Matching a recorded number verifies transcription only. It does not validate the underlying study or establish causality, profitability or quantum advantage.",
            "Five specified claim probes demonstrate interface behavior, not robustness to all adversarial inputs. JSON boundaries and instructions do not guarantee an LLM will resist prompt injection.",
            "The offline browser and CLI do not generate prose using an LLM. Live model integration requires the existing authorized session; no paid fallback is installed.",
        ],
        "reproduce": 'python src/evidence.py --query "quantum portfolio risk" --context --max-chars 8000',
    }
    return {
        "schema_version": 1,
        "slug": "ai-research-workbench",
        "title": "Research Evidence Observatory",
        "subtitle": "An inspectable bridge from experiments to AI-assisted research.",
        "accent": "#ff9caa",
        "seed": None,
        "cases": [retrieval, claims],
        "provenance": "Registry derived solely from the four public companion study artifacts. No unpublished research, credentials or paper text is ingested.",
        "references": [
            {
                "title": "BM25: The Probabilistic Relevance Framework",
                "url": "https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf",
            },
            {
                "title": "Retrieval-augmented generation",
                "url": "https://arxiv.org/abs/2005.11401",
            },
        ],
    }


if __name__ == "__main__":
    finalize(experiment())
