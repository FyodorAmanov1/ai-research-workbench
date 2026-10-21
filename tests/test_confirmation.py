import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from src import confirmation, evidence, studio


class ConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = confirmation.experiment()

    def test_questions_are_new_and_cover_frozen_sources(self):
        rows = self.result["methods"]["bm25"]["rows"]
        old = {q.casefold() for q, _ in studio.QUESTIONS}
        self.assertGreaterEqual(len(rows), 20)
        self.assertTrue(all(r["question"].casefold() not in old for r in rows))
        _, registry = confirmation.validate_freeze()
        for document in registry["documents"]:
            self.assertEqual(sum(document["id"] in r["expected_sources"] for r in rows), 2)
        self.assertEqual({r["stratum"] for r in rows}, {"answerable", "unanswerable", "misleading_overlap"})

    def test_recall_does_not_count_abstention_as_source_recall(self):
        rows = [
            {"stratum": "answerable", "expected_sources": ["a"], "retrieved_ids": ["b", "a"]},
            {"stratum": "answerable", "expected_sources": ["b"], "retrieved_ids": []},
            {"stratum": "unanswerable", "expected_sources": [], "retrieved_ids": []},
            {"stratum": "misleading_overlap", "expected_sources": [], "retrieved_ids": ["a"]},
        ]
        summary = confirmation.summarize(rows)
        self.assertEqual(summary["source_recall"]["1"], {"hits": 0, "total": 2, "rate": 0.0})
        self.assertEqual(summary["source_recall"]["3"], {"hits": 1, "total": 2, "rate": 0.5})
        self.assertEqual(summary["false_support"], {"count": 1, "total": 2, "rate": 0.5})
        self.assertEqual(summary["empty_retrieval"], {"answerable": 1, "unanswerable": 1})

    def test_freeze_rejects_registry_rule_browser_and_question_drift(self):
        files = list(self.result["frozen_files"]) + [confirmation.FREEZE, confirmation.QUESTIONS, "experiments/AI01-seal.json"]
        with tempfile.TemporaryDirectory(dir=confirmation.ROOT / "results") as directory:
            root = Path(directory)
            for name in files:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(confirmation.ROOT / name, target)
            confirmation.validate_freeze(root)
            # Whitespace alone must fail: this freezes full artifacts, not just text hashes.
            for name in files[:-1]:
                with self.subTest(name=name):
                    path = root / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n")
                    with self.assertRaisesRegex(ValueError, "changed"):
                        confirmation.validate_freeze(root)
                    path.write_bytes(original)

    def test_baseline_uses_unique_terms_positive_filter_and_id_ties(self):
        registry = {"documents": [
            {"id": "z", "title": "alpha alpha", "text": "beta"},
            {"id": "a", "title": "alpha", "text": "beta beta"},
            {"id": "empty", "title": "gamma", "text": "delta"},
        ]}
        hits = confirmation.overlap_retrieve("the alpha alpha beta", registry)
        self.assertEqual([(r["id"], r["score"]) for r in hits], [("a", 2), ("z", 2)])
        self.assertEqual(confirmation.overlap_retrieve("unknown", registry), [])

    def test_unsupported_lexical_hit_is_not_empty_retrieval(self):
        _, registry = confirmation.validate_freeze()
        question = "What battery voltage and cycle lifetime does the Hubbard dimer predict?"
        self.assertTrue(evidence.retrieve(question, registry, 3))
        row = next(r for r in self.result["methods"]["bm25"]["rows"] if r["question"] == question)
        self.assertEqual(row["outcome"], "false_support")
        self.assertEqual(row["expected_sources"], [])

    def test_saved_results_and_studio_use_same_confirmation(self):
        saved = json.loads((confirmation.ROOT / "results/AI01-confirmation.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.result)
        case = studio.confirmation_case()
        self.assertEqual(len(case["table"]["rows"]), self.result["question_count"])
        self.assertIn(self.result["questions_sha256"], " ".join(case["method"]))
        for data in self.result["methods"].values():
            summary = data["summary"]
            self.assertEqual(summary["false_support"]["count"] + summary["empty_retrieval"]["unanswerable"], summary["unanswerable_count"])

    @unittest.skipUnless(shutil.which("node"), "Node is optional; Python confirmation requires no JS runtime")
    def test_frozen_browser_ranking_matches_python_for_all_questions(self):
        source = (confirmation.ROOT / "docs/app.js").read_text(encoding="utf-8")
        retrieval_code = source[source.index("const STOP ="):source.index("function search()")]
        registry = json.loads((confirmation.ROOT / "docs/registry.json").read_text(encoding="utf-8"))
        rows = self.result["methods"]["bm25"]["rows"]
        script = (
            "const fs=require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8')); const registry=input.registry;\n"
            + retrieval_code
            + "\nconsole.log(JSON.stringify(input.questions.map(q=>retrieve(q).map(d=>d.id))));"
        )
        process = subprocess.run([shutil.which("node"), "-e", script],
                                 input=json.dumps({"registry": registry, "questions": [r["question"] for r in rows]}),
                                 capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(json.loads(process.stdout), [r["retrieved_ids"] for r in rows])


if __name__ == "__main__":
    unittest.main()
