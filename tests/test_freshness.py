import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.freshness import ROOT, encode, refresh, sha
from src.freshness_study import experiment, fixture, mutate
from src.ingest import PROJECTS, ingest


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "results")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "inputs"
        self.registry = fixture(self.workspace)
        self.path = self.base / "registry.json"
        self.original = encode(self.registry)
        self.path.write_bytes(self.original)
        self.archive = self.base / "history"
        self.source = self.workspace / PROJECTS[0] / "docs/study.json"

    def run_refresh(self, out=None):
        return refresh(self.workspace, self.path, out or self.path, self.archive)

    def test_legacy_ingest_and_unchanged_digests(self):
        self.assertEqual(ingest(self.workspace), self.registry)
        report = self.run_refresh()
        self.assertTrue(report["ready"])
        self.assertTrue(all(r["status"] == "unchanged" for r in report["sources"]))
        self.assertEqual((self.archive / report["old_registry_snapshot"]).read_bytes(), self.original)
        self.assertEqual(report["sources"][0]["old_sha256"], sha(self.source.read_bytes()))
        before = self.path.read_bytes()
        self.run_refresh()
        self.assertEqual(self.path.read_bytes(), before)

    def test_metadata_drift_with_unchanged_text_and_preserved_raw(self):
        source_bytes = self.source.read_bytes()
        self.run_refresh()
        mutate(self.source, "source_metadata_only")
        report = self.run_refresh()
        row = report["sources"][0]
        self.assertEqual(row["status"], "stale")
        self.assertNotEqual(row["old_sha256"], row["new_sha256"])
        self.assertTrue(all(c["status"] == "unchanged" for c in row["record_changes"]))
        self.assertEqual((self.archive / row["old_raw_source_snapshot"]).read_bytes(), source_bytes)
        current = json.loads(self.path.read_bytes())
        self.assertEqual([d["id"] for d in current["documents"]], [d["id"] for d in self.registry["documents"]])
        self.assertEqual([d["text"] for d in current["documents"]], [d["text"] for d in self.registry["documents"]])

    def test_removed_ids_and_complete_evidence_still_loadable(self):
        mutate(self.source, "case_removed")
        report = self.run_refresh()
        old = json.loads((self.archive / report["old_registry_snapshot"]).read_bytes())
        self.assertEqual(old, self.registry)
        removed = self.registry["documents"][0]
        self.assertEqual(old["documents"][0], removed)
        self.assertNotIn(removed["id"], [d["id"] for d in json.loads(self.path.read_bytes())["documents"]])
        self.assertIn({"source_id": removed["id"], "status": "removed"}, report["sources"][0]["record_changes"])
        # The public loader accepts a historical snapshot for retrieval/claim use.
        from src.evidence import load_registry, validate_claim
        restored = load_registry(self.archive / report["old_registry_snapshot"])
        m = removed["metrics"][0]
        self.assertTrue(validate_claim(restored, removed["id"], m["label"], m["value"], m["unit"])["accepted"])

    def test_blocked_sources_never_replace_active_or_candidate(self):
        for scenario, status in [("missing", "missing"), ("malformed_json", "invalid"),
                                 ("wrong_project", "invalid"), ("duplicate_case_id", "invalid")]:
            with self.subTest(scenario=scenario):
                fixture(self.workspace)
                mutate(self.source, scenario)
                out = self.base / "candidate.json"
                out.write_bytes(b"existing candidate")
                report = self.run_refresh(out)
                self.assertFalse(report["ready"])
                self.assertEqual(report["sources"][0]["status"], status)
                self.assertEqual(self.path.read_bytes(), self.original)
                self.assertEqual(out.read_bytes(), b"existing candidate")
                self.assertIsNone(report["new_registry_sha256"])

    def test_missing_prior_digest_and_raw_availability_are_explicit(self):
        mutate(self.source, "metric_edit")
        report = self.run_refresh()
        self.assertFalse(report["sources"][0]["old_raw_source_available"])
        for d in self.registry["documents"]:
            if d["project"] == PROJECTS[0]:
                d.pop("artifact_sha256")
        self.path.write_bytes(encode(self.registry))
        before = self.path.read_bytes()
        report = self.run_refresh()
        self.assertEqual(report["sources"][0]["status"], "unverifiable")
        self.assertFalse(report["ready"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_project_retains_digest_for_later_refresh(self):
        study = json.loads(self.source.read_bytes())
        study["cases"] = []
        self.source.write_bytes(encode(study))
        self.assertTrue(self.run_refresh()["ready"])
        second = self.run_refresh()
        self.assertTrue(second["ready"])
        self.assertEqual(second["sources"][0]["status"], "unchanged")

    def test_corrupt_history_refuses_overwrite_before_publication(self):
        target = self.archive / "registries" / f"{sha(self.original)}.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"corrupt history")
        with self.assertRaisesRegex(ValueError, "refusing overwrite"):
            self.run_refresh()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(target.read_bytes(), b"corrupt history")

    def test_nonfinite_or_malformed_metric_blocks_refresh(self):
        for bad in (True, "1", float("inf")):
            fixture(self.workspace)
            study = json.loads(self.source.read_bytes())
            study["cases"][0]["metrics"][0]["value"] = bad
            self.source.write_text(json.dumps(study), encoding="utf-8")
            self.assertEqual(self.run_refresh()["sources"][0]["status"], "invalid")
            self.assertEqual(self.path.read_bytes(), self.original)

    def test_existing_ingest_cli_archives_instead_of_silent_overwrite(self):
        mutate(self.source, "metric_edit")
        run = subprocess.run([sys.executable, str(ROOT / "src/ingest.py"), "--workspace", str(self.workspace),
                              "--out", str(self.path), "--archive", str(self.archive)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["sources"][0]["status"], "stale")
        self.assertEqual((self.archive / report["old_registry_snapshot"]).read_bytes(), self.original)

    def test_refresh_cli_blocks_missing_source_and_keeps_report(self):
        self.source.unlink()
        output, audit = self.base / "candidate.json", self.base / "audit.json"
        run = subprocess.run([sys.executable, "-m", "src.freshness", "--workspace", str(self.workspace),
                              "--registry", str(self.path), "--out", str(output),
                              "--archive", str(self.archive), "--report", str(audit)],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertEqual(json.loads(audit.read_bytes())["sources"][0]["status"], "missing")
        self.assertFalse(output.exists())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_measured_baseline_and_studio_case(self):
        result = experiment()
        self.assertEqual(result["summary"], {"scenarios": 10, "decisions_matching_specification": 10,
                         "changed_artifacts": 5, "digest_changes_detected": 5,
                         "text_only_changes_detected": 3, "prior_snapshots_retained": 10, "blocked_refreshes": 4})
        self.assertTrue(all(r["blocked_refresh_preserved_active"] for r in result["rows"]))
        from src.studio import freshness_case
        self.assertEqual(freshness_case()["id"], "freshness")
        self.assertEqual(len(freshness_case()["table"]["rows"]), 10)
        self.assertEqual(json.loads((ROOT / "results/AI03-freshness.json").read_bytes()), result)
        self.assertEqual((ROOT / "results/AI03-freshness.json").read_bytes(),
                         (ROOT / "docs/freshness-study.json").read_bytes())

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_browser_saved_scenario_and_local_audit_inspection(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const nodes = {};
global.document = {getElementById(id) {
  return nodes[id] ||= {hidden: false, value: '', textContent: '', handlers: {},
    addEventListener(name, fn) {this.handlers[name] = fn;},
    replaceChildren(...children) {this.children = children;}};
}};
global.location = {hash: '#freshness'};
global.window = {addEventListener() {}};
global.Option = function(text, value) {return {text, value};};
const study = JSON.parse(fs.readFileSync('docs/freshness-study.json', 'utf8'));
global.fetch = async () => ({ok: true, json: async () => study});
vm.runInThisContext(fs.readFileSync('docs/freshness.js', 'utf8').replace(/initializeFreshness\(\);\s*$/, ''));
(async () => {
  await initializeFreshness();
  assert.equal(nodes.freshness.hidden, false);
  assert.equal(nodes['freshness-scenario'].children.length, 10);
  assert.equal(JSON.parse(nodes['freshness-details'].textContent).scenario, 'source_metadata_only');
  nodes['freshness-scenario'].value = 'missing';
  nodes['freshness-scenario'].handlers.change();
  assert(nodes['freshness-status'].textContent.includes('blocked'));
  const audit = {ready: false, old_registry_sha256: study.registry_sha256,
    sources: [{project: 'fixture', status: 'missing'}]};
  await nodes['freshness-audit-file'].handlers.change({target: {files: [{text: async () => JSON.stringify(audit)}]}});
  assert(nodes['freshness-status'].textContent.includes('matches the bundled study'));
  assert.deepEqual(JSON.parse(nodes['freshness-details'].textContent), audit);
  await nodes['freshness-audit-file'].handlers.change({target: {files: [{text: async () => '{}'}]}});
  assert(nodes['freshness-status'].textContent.includes('Could not inspect audit'));
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        run = subprocess.run([shutil.which("node"), "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
