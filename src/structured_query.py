"""Exact, offline project/experiment/metric queries over a saved registry."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Literal, TypedDict

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProjectQuery:
    project_id: str | None = None
    kind: Literal["project"] = "project"


@dataclass(frozen=True)
class ExperimentQuery:
    project_id: str
    experiment_id: str | None = None
    kind: Literal["experiment"] = "experiment"


@dataclass(frozen=True)
class MetricQuery:
    project_id: str
    experiment_id: str
    metric_label: str | None = None
    kind: Literal["metric"] = "metric"


Query = ProjectQuery | ExperimentQuery | MetricQuery


class QueryResult(TypedDict, total=False):
    status: Literal["ok", "error"]
    code: str
    message: str
    registry_sha256: str
    query: dict
    data: list[dict]
    sources: list[dict]


class QueryError(ValueError):
    """Stable machine-readable failure; never substitutes a nearby record."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def record_sha256(document: dict) -> str:
    """Canonical complete record, including metrics; distinct from indexed text."""
    return sha256(json.dumps(document, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8"))


def parse_query(payload: object) -> Query:
    if not isinstance(payload, dict):
        raise QueryError("invalid_query", "Query must be a JSON object")
    classes = {"project": ProjectQuery, "experiment": ExperimentQuery, "metric": MetricQuery}
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in classes:
        raise QueryError("invalid_query", "kind must be project, experiment or metric")
    fields = {"project": {"kind", "project_id"},
              "experiment": {"kind", "project_id", "experiment_id"},
              "metric": {"kind", "project_id", "experiment_id", "metric_label"}}[kind]
    if set(payload) - fields:
        raise QueryError("invalid_query", "Unknown query fields")
    required = {"project": (), "experiment": ("project_id",),
                "metric": ("project_id", "experiment_id")}[kind]
    for field in fields - {"kind"}:
        value = payload.get(field)
        if value is None and field not in required:
            continue
        if not isinstance(value, str) or not value.strip():
            raise QueryError("invalid_query", field + " must be a nonempty string")
    return classes[kind](**payload)


class QueryTool:
    """Own one validated snapshot. Hash raw bytes before decoding; no live refresh."""
    def __init__(self, raw: bytes):
        self.registry_sha256 = sha256(raw)
        try:
            registry = json.loads(raw)
            documents = registry["documents"]
            if not isinstance(documents, list):
                raise ValueError("documents must be a list")
            ids = set()
            for d in documents:
                if not isinstance(d["title"], str) or not isinstance(d["metrics"], list):
                    raise ValueError("Title and metric list required")
                if not isinstance(d["project"], str) or not d["project"]:
                    raise ValueError("Missing project identity")
                if not d["id"].startswith(d["project"] + ":") or not d["id"].split(":", 1)[1]:
                    raise ValueError("Source ID must contain project:experiment")
                if d["id"] in ids:
                    raise ValueError("Duplicate source ID")
                ids.add(d["id"])
                if not d["url"].startswith("https://github.com/FyodorAmanov1/"):
                    raise ValueError("Untrusted evidence origin")
                for field in ("sha256", "artifact_sha256"):
                    if not isinstance(d[field], str) or not re.fullmatch(r"[0-9a-f]{64}", d[field]):
                        raise ValueError("Invalid source digest")
                if sha256(d["text"].encode("utf-8")) != d["sha256"]:
                    raise ValueError("Evidence content hash mismatch")
                labels = set()
                for m in d["metrics"]:
                    if not isinstance(m["label"], str) or not m["label"] or m["label"] in labels:
                        raise ValueError("Invalid or duplicate metric label")
                    labels.add(m["label"])
                    if type(m["value"]) not in (int, float) or not math.isfinite(m["value"]):
                        raise ValueError("Metric must be finite numeric data; booleans excluded")
                    if not isinstance(m["unit"], str):
                        raise ValueError("Explicit metric unit required")
                record_sha256(d)
            # Private decoded copy: neither caller mutations nor result edits affect it.
            self._documents = documents
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
            raise QueryError("invalid_data", str(error)) from error

    @classmethod
    def from_path(cls, path: Path = ROOT / "docs/registry.json") -> QueryTool:
        try:
            return cls(Path(path).read_bytes())
        except OSError as error:
            raise QueryError("unavailable_registry", "Registry cannot be read") from error

    def execute(self, query: Query | dict) -> QueryResult:
        sources = []
        try:
            payload = asdict(query) if isinstance(query, (ProjectQuery, ExperimentQuery, MetricQuery)) else query
            q = parse_query(payload)
            docs = self._documents
            project = q.project_id
            if project is not None:
                docs = [d for d in docs if d["project"] == project]
                if not docs:
                    raise QueryError("unknown_project", "Project is absent from this snapshot")
            if isinstance(q, (ExperimentQuery, MetricQuery)) and q.experiment_id is not None:
                docs = [d for d in docs if d["id"] == project + ":" + q.experiment_id]
                if not docs:
                    raise QueryError("unknown_experiment", "Experiment is absent from the selected project")
            docs = sorted(docs, key=lambda d: d["id"])
            sources = [{"source_id": d["id"], "url": d["url"], "sha256": d["sha256"],
                        "artifact_sha256": d["artifact_sha256"], "record_sha256": record_sha256(d)} for d in docs]
            if isinstance(q, ProjectQuery):
                data = [{"project_id": p, "experiment_ids": [d["id"].split(":", 1)[1] for d in docs if d["project"] == p]}
                        for p in sorted({d["project"] for d in docs})]
            elif isinstance(q, ExperimentQuery):
                data = [{"project_id": d["project"], "experiment_id": d["id"].split(":", 1)[1],
                         "source_id": d["id"], "title": d["title"], "metric_labels": [m["label"] for m in d["metrics"]]} for d in docs]
            else:
                data = [{"source_id": d["id"], **m} for d in docs for m in d["metrics"]
                        if q.metric_label is None or m["label"] == q.metric_label]
                if not data:
                    raise QueryError("unknown_metric", "Metric is absent from the selected experiment")
            result = {"status": "ok", "code": "ok", "query": asdict(q), "data": data,
                      "sources": sources, "registry_sha256": self.registry_sha256}
            return json.loads(json.dumps(result, allow_nan=False))
        except QueryError as error:
            return {"status": "error", "code": error.code, "message": str(error),
                    "sources": sources, "registry_sha256": self.registry_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "docs/registry.json")
    parser.add_argument("--query", required=True, help="JSON object with exact selectors")
    args = parser.parse_args()
    try:
        result = QueryTool.from_path(args.registry).execute(json.loads(args.query))
    except (QueryError, json.JSONDecodeError) as error:
        result = {"status": "error", "code": getattr(error, "code", "invalid_query"), "message": str(error)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
