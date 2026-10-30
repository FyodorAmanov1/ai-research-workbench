import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from src import comparison, studio


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.contracts = comparison.load_inputs()

    def setUp(self):
        self.r = copy.deepcopy(self.registry)
        self.c = copy.deepcopy(self.contracts)
        self.source = "statistical-learning-lab:stationary"

    def compare(self, left="Expanding ridge MAE", right="Frozen ridge MAE", source=None):
        return comparison.compare_metrics(self.r, self.c, self.source, left, source or self.source, right)

    def test_candidate_baseline_difference_and_provenance(self):
        result = self.compare()
        self.assertTrue(result["accepted"])
        self.assertAlmostEqual(result["difference"], 0.0007540724717869365)
        for side in ("left", "right"):
            self.assertEqual(result[side]["source_id"], self.source)
            self.assertTrue(result[side]["url"].startswith("https://github.com/"))
            self.assertEqual(len(result[side]["artifact_sha256"]), 64)
        reverse = self.compare("Frozen ridge MAE", "Expanding ridge MAE")
        self.assertEqual(reverse["difference"], -result["difference"])
        self.assertEqual(self.compare("Frozen ridge MAE")["difference"], 0)

    def test_separate_incompatibilities_never_return_difference(self):
        cases = [
            (self.compare(source="statistical-learning-lab:shift"), "dataset_mismatch"),
            (self.compare("Nominal interval coverage", "Observed test coverage"), "protocol_mismatch"),
            (self.compare(right="Observed test coverage"), "unit_mismatch"),
            (comparison.compare_metrics(self.r, self.c, "quantum-estimation-lab:risk-1", "99% value at risk", "quantum-estimation-lab:risk-1", "99% expected shortfall"), "quantity_mismatch"),
            (self.compare(left="not registered"), "unknown_metric"),
            (self.compare(source="missing"), "unknown_source"),
        ]
        for result, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(result["code"], expected)
                self.assertFalse(result["accepted"])
                self.assertNotIn("difference", result)

    def test_missing_or_blank_metadata_fails_closed(self):
        for field in ("dataset_id", "protocol_id", "quantity_id"):
            for bad in (None, "", " ", 1):
                with self.subTest(field=field, bad=bad):
                    self.c = copy.deepcopy(self.contracts)
                    entry = next(c for c in self.c["metrics"] if c["source_id"] == self.source and c["label"] == "Frozen ridge MAE")
                    entry[field] = bad
                    self.assertEqual(self.compare()["code"], "missing_metadata")
        self.c["metrics"] = []
        self.assertEqual(self.compare()["code"], "missing_metadata")

    def test_unreviewed_counts_are_not_dimensionless_equivalents(self):
        result = comparison.compare_metrics(self.r, self.c, "quantum-estimation-lab:amplitude", "Logical qubits", "quantum-estimation-lab:amplitude", "Oracle preparation calls")
        self.assertEqual(result["code"], "missing_metadata")

    def test_finite_numeric_metrics_required(self):
        metric = next(d for d in self.r["documents"] if d["id"] == self.source)["metrics"][0]
        for value in (True, False, "0.4", None, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                metric["value"] = value
                result = self.compare()
                self.assertEqual(result["code"], "non_numeric")
                self.assertNotIn("difference", result)

    def test_units_must_be_explicit_and_exact(self):
        metric = next(d for d in self.r["documents"] if d["id"] == self.source)["metrics"][0]
        del metric["unit"]
        self.assertEqual(self.compare()["code"], "missing_unit")
        metric["unit"] = "dimensionless"
        self.assertEqual(self.compare()["code"], "unit_mismatch")

    def test_ambiguous_source_metric_and_contract_rejected(self):
        document = next(d for d in self.r["documents"] if d["id"] == self.source)
        self.r["documents"].append(copy.deepcopy(document))
        self.assertEqual(self.compare()["code"], "ambiguous_source")
        self.r["documents"].pop()
        document["metrics"].append(copy.deepcopy(document["metrics"][0]))
        self.assertEqual(self.compare()["code"], "ambiguous_metric")
        document["metrics"].pop()
        self.c["metrics"].append(copy.deepcopy(next(c for c in self.c["metrics"] if c["source_id"] == self.source and c["label"] == "Frozen ridge MAE")))
        self.assertEqual(self.compare()["code"], "missing_metadata")

    def test_source_and_metric_drift_rejected(self):
        for field in ("artifact_sha256", "sha256"):
            self.r = copy.deepcopy(self.registry)
            next(d for d in self.r["documents"] if d["id"] == self.source)[field] = "changed"
            self.assertEqual(self.compare()["code"], "stale_contract")
        self.r = copy.deepcopy(self.registry)
        next(d for d in self.r["documents"] if d["id"] == self.source)["metrics"][0]["value"] += 1
        self.assertEqual(self.compare()["code"], "stale_contract")

    def test_full_registry_fingerprint_rejected_on_drift(self):
        with tempfile.TemporaryDirectory(dir=comparison.ROOT / "results") as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            for name in ("registry.json", "comparison-contracts.json"):
                shutil.copyfile(comparison.ROOT / "docs" / name, root / "docs" / name)
            comparison.load_inputs(root)
            path = root / "docs/registry.json"
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                comparison.load_inputs(root)

    def test_measured_cases_and_studio_remain_consistent(self):
        result = comparison.experiment()
        self.assertEqual(result["summary"], {"probes": 7, "decisions_matching_specification": 7, "accepted": 2, "incompatible_accepted": 0, "unit_only_incompatible_accepted": 4})
        self.assertGreater(result["rows"][1]["result"]["difference"], 0)
        self.assertEqual(len(studio.comparison_case()["table"]["rows"]), 7)
        saved = json.loads((comparison.ROOT / "results/AI02-comparisons.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, result)

    @unittest.skipUnless(shutil.which("node"), "Node is optional")
    def test_browser_matches_python_on_all_registered_pairs_and_invalid_inputs(self):
        choices = [(d["id"], m["label"]) for d in self.r["documents"] for m in d["metrics"]]
        pairs = [[*a, *b] for a in choices for b in choices]
        pairs += [["missing", "missing", *choices[0]], [*choices[0], choices[0][0], "missing"]]
        source = (comparison.ROOT / "docs/comparison.js").read_text(encoding="utf-8").split("async function initializeComparisons")[0]
        script = "const input=JSON.parse(require('fs').readFileSync(0,'utf8'));\n" + source + "\nconsole.log(JSON.stringify(input.pairs.map(p=>compareMetrics(input.registry,input.contracts,...p))));"
        process = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({"registry": self.r, "contracts": self.c, "pairs": pairs}), capture_output=True, text=True, check=True, timeout=30)
        expected = [comparison.compare_metrics(self.r, self.c, *p) for p in pairs]
        self.assertEqual(json.loads(process.stdout), expected)


if __name__ == "__main__":
    unittest.main()
