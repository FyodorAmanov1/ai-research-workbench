# Applied case study: Research Evidence Observatory

## Research question

Build an evidence-driven AI research interface around actual experiment artifacts, with inspectable provenance and bounded integration.

## Reproduce

`python src/studio.py --out docs/study.json`

## Evidence explorer

Search actual experiment records across four public research projects. Every result carries its source URL, content digest, measured metrics and limitations. No model or API is called by this offline explorer.

### Method

A portable JSON registry snapshots public study artifacts. Each record contains source repository, experiment ID, source-artifact SHA-256, content SHA-256, typed metrics, methods and limitations.

BM25 term weighting (k₁=1.2, b=0.75) ranks original experiment records. Ties use source ID. Empty lexical support causes abstention; scores are relevance weights, not confidence probabilities.

The browser performs the same deterministic retrieval locally. Python provides an extractive answer interface and a bounded JSON context adapter for an already running model session. Neither path creates a model session or spends tokens.

### Measured comparison

| Question | Expected source | Top result | Correct at rank 1 |
| --- | --- | --- | --- |
| tail exposure option book | quantum-estimation-lab:risk-1.0 | quantum-estimation-lab:risk-1 | False |
| stressed annual volatility derivatives | quantum-estimation-lab:risk-1.8 | quantum-estimation-lab:risk-1.8 | True |
| Grover oracle preparation calls | quantum-estimation-lab:amplitude | quantum-estimation-lab:amplitude | True |
| exactly three holdings turnover | quantum-optimization-lab:allocation | quantum-optimization-lab:allocation | True |
| fermionic electron double occupancy | quantum-optimization-lab:electrons | quantum-optimization-lab:electrons | True |
| informed flow latency | market-microstructure-lab:adverse | market-microstructure-lab:adverse | True |
| directional market inventory | market-microstructure-lab:trend | market-microstructure-lab:trend | True |
| balanced flow cancellations | market-microstructure-lab:balanced | market-microstructure-lab:balanced | True |
| volatility regime break coverage | statistical-learning-lab:shift | statistical-learning-lab:shift | True |
| stable regime chronological calibration | statistical-learning-lab:stationary | statistical-learning-lab:stationary | True |
| volcanology tectonic magma | ABSTAIN | ABSTAIN | True |
| medieval manuscript paleography | ABSTAIN | ABSTAIN | True |

### Limits

- Twelve authored regression questions are small development fixtures, not an independent held-out benchmark. Failed queries remain in the table.
- Lexical relevance does not prove that evidence supports an arbitrary claim. No semantic answer correctness or hallucination rate is estimated.
- Snapshots can become stale. Source artifact digests identify exactly which local public report was ingested; re-ingestion is explicit. Registry hashes detect accidental edits, not a malicious party able to rewrite both data and hashes.

## Claim audit & integration

A numeric claim must name an existing experiment, a recorded metric, its exact unit and a matching value. Export source-labelled context for evidence-based analysis.

### Method

Claim validation uses exact source IDs and metric labels, exact unit strings and numeric isclose tolerance 10⁻⁶ relative / 10⁻⁸ absolute. It never changes units implicitly.

Source text is serialized as JSON evidence under a data-only header. Context export is capped at 8,000 characters by default and accepts a bounded 500–32,000-character setting. Complete records are included; records are not silently truncated.

The adapter exports bounded, source-labelled evidence for research analysis. It does not invoke an external model provider.

### Measured comparison

| Probe | Accepted | Reason |
| --- | --- | --- |
| Correct value and unit | True | Matches a recorded typed metric |
| Changed numeric value | False | Numeric value mismatch |
| Wrong unit | False | Unit mismatch |
| Unknown evidence | False | Unknown source ID |
| Unknown label | False | Unknown metric label |

### Limits

- Matching a recorded number verifies transcription only. It does not validate the underlying study or establish causality, profitability or quantum advantage.
- Five specified claim probes demonstrate interface behavior, not robustness to all adversarial inputs. JSON boundaries and instructions do not guarantee an LLM will resist prompt injection.
- The browser and CLI use deterministic retrieval and do not generate prose using an LLM.

## Concepts to explain in an interview

Explain the objective and units, where each baseline obtains its information, what was fixed before evaluation, how costs and uncertainty were measured, and one failure the model cannot capture. Reproduce the data before presenting a number; distinguish an implementation demonstration from a validated research conclusion.

## Next work

- Freeze retrieval rules, then author independent confirmation questions and report false support separately from empty retrieval.
- Add compatible experiment comparisons that reject unit, dataset and protocol mismatches.
- Add explicit registry refresh and stale-artifact diagnostics while retaining source IDs and full evidence boundaries.
