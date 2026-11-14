import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.structured_query import (ROOT, QueryTool, QueryError, ProjectQuery,
                                  ExperimentQuery, MetricQuery, record_sha256)
from src.query_study import experiment


class StructuredQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "docs/registry.json").read_bytes()
        cls.registry = json.loads(cls.raw)

    def setUp(self):
        self.tool = QueryTool(self.raw)

    def test_typed_scope_enumeration_and_exact_lookup(self):
        projects = self.tool.execute(ProjectQuery())
        self.assertEqual(len(projects["data"]), 4)
        self.assertEqual(len(projects["sources"]), 10)
        for project in projects["data"]:
            result = self.tool.execute(ExperimentQuery(project["project_id"]))
            self.assertEqual([d["experiment_id"] for d in result["data"]], project["experiment_ids"])
            for d in result["data"]:
                metrics = self.tool.execute(MetricQuery(project["project_id"], d["experiment_id"]))
                self.assertEqual([m["label"] for m in metrics["data"]], d["metric_labels"])
                for m in metrics["data"]:
                    exact = self.tool.execute(MetricQuery(project["project_id"], d["experiment_id"], m["label"]))
                    self.assertEqual(exact["data"], [m])

    def test_unknown_data_is_distinct_from_zero_and_no_fallback(self):
        zero = self.tool.execute(MetricQuery("market-microstructure-lab", "balanced", "Cash / inventory violations"))
        self.assertEqual(zero["data"][0]["value"], 0)
        for query, code in [(ProjectQuery("missing"), "unknown_project"),
                            (ExperimentQuery("statistical-learning-lab", "balanced"), "unknown_experiment"),
                            (MetricQuery("statistical-learning-lab", "stationary", "frozen ridge mae"), "unknown_metric")]:
            result = self.tool.execute(query)
            self.assertEqual(result["code"], code)
            self.assertNotIn("data", result)
            self.assertEqual(result["registry_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(len(result["sources"]), 1)

    def test_runtime_types_and_unknown_fields_fail_closed(self):
        queries = [None, [], "metric", {}, {"kind": []}, {"kind": "other"},
                   {"kind": "experiment"}, {"kind": "metric", "project_id": "x"},
                   {"kind": "project", "project_id": " "}, {"kind": "project", "project_id": 0},
                   {"kind": "project", "limit": 1}, asdict(ProjectQuery(kind="metric")),
                   {"kind": "metric", "project_id": "x", "experiment_id": "y", "metric_label": False}]
        for query in queries:
            with self.subTest(query=query):
                result = self.tool.execute(query)
                self.assertEqual(result["code"], "invalid_query")
                self.assertNotIn("data", result)

    def test_hashes_cover_complete_record_and_exact_registry_bytes(self):
        original = self.tool.execute(ProjectQuery())["sources"][0]
        registry = copy.deepcopy(self.registry)
        doc = next(d for d in registry["documents"] if d["id"] == original["source_id"])
        self.assertEqual(original["record_sha256"], record_sha256(doc))
        doc["metrics"][0]["value"] += 1
        changed = QueryTool(json.dumps(registry).encode()).execute(ProjectQuery())["sources"][0]
        self.assertNotEqual(original["record_sha256"], changed["record_sha256"])
        self.assertEqual(original["sha256"], changed["sha256"])
        # Formatting-only registry change has a distinct byte digest.
        other = QueryTool(self.raw + b"\n").execute(ProjectQuery())
        self.assertNotEqual(other["registry_sha256"], self.tool.registry_sha256)
        self.assertEqual(other["sources"][0], original)

    def test_results_cannot_mutate_snapshot(self):
        first = self.tool.execute(MetricQuery("statistical-learning-lab", "stationary"))
        expected = copy.deepcopy(first)
        first["data"][0]["value"] = 123
        first["sources"][0]["sha256"] = "changed"
        self.assertEqual(self.tool.execute(MetricQuery("statistical-learning-lab", "stationary")), expected)

    def test_invalid_snapshots_rejected(self):
        def duplicate_source(r):
            r["documents"].append(copy.deepcopy(r["documents"][0]))
        def duplicate_metric(r):
            r["documents"][0]["metrics"].append(copy.deepcopy(r["documents"][0]["metrics"][0]))
        mutations = [duplicate_source, duplicate_metric,
                     lambda r: r["documents"][0].update(text="edited"),
                     lambda r: r["documents"][0].update(artifact_sha256="bad"),
                     lambda r: r["documents"][0].update(project="other"),
                     lambda r: r["documents"][0].update(url="https://example.com"),
                     lambda r: r["documents"][0].pop("title"),
                     lambda r: r["documents"][0]["metrics"][0].pop("unit")]
        for value in [True, None, "1", float("nan"), float("inf")]:
            mutations.append(lambda r, value=value: r["documents"][0]["metrics"][0].update(value=value))
        for mutate in mutations:
            r = copy.deepcopy(self.registry)
            mutate(r)
            with self.assertRaises(QueryError) as caught:
                QueryTool(json.dumps(r).encode())
            self.assertEqual(caught.exception.code, "invalid_data")
        with self.assertRaises(QueryError):
            QueryTool(b"not json")

    def test_actual_study_and_saved_artifacts(self):
        result = experiment()
        self.assertEqual(result["summary"], {"probes": 12, "matching_specification": 12,
                         "known_requests": 6, "known_requests_correct": 6, "unknown_requests": 6,
                         "explicit_unknown_errors": 6, "unknown_values_returned": 0,
                         "bm25_nonempty_on_unknown": 6, "bm25_empty_on_unknown": 0})
        self.assertEqual(result, json.loads((ROOT / "results/AI05-queries.json").read_text(encoding="utf-8")))
        from src.studio import query_case
        self.assertEqual(len(query_case()["table"]["rows"]), 12)
        self.assertEqual(query_case()["query_snapshot"], self.tool.execute(ProjectQuery()))

    def test_cli_errors_are_json_and_have_nonzero_status(self):
        queries = [(asdict(MetricQuery("statistical-learning-lab", "stationary", "Frozen ridge MAE")), 0, "ok"),
                   (asdict(ProjectQuery("missing")), 2, "unknown_project"), ([], 2, "invalid_query")]
        for query, status, code in queries:
            run = subprocess.run([sys.executable, "-m", "src.structured_query", "--query", json.dumps(query)],
                                 cwd=ROOT, capture_output=True, text=True, check=False, timeout=15)
            self.assertEqual(run.returncode, status, run.stderr)
            self.assertEqual(json.loads(run.stdout)["code"], code)
        with tempfile.TemporaryDirectory(dir=ROOT / "results") as directory:
            with self.assertRaises(QueryError) as caught:
                QueryTool.from_path(Path(directory) / "missing.json")
            self.assertEqual(caught.exception.code, "unavailable_registry")

    @unittest.skipUnless(shutil.which("node"), "Node is optional")
    def test_browser_python_parity_all_metrics_and_errors(self):
        queries = [{"kind": "project"}, {"kind": "project", "project_id": "missing"},
                   {"kind": "experiment", "project_id": "statistical-learning-lab", "experiment_id": "missing"},
                   {"kind": "metric", "project_id": "statistical-learning-lab", "experiment_id": "stationary", "metric_label": "missing"},
                   {"kind": "project", "project_id": False}, {"kind": []}, None, [], {"kind": "project", "extra": 1}]
        for d in self.registry["documents"]:
            p, e = d["id"].split(":", 1)
            queries.extend([asdict(ProjectQuery(p)), asdict(ExperimentQuery(p)), asdict(ExperimentQuery(p, e)), asdict(MetricQuery(p, e))])
            queries.extend(asdict(MetricQuery(p, e, m["label"])) for m in d["metrics"])
        snapshot = self.tool.execute(ProjectQuery())
        source = (ROOT / "docs/structured-query.js").read_text(encoding="utf-8").split("async function initializeStructuredQuery")[0]
        script = "const x=JSON.parse(require('fs').readFileSync(0,'utf8'));\n" + source + "\nconsole.log(JSON.stringify(x.queries.map(q=>structuredQuery(x.registry,x.snapshot,q))));"
        run = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({"registry": self.registry, "snapshot": snapshot, "queries": queries}),
                             capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(json.loads(run.stdout), [self.tool.execute(q) for q in queries])


if __name__ == "__main__":
    unittest.main()
