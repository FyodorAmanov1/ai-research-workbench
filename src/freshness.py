"""Offline artifact refresh with immutable snapshots and explicit unknown states."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

try:
    from .ingest import PROJECTS, artifact_documents
    from .evidence import load_registry
except ImportError:
    from ingest import PROJECTS, artifact_documents
    from evidence import load_registry

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def inspect_sources(workspace, registry):
    """Read each allowlisted artifact once; compare bytes, never timestamps."""
    rows, documents, artifacts = [], [], {}
    for project in PROJECTS:
        old = [d for d in registry["documents"] if d["project"] == project]
        digests = {d.get("artifact_sha256") for d in old}
        if not old and project in registry.get("source_artifacts", {}):
            digests = {registry["source_artifacts"][project]}
        row = {"project": project, "old_ids": [d["id"] for d in old],
               "old_sha256": next(iter(digests)) if len(digests) == 1 else None,
               "new_sha256": None, "new_ids": [], "record_changes": []}
        rows.append(row)
        try:
            raw = (Path(workspace) / project / "docs/study.json").read_bytes()
        except OSError:
            row.update(status="missing", reason="Source artifact unavailable; freshness unknown")
            continue
        row["new_sha256"] = sha(raw)
        artifacts[sha(raw)] = raw
        try:
            fresh = artifact_documents(project, raw)
            # Reject nonfinite JSON values before any publication.
            encode(fresh)
        except (ValueError, KeyError, TypeError, UnicodeError, AttributeError):
            row.update(status="invalid", reason="Invalid study schema, values or project identity")
            continue
        if not isinstance(row["old_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["old_sha256"]):
            row.update(status="unverifiable", reason="No unique explicit prior source-artifact SHA-256")
            continue
        row["new_ids"] = [d["id"] for d in fresh]
        previous = {d["id"]: d for d in old}
        current = {d["id"]: d for d in fresh}
        for source_id in sorted(previous.keys() | current.keys()):
            before, after = previous.get(source_id), current.get(source_id)
            state = "added" if before is None else "removed" if after is None else (
                "unchanged" if {k: v for k, v in before.items() if k != "artifact_sha256"} ==
                {k: v for k, v in after.items() if k != "artifact_sha256"} else "changed")
            row["record_changes"].append({"source_id": source_id, "status": state})
        row["status"] = "unchanged" if row["old_sha256"] == row["new_sha256"] else "stale"
        row["reason"] = "Exact source bytes match" if row["status"] == "unchanged" else "Source bytes changed; prior snapshot retained"
        documents.extend(fresh)
    ready = all(r["status"] in ("unchanged", "stale") for r in rows)
    candidate = {**registry, "documents": documents,
                 "source_artifacts": {r["project"]: r["new_sha256"] for r in rows}} if ready else None
    return {"ready": ready, "sources": rows}, candidate, artifacts


def _snapshot(archive, kind, raw):
    relative = f"{kind}/{sha(raw)}.json"
    path = Path(archive) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("History snapshot hash mismatch; refusing overwrite")
    return relative


def refresh(workspace, registry_path, out, archive):
    """Archive the exact old registry and observed sources before atomic replacement.

    A failed check never writes out. Old raw source bytes cannot be recovered from
    projected records: history reports whether those bytes were already archived.
    """
    registry_path, out, archive = Path(registry_path), Path(out), Path(archive)
    raw = registry_path.read_bytes()
    registry = load_registry(registry_path)
    if registry_path.read_bytes() != raw:
        raise ValueError("Registry changed during refresh; retry with a stable snapshot")
    projects = set(d["project"] for d in registry["documents"]) | set(registry.get("source_artifacts", {}))
    if projects != set(PROJECTS):
        raise ValueError("Refresh requires the four explicit companion projects")
    report, candidate, artifacts = inspect_sources(workspace, registry)
    report["old_registry_sha256"] = sha(raw)
    report["old_registry_snapshot"] = _snapshot(archive, "registries", raw)
    for digest, source_raw in artifacts.items():
        _snapshot(archive, "sources", source_raw)
    for row in report["sources"]:
        digest = row["old_sha256"]
        valid_digest = isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        old_path = archive / "sources" / f"{digest}.json" if valid_digest else None
        row["old_raw_source_available"] = bool(old_path and old_path.is_file() and sha(old_path.read_bytes()) == digest)
        row["old_raw_source_snapshot"] = f"sources/{digest}.json" if row["old_raw_source_available"] else None
        row["new_raw_source_snapshot"] = f"sources/{row['new_sha256']}.json" if row["new_sha256"] else None
    if candidate is not None:
        candidate_raw = encode(candidate)
        report["new_registry_sha256"] = sha(candidate_raw)
        report["new_registry_snapshot"] = _snapshot(archive, "registries", candidate_raw)
    else:
        report["new_registry_sha256"] = None
        report["new_registry_snapshot"] = None
    _snapshot(archive, "audits", encode(report))
    if candidate is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        # Same-directory replacement keeps an interrupted write off the active path.
        with tempfile.NamedTemporaryFile(dir=out.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(candidate_raw)
        try:
            temporary.replace(out)
        finally:
            temporary.unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("docs/registry.json"))
    parser.add_argument("--out", type=Path, default=Path("results/refreshed-registry.json"))
    parser.add_argument("--archive", type=Path, default=Path("results/registry-history"))
    parser.add_argument("--report", type=Path, default=Path("results/refresh-audit.json"))
    args = parser.parse_args()
    report = refresh(args.workspace, args.registry, args.out, args.archive)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(encode(report))
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
