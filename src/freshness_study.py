"""Measured refresh fault injections over explicit projections of saved evidence."""

import argparse
import copy
import json
from pathlib import Path
import tempfile

try:
    from .freshness import ROOT, encode, refresh, sha
    from .ingest import PROJECTS, ingest, artifact_documents
except ImportError:
    from freshness import ROOT, encode, refresh, sha
    from ingest import PROJECTS, ingest, artifact_documents


def fixture(workspace):
    """Synthetic study envelopes, not recovered original artifact bytes."""
    registry = json.loads((ROOT / "docs/registry.json").read_text(encoding="utf-8"))
    for project in PROJECTS:
        cases = [{"id": d["id"].split(":", 1)[1], "label": d["title"],
                  "description": d["text"], "metrics": copy.deepcopy(d["metrics"]),
                  "method": ["Synthetic refresh fixture projecting the bundled record; no simulation rerun."],
                  "limitations": ["Original source bytes are unavailable; this envelope is synthetic."]}
                 for d in registry["documents"] if d["project"] == project]
        path = Path(workspace) / project / "docs/study.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encode({"slug": project, "title": "Projected evidence refresh fixture", "cases": cases,
                                "provenance": "Synthetic envelope around saved registry evidence"}))
    return ingest(Path(workspace))


SCENARIOS = [
    ("unchanged", "unchanged"), ("formatting_only", "stale"),
    ("source_metadata_only", "stale"), ("metric_edit", "stale"),
    ("case_added", "stale"), ("case_removed", "stale"),
    ("missing", "missing"), ("malformed_json", "invalid"),
    ("wrong_project", "invalid"), ("duplicate_case_id", "invalid"),
]


def mutate(path, name):
    study = json.loads(path.read_bytes())
    if name == "missing":
        path.unlink()
        return
    if name == "malformed_json":
        path.write_bytes(b"{")
        return
    if name == "formatting_only":
        path.write_bytes(path.read_bytes() + b"\n")
        return
    if name == "source_metadata_only":
        study["provenance"] = "Changed source-level limitation outside the indexed projection"
    elif name == "metric_edit":
        study["cases"][0]["metrics"][0]["value"] += 1
    elif name == "case_added":
        case = copy.deepcopy(study["cases"][0])
        case["id"] = "synthetic-added"
        study["cases"].append(case)
    elif name == "case_removed":
        study["cases"].pop(0)
    elif name == "wrong_project":
        study["slug"] = "unexpected-project"
    elif name == "duplicate_case_id":
        study["cases"].append(copy.deepcopy(study["cases"][0]))
    path.write_bytes(encode(study))


def experiment():
    rows = []
    for name, expected in SCENARIOS:
        with tempfile.TemporaryDirectory(dir=ROOT / "results") as directory:
            base = Path(directory)
            workspace, registry_path, archive = base / "inputs", base / "registry.json", base / "history"
            registry = fixture(workspace)
            registry_path.write_bytes(encode(registry))
            # First refresh archives the original fixture source bytes as well.
            refresh(workspace, registry_path, registry_path, archive)
            before = registry_path.read_bytes()
            source = workspace / PROJECTS[0] / "docs/study.json"
            mutate(source, name)
            report = refresh(workspace, registry_path, registry_path, archive)
            outcome = report["sources"][0]
            try:
                current = artifact_documents(PROJECTS[0], source.read_bytes())
                old = [d for d in registry["documents"] if d["project"] == PROJECTS[0]]
                baseline = "changed" if {d["id"]: d["sha256"] for d in old} != {d["id"]: d["sha256"] for d in current} else "unchanged"
            except (OSError, ValueError, KeyError, TypeError):
                baseline = "unknown"
            archived = archive / report["old_registry_snapshot"]
            retained = archived.read_bytes() == before
            source_retained = outcome["old_raw_source_available"]
            blocked_preserved = report["ready"] or registry_path.read_bytes() == before
            rows.append({"scenario": name, "expected": expected, "status": outcome["status"],
                         "text_only_baseline": baseline, "ready": report["ready"],
                         "old_registry_sha256": sha(before), "new_registry_sha256": report["new_registry_sha256"],
                         "old_source_sha256": outcome["old_sha256"], "new_source_sha256": outcome["new_sha256"],
                         "old_ids": outcome["old_ids"], "new_ids": outcome["new_ids"],
                         "record_changes": outcome["record_changes"],
                         "exact_prior_snapshot_retained": retained,
                         "prior_raw_source_retained": source_retained,
                         "blocked_refresh_preserved_active": blocked_preserved})
    stale = [r for r in rows if r["expected"] == "stale"]
    return {"question": "Can artifact-byte checks detect changes missed by indexed-text checks while preserving reproducible prior evidence?",
            "fixture": "Synthetic source envelopes project all ten saved registry records with their metrics and full text; mutations are controlled fault injections, not observations of live source changes.",
            "registry_sha256": sha((ROOT / "docs/registry.json").read_bytes()),
            "summary": {"scenarios": len(rows), "decisions_matching_specification": sum(r["status"] == r["expected"] for r in rows),
                        "changed_artifacts": len(stale), "digest_changes_detected": sum(r["status"] == "stale" for r in stale),
                        "text_only_changes_detected": sum(r["text_only_baseline"] == "changed" for r in stale),
                        "prior_snapshots_retained": sum(r["exact_prior_snapshot_retained"] for r in rows),
                        "blocked_refreshes": sum(not r["ready"] for r in rows)},
            "rows": rows,
            "limitations": ["Controlled synthetic fault injections, not a live freshness survey or an accuracy estimate. No network refresh or companion experiment was run.",
                            "Byte changes include formatting and source metadata: stale means different bytes, not necessarily different scientific results. Unavailable or invalid sources have unknown freshness and block replacement.",
                            "Prior registry snapshots retain complete recorded IDs, metrics and evidence text. Original raw sources absent from history cannot be reconstructed; this is reported explicitly. Stored hashes do not authenticate an adversary rewriting both bytes and hashes.",
                            "A refreshed registry needs new retrieval protocols and reviewed comparison contracts. Existing frozen inputs are preserved; no compute-cost advantage or model inference is measured."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/AI03-freshness.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(experiment()))
    print(f"Wrote {args.output}")
