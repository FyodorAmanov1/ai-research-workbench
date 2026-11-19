import copy
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

from src import baseline_study as study, studio
from src.retrieval_baselines import METHODS, tfidf_retrieve


class TfidfTests(unittest.TestCase):
    def test_analytic_cosine_and_corpus_only_idf(self):
        registry = {"documents": [
            {"id": "b", "title": "", "text": "apple apple banana"},
            {"id": "a", "title": "", "text": "banana"}]}
        hits = tfidf_retrieve("apple unseen", registry)
        rare = 1 + math.log(3 / 2)
        self.assertEqual([h["id"] for h in hits], ["b"])
        self.assertAlmostEqual(hits[0]["score"], 2 * rare / math.sqrt(4 * rare ** 2 + 1))
        self.assertEqual(hits, tfidf_retrieve("apple apple", registry))
        self.assertEqual(registry["documents"][0].keys(), {"id", "title", "text"})

    def test_empty_oov_stopwords_and_ties(self):
        registry = {"documents": [{"id": x, "title": "apple", "text": ""} for x in ("z", "a")]}
        self.assertEqual([h["id"] for h in tfidf_retrieve("apple", registry, 1)], ["a"])
        for q in ("", "the and", "quasar"):
            self.assertEqual(tfidf_retrieve(q, registry), [])
        self.assertEqual(tfidf_retrieve("apple", {"documents": []}), [])
        for k in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                tfidf_retrieve("apple", registry, k)


class BaselineStudyTests(unittest.TestCase):
    def test_development_never_needs_confirmation_files(self):
        with tempfile.TemporaryDirectory(dir=study.ROOT / "results") as directory:
            root = Path(directory)
            for name in (study.DEVELOPMENT, "docs/registry.json"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(study.ROOT / name, root / name)
            self.assertEqual(study.development(root), study.development())

    def test_selection_is_development_only_and_has_fixed_tie_rule(self):
        methods = study.development()["methods"]
        self.assertEqual(study.select_method(methods), "bm25")
        altered = copy.deepcopy(methods)
        altered["tfidf"]["summary"]["source_recall"]["1"]["hits"] += 1
        self.assertEqual(study.select_method(altered), "tfidf")

    def test_frozen_files_and_sealed_questions_reject_drift(self):
        result = study.experiment()
        files = list(result["frozen_files"]) + [study.FREEZE, study.QUESTIONS, study.SEAL]
        with tempfile.TemporaryDirectory(dir=study.ROOT / "results") as directory:
            root = Path(directory)
            for name in files:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(study.ROOT / name, root / name)
            study.validate_freeze(root)
            for name in files[:-1]:
                original = (root / name).read_bytes()
                (root / name).write_bytes(original + b"\n")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "changed"):
                    study.validate_freeze(root)
                (root / name).write_bytes(original)

    def test_confirmation_labels_anchors_and_reuse(self):
        manifest, registry, _ = study.validate_freeze()
        fixture = json.loads((study.ROOT / study.QUESTIONS).read_text(encoding="utf-8"))
        study.validate_questions(fixture, manifest, registry, set())
        for change in ("anchor", "reuse", "count", "source", "duplicate"):
            altered = copy.deepcopy(fixture)
            prior = set()
            if change == "anchor":
                source = altered["questions"][0]["expected_sources"][0]
                altered["questions"][0]["anchors"][source] = "invented anchor"
            elif change == "reuse":
                prior.add(altered["questions"][0]["question"].strip().casefold())
            elif change == "count":
                altered["questions"].pop()
            elif change == "source":
                altered["questions"][0]["expected_sources"] = ["unknown"]
            else:
                altered["questions"][1]["id"] = altered["questions"][0]["id"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                study.validate_questions(altered, manifest, registry, prior)

    def test_saved_results_accounting_and_studio(self):
        result = study.experiment()
        saved = json.loads((study.ROOT / "results/AI06-baselines.json").read_text(encoding="utf-8"))
        self.assertEqual(result, saved)
        case = studio.baseline_case()
        self.assertEqual(case["id"], "retrieval-baselines")
        self.assertEqual(len(case["table"]["rows"]), (13 + 14) * 3)
        self.assertIn(result["freeze_sha256"], " ".join(case["method"]))
        for phase in ("development", "confirmation"):
            self.assertEqual(set(result[phase]["methods"]), set(METHODS))
            for method in result[phase]["methods"].values():
                s = method["summary"]
                for k in ("1", "3"):
                    miss = s["source_misses"][k]
                    self.assertEqual(s["source_recall"][k]["hits"] + miss["empty"] + miss["wrong_source"], s["answerable_count"])
                self.assertEqual(s["false_support"]["count"] + s["empty_retrieval"]["unanswerable"], s["unanswerable_count"])


if __name__ == "__main__":
    unittest.main()
