import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from src import independent_confirmation as confirmation, studio


class IndependentConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = confirmation.experiment()

    def test_misses_partition_wrong_source_and_empty_at_each_cutoff(self):
        rows = [
            {"stratum": "answerable", "expected_sources": ["a"], "retrieved_ids": ["b", "a"]},
            {"stratum": "answerable", "expected_sources": ["a"], "retrieved_ids": ["b"]},
            {"stratum": "answerable", "expected_sources": ["a"], "retrieved_ids": []},
            {"stratum": "misleading_overlap", "expected_sources": [], "retrieved_ids": ["a"]},
            {"stratum": "unanswerable", "expected_sources": [], "retrieved_ids": []},
        ]
        result = confirmation.summarize_with_misses(rows)
        self.assertEqual(result["source_misses"]["1"],
                         {"count": 3, "total": 3, "rate": 1.0, "empty": 1, "wrong_source": 2})
        self.assertEqual(result["source_misses"]["3"],
                         {"count": 2, "total": 3, "rate": 2 / 3, "empty": 1, "wrong_source": 1})
        self.assertEqual(result["false_support"], {"count": 1, "total": 2, "rate": 0.5})
        self.assertEqual(result["empty_retrieval"], {"answerable": 1, "unanswerable": 1})
        self.assertIsNone(confirmation.summarize_with_misses([])["source_misses"]["1"]["rate"])

    def test_every_frozen_input_and_both_sealed_inputs_reject_drift(self):
        files = list(self.result["frozen_files"]) + [confirmation.FREEZE, confirmation.QUESTIONS, confirmation.SEAL]
        with tempfile.TemporaryDirectory(dir=confirmation.ROOT / "results") as directory:
            root = Path(directory)
            for name in files:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(confirmation.ROOT / name, target)
            confirmation.validate_freeze(root)
            for name in files[:-1]:
                with self.subTest(name=name):
                    target = root / name
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n")
                    with self.assertRaisesRegex(ValueError, "changed"):
                        confirmation.validate_freeze(root)
                    target.write_bytes(original)

    def test_new_questions_coverage_and_source_anchor_validation(self):
        manifest, registry = confirmation.validate_freeze()
        fixture = json.loads((confirmation.ROOT / confirmation.QUESTIONS).read_text(encoding="utf-8"))
        prior = json.loads((confirmation.ROOT / "experiments/AI01-questions.json").read_text(encoding="utf-8"))
        old = {q["question"].casefold() for q in prior["questions"]} | {q.casefold() for q, _ in studio.QUESTIONS}
        confirmation.validate_questions(fixture, manifest, registry, old)
        for change, message in (("anchor", "anchor"), ("reuse", "reused"), ("label", "label"), ("count", "strata")):
            altered = copy.deepcopy(fixture)
            if change == "anchor":
                altered["questions"][0]["anchors"] = {altered["questions"][0]["expected_sources"][0]: "invented measurement"}
            elif change == "reuse":
                altered["questions"][0]["question"] = next(iter(old))
            elif change == "label":
                altered["questions"][0]["expected_sources"] = ["unknown-source"]
            else:
                altered["questions"].pop()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                confirmation.validate_questions(altered, manifest, registry, old)

    def test_saved_artifact_studio_and_accounting_agree(self):
        saved = json.loads((confirmation.ROOT / "results/AI04-confirmation.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.result)
        case = studio.independent_confirmation_case()
        self.assertEqual(len(case["table"]["rows"]), 28)
        self.assertIn(self.result["questions_sha256"], " ".join(case["method"]))
        for method in self.result["methods"].values():
            summary = method["summary"]
            for k in ("1", "3"):
                miss = summary["source_misses"][k]
                self.assertEqual(miss["count"], miss["wrong_source"] + miss["empty"])
                self.assertEqual(summary["source_recall"][k]["hits"] + miss["count"], summary["answerable_count"])
            self.assertEqual(summary["false_support"]["count"] + summary["empty_retrieval"]["unanswerable"], 8)
            for row in method["rows"]:
                rank = row["first_expected_rank"]
                if rank:
                    self.assertIn(row["retrieved_ids"][rank - 1], row["expected_sources"])

    @unittest.skipUnless(shutil.which("node"), "Node is optional")
    def test_browser_and_python_rankings_match_on_new_questions(self):
        source = (confirmation.ROOT / "docs/app.js").read_text(encoding="utf-8")
        code = source[source.index("const STOP ="):source.index("function search()")]
        registry = json.loads((confirmation.ROOT / "docs/registry.json").read_text(encoding="utf-8"))
        rows = self.result["methods"]["bm25"]["rows"]
        script = ("const fs=require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8')); const registry=input.registry;\n"
                  + code + "\nconsole.log(JSON.stringify(input.questions.map(q=>retrieve(q).map(d=>d.id))));")
        process = subprocess.run([shutil.which("node"), "-e", script],
                                 input=json.dumps({"registry": registry, "questions": [r["question"] for r in rows]}),
                                 capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(json.loads(process.stdout), [r["retrieved_ids"] for r in rows])


if __name__ == "__main__":
    unittest.main()
