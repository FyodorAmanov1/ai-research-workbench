import unittest
import lab


class RetrievalTests(unittest.TestCase):
    def test_expected_references(self):
        for case in lab.CASES:
            with self.subTest(case=case):
                self.assertEqual(lab.retrieve(case["question"], 1)[0]["id"], case["expected"])

    def test_abstention(self):
        self.assertEqual(lab.answer("volcanology tectonics")["citations"], [])

    def test_citations_are_grounded(self):
        result = lab.answer("amplitude estimation oracle")
        reference = next(d for d in lab.CORPUS if d["id"] == result["citations"][0]["id"])
        self.assertEqual(result["answer"], reference["text"])
        self.assertEqual(result["citations"][0]["url"], reference["url"])

    def test_empty_query(self):
        with self.assertRaises(ValueError):
            lab.retrieve(" ")


if __name__ == "__main__":
    unittest.main()
