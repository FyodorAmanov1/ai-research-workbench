"""Explicitly ingest only named public companion study JSON, without network access."""

import argparse
import hashlib
import json
import math
from pathlib import Path

PROJECTS = [
    "quantum-estimation-lab",
    "quantum-optimization-lab",
    "market-microstructure-lab",
    "statistical-learning-lab",
]


def ingest(workspace):
    documents = []
    for project in PROJECTS:
        raw = (workspace / project / "docs/study.json").read_bytes()
        documents.extend(artifact_documents(project, raw))
    return {
        "schema_version": 1,
        "description": "Explicit snapshot of four public companion studies; not a live index.",
        "documents": documents,
    }


def artifact_documents(project, raw):
    """Project one explicit artifact, keeping the original registry format."""
    documents = []
    study = json.loads(raw)
    if study["slug"] != project:
        raise ValueError("Unexpected project identity")
    if not isinstance(study["title"], str) or not isinstance(study["cases"], list):
        raise ValueError("Invalid study fields")
    artifact = hashlib.sha256(raw).hexdigest()
    for case in study["cases"]:
        if not all(isinstance(case[k], str) and case[k] for k in ("id", "label", "description")):
            raise ValueError("Invalid case fields")
        if not all(isinstance(case[k], list) and all(isinstance(v, str) for v in case[k]) for k in ("method", "limitations")):
            raise ValueError("Invalid evidence boundaries")
        if not isinstance(case["metrics"], list):
            raise ValueError("Invalid metrics")
        for m in case["metrics"]:
            if (not isinstance(m["label"], str) or not isinstance(m.get("unit", ""), str)
                    or isinstance(m["value"], bool) or not isinstance(m["value"], (int, float))
                    or not math.isfinite(m["value"])):
                raise ValueError("Invalid typed metric")
        title = study["title"] + " / " + case["label"]
        text = "\n".join(
            [
                case["description"],
                *[
                    f"{m['label']}: {m['value']} {m.get('unit', '')}"
                    for m in case["metrics"]
                ],
                *case["method"],
                "Limitations:",
                *case["limitations"],
            ]
        )
        documents.append(
            {
                "id": project + ":" + case["id"],
                "title": title,
                "project": project,
                "url": f"https://github.com/FyodorAmanov1/{project}/blob/main/docs/study.json",
                "demo": f"https://fyodoramanov1.github.io/{project}/#{case['id']}",
                "artifact_sha256": artifact,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "text": text,
                "metrics": case["metrics"],
            }
        )
    ids = [d["id"] for d in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source case IDs")
    return documents


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/registry.json"))
    parser.add_argument("--archive", type=Path, default=Path("results/registry-history"))
    a = parser.parse_args()
    if a.out.exists():
        try:
            from .freshness import refresh
        except ImportError:
            from freshness import refresh
        report = refresh(a.workspace.resolve(), a.out, a.out, a.archive)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["ready"] else 2)
    payload = ingest(a.workspace.resolve())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Indexed {len(payload['documents'])} source records")
