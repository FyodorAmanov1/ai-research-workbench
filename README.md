# Research Evidence Observatory

**Find the experiment behind a research claim, inspect the exact metric and carry its source context into a larger analysis.**

Research Evidence Observatory turns companion research artifacts into a small searchable evidence collection. The browser and Python tools retrieve recorded experiments, display their methods and limitations, and check numerical claims against typed source metrics.

[Open the evidence explorer](https://fyodoramanov1.github.io/ai-research-workbench/)

## From experiment to evidence

```text
Companion study artifacts → source registry → BM25 retrieval
                                          → metric verification
                                          → bounded context export
```

The bundled registry contains ten case records from four quantitative and quantum research projects. Each record carries a source identifier, artifact URL, source-artifact SHA-256, text hash, methods, limitations and typed metrics.

- **Search:** BM25 ranking with matching Python and browser implementations.
- **Inspect:** source-linked evidence cards and the recorded numerical values.
- **Verify:** check a source, metric name, value and unit together.
- **Compare:** subtract registered metrics only after units, dataset, evaluation protocol and quantity match; inspect explicit rejection reasons.
- **Export:** build a character-bounded evidence context for use by another tool or model.

The application does not generate answers with an LLM. Retrieval and typed verification remain explicit operations, making it possible to examine where a proposed claim came from.

## What verification means here

A claim must name an existing source and metric, match the metric's unit and agree numerically within the configured tolerance. Unknown sources, mismatched units and incorrect values are rejected.

This checks agreement with the saved artifact. It does not prove that the experiment is scientifically correct, establish the meaning of an arbitrary sentence or provide tamper-proof provenance if both content and hashes are replaced.

## Recorded diagnostic results

The included 13 authored retrieval fixtures contain ten expected-source questions, two unrelated questions and one misleading guaranteed-profit question. Twelve behave as expected. The misleading question still retrieves related evidence because it shares vocabulary with the collection.

That failure is useful: **lexical relevance does not establish support for a claim**. These fixtures are regression examples, not an independent held-out retrieval benchmark. Five separate numerical claim probes exercise one accepted claim and four rejected cases.

The saved context example contains **7,522 characters**, below the default 8,000-character cap. Character limits make exports predictable but do not measure token use or reasoning quality.

## Frozen retrieval confirmation

The [confirmation study](reports/AI01.md) freezes the ten-record registry, Python and browser retrieval implementations, BM25 settings and evaluation protocol before authoring 30 new questions. The question set is sealed before evaluation; drift in the inputs causes evaluation to fail. No rules or labels were tuned on these outcomes.

| Measure | BM25 | Unique-term overlap baseline |
| --- | --- | --- |
| Source recall at 1 (20 answerable questions) | 20/20 | 18/20 |
| Source recall at 3 (20 answerable questions) | 20/20 | 20/20 |
| False support proxy (10 unanswerable questions) | 6/10 | 6/10 |
| Empty retrieval on unanswerable questions | 4/10 | 4/10 |
| Empty retrieval on answerable questions | 0/20 | 0/20 |

All six misleading lexical overlaps retrieve related records despite lacking an answer. All four unrelated questions return nothing. False support here means **any retrieval on a labelled unanswerable question**, not generated-answer error. These source-aware authored questions test fixed rules; they do not estimate real-world accuracy.

Open the **Frozen retrieval confirmation** case in the explorer to compare rankings, label rationales and outcomes, or inspect [the full measured artifact](results/AI01-confirmation.json). Reproduce with:

```bash
python -m src.confirmation --output results/AI01-confirmation.json
python lab.py --output results/latest.json
python src/studio.py --out docs/study.json
python src/studio.py --check docs/study.json
python -m unittest discover -s tests -v
```

## Independent confirmation questions

The [second confirmation wave](reports/AI04.md) freezes the current registry, Python/browser retrievers, baseline and evaluator before authoring 28 additional questions, then seals all questions and labels before evaluation. Open **Independent confirmation questions** (`#independent-confirmation`) to inspect both rankings, expected-source rank, exact source anchors and separate miss/unsupported charts.

| Measure | BM25 | Unique-term overlap |
| --- | --- | --- |
| Source recall at 1, answerable only | 19/20 | 16/20 |
| Source recall at 3, answerable only | 20/20 | 20/20 |
| Wrong-source misses at 1 | 1/20 | 4/20 |
| Empty answerable retrieval | 0/20 | 0/20 |
| Unsupported false support proxy | 4/8 | 4/8 |
| Empty unsupported retrieval | 4/8 | 4/8 |

Both methods rank the directional-market source third for a question using “one-sided” order flow. Both return records for all four absent measurements with overlapping vocabulary; four unrelated topics return nothing. Better source ranking still does not establish answer support. These are source-aware authored questions, with earlier results visible, not blinded or representative user samples. The new wave's aggregate unsupported rate must not be interpreted as an improvement over the earlier question mixture.

```bash
python -m src.independent_confirmation --output results/AI04-confirmation.json
python lab.py --output results/latest.json
python src/studio.py --out docs/study.json
python src/studio.py --check docs/study.json
python -m unittest discover -s tests -v
```

The [measured ledger](results/AI04-confirmation.json) separately records source recall, wrong-source and empty misses at each cutoff, unsupported false support and empty unsupported retrieval. The earlier confirmation protocol remains reproducible.

## Compatible experiment comparisons

Open **Compatible experiment comparisons** in the explorer (`#comparisons`) to choose two records and metrics. Accepted results show left minus right and both source contracts; incompatible pairs show a rejection reason without a numerical difference. Values come from registered metrics, with exact unit strings and reviewed dataset, evaluation protocol and quantity identities. Missing metadata fails closed. The frozen retrieval registry and rules are preserved.

The [comparison study](reports/AI02.md) asks whether expanding ridge lowers recorded test MAE against frozen ridge on the same synthetic test case. It does not: expanding minus frozen MAE is **+0.0007540725** in the stable case and **+0.6479200085** after the shift. These are saved point estimates, without significance or real-market claims. Cross-regime comparisons are rejected because their datasets differ.

Seven authored probes produce two compatible comparisons and five explicit rejections. An exact-unit-only baseline incorrectly admits four incompatible pairs; the contract gate admits none. Sixteen of forty registry metrics have reviewed metadata; remaining metrics are unavailable for comparison. Dataset identities describe saved cases, not independently verified raw-sample hashes.

```bash
python -m src.comparison --output results/AI02-comparisons.json
python -m src.comparison --left-source statistical-learning-lab:stationary --left-metric "Expanding ridge MAE" --right-source statistical-learning-lab:stationary --right-metric "Frozen ridge MAE"
python lab.py --output results/latest.json
python src/studio.py --out docs/study.json
python src/studio.py --check docs/study.json
python -m unittest discover -s tests -v
```

Python callers can use `load_inputs()` and `compare_metrics(registry, contracts, left_source, left_metric, right_source, right_metric)` from [src/comparison.py](src/comparison.py). Use the loader to verify the registry fingerprint. [Comparison contracts](docs/comparison-contracts.json) bind selected values, units and source fingerprints. Registry changes require new reviewed contracts; frozen retrieval changes require a new retrieval protocol.

## Registry freshness and retained history

Open **Registry freshness audit** (`#freshness`) to inspect ten controlled refresh scenarios, old/new source digests, case IDs and retention checks. The text-only baseline detects **3/5** changed artifacts; checking the complete source-artifact SHA-256 detects **5/5**, including source metadata outside indexed text and formatting changes. All **10/10** exact prior registry snapshots are retained; four unavailable or invalid inputs block replacement. These are synthetic fault injections around the ten saved evidence records, not a survey of current remote repositories. See [AI03](reports/AI03.md).

Refresh only an explicitly supplied directory containing the four named companion study artifacts:

```bash
python -m src.freshness --workspace SOURCE_DIRECTORY --registry docs/registry.json --out results/refreshed-registry.json --archive results/registry-history --report results/refresh-audit.json
```

The default writes a separate candidate; missing, malformed, wrong-project, duplicate-case or unverifiable prior digests block replacement (exit code 2). Successful refresh reports unchanged/stale source bytes and added/changed/removed IDs. The exact prior registry, observed raw source bytes, candidate and audit are stored under SHA-256 names in history before replacement. Load an old registry with the existing `load_registry(snapshot_path)` to reproduce retrieval or claim checks against removed IDs. Previously unavailable original source bytes cannot be recovered from the registry; `old_raw_source_available` reports that boundary explicitly. Hashes detect drift, not authenticity or scientific validity.

The existing `python src/ingest.py --workspace SOURCE_DIRECTORY --out REGISTRY_PATH` remains supported. When its output already exists it now performs this audit and archives history before replacement; a new output still performs initial ingestion. Prefer the separate-candidate refresh command for frozen studies: the current confirmation protocol and comparison contracts intentionally reject changed registries. Stable case IDs keep their identity; versions are distinguished by registry and artifact digests. Import a generated audit JSON in the studio to inspect it locally; imported reports are user-provided and do not establish live freshness.

```bash
python -m src.freshness_study --output results/AI03-freshness.json
python lab.py --output results/latest.json
python src/studio.py --out docs/study.json
python src/studio.py --check docs/study.json
python -m unittest discover -s tests -v
```

The browser ledger copy is `docs/freshness-study.json`; copy the measured `results/AI03-freshness.json` there after rerunning that measurement.

## Structured project, experiment and metric queries

Open **Structured query tool** (`#structured-query`) to list projects or experiments, fetch exact metrics, or try an absent measurement. Editable selectors offer known IDs and labels while allowing unknown requests. Responses distinguish `unknown_project`, `unknown_experiment` and `unknown_metric`; missing data is never replaced by zero or a nearby search result.

```python
from src.structured_query import QueryTool, ProjectQuery, ExperimentQuery, MetricQuery

tool = QueryTool.from_path()
tool.execute(ProjectQuery())  # list projects
tool.execute(ExperimentQuery("statistical-learning-lab"))  # list experiments
result = tool.execute(MetricQuery("statistical-learning-lab", "stationary", "Frozen ridge MAE"))
print(result["data"][0])
```

Selectors are case-sensitive. Experiment IDs are local to a project (`stationary`, not the full source ID). Omit an optional selector or supply JSON `null` to list its scope; blank strings, wrong types and extra fields return `invalid_query`. Project is required for experiment queries; project and experiment are required for metric queries. The CLI accepts the same JSON shape and exits 2 on errors:

```bash
python -m src.structured_query --query '{"kind":"metric","project_id":"statistical-learning-lab","experiment_id":"stationary","metric_label":"Frozen ridge MAE"}'
python -m src.query_study --output results/AI05-queries.json
```

Every response from a loaded tool includes the exact registry-byte SHA-256. Successful queries also include source IDs, URLs, source-artifact and indexed-text hashes, plus a complete-record hash covering metrics and metadata. Unknown metric errors retain selected source references and return no `data`. Invalid or unreadable registries raise `QueryError` in Python and produce structured CLI errors. Hashes identify snapshots, not authenticity, remote freshness or scientific validity.

The [AI05 study](reports/AI05.md) measures 12 authored probes: six known requests return expected saved data and six absent requests return explicit errors without values. BM25 returns related records for all six absent requests and empty retrieval for none. This compares an exact-selector contract with the risk of interpreting lexical results as answers; it does not estimate natural-language understanding or deployment accuracy. Zero violations and negative policy improvement remain intact. See [the measured ledger](results/AI05-queries.json).

## Use locally

Use Python 3.12 and install [requirements.txt](requirements.txt) in an activated virtual environment. Serve the bundled application:

```bash
python -m pip install -r requirements.txt
python -m http.server 8000 --directory docs
```

Open <http://localhost:8000>. Search and export from Python with:

```bash
python src/evidence.py --query "fermionic double occupancy"
python src/evidence.py --query "quantum portfolio risk" --context --max-chars 8000
```

To rebuild the registry, place the four companion repositories named in [src/ingest.py](src/ingest.py) in one directory and pass that directory to `python src/ingest.py --workspace <directory>`. The bundled registry can be explored without that workspace.

## Code and evidence

- [Retrieval and claim verification](src/evidence.py)
- [Source ingestion](src/ingest.py)
- [Recorded study](docs/study.json)
- [Applied report](reports/applied-study.md) and [references](REFERENCES.md)
- [MIT license](LICENSE)
