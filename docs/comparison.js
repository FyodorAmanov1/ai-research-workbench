// Comparison is separate from the frozen retrieval implementation.
function compareMetrics(registry, contracts, leftSource, leftMetric, rightSource, rightMetric) {
  const reject = (code, reason) => ({accepted: false, code, reason});
  const resolved = [];
  for (const [side, source, label] of [["Left", leftSource, leftMetric], ["Right", rightSource, rightMetric]]) {
    const documents = registry.documents.filter(d => d.id === source);
    if (documents.length !== 1) return reject(documents.length ? "ambiguous_source" : "unknown_source", `${side}: source ID must identify exactly one record`);
    const document = documents[0];
    const metrics = (document.metrics || []).filter(m => m.label === label);
    if (metrics.length !== 1) return reject(metrics.length ? "ambiguous_metric" : "unknown_metric", `${side}: metric label must identify exactly one registered metric`);
    const item = metrics[0];
    if (typeof item.value !== "number" || !Number.isFinite(item.value)) return reject("non_numeric", `${side}: metric must be a finite number (booleans excluded)`);
    if (typeof item.unit !== "string") return reject("missing_unit", `${side}: explicit unit string required`);
    resolved.push([document, item]);
  }
  if (resolved[0][1].unit !== resolved[1][1].unit) return reject("unit_mismatch", "Unit mismatch: exact strings required; no implicit conversion");
  const evidence = [];
  for (const [document, item] of resolved) {
    const entries = (contracts.metrics || []).filter(c => c.source_id === document.id && c.label === item.label);
    if (entries.length !== 1) return reject("missing_metadata", "Exactly one reviewed comparison contract is required for each metric");
    const entry = entries[0];
    for (const field of ["dataset_id", "protocol_id", "quantity_id"]) {
      if (typeof entry[field] !== "string" || !entry[field].trim()) return reject("missing_metadata", `Missing comparison metadata: ${field}`);
    }
    if (entry.artifact_sha256 !== document.artifact_sha256 || entry.sha256 !== document.sha256 || entry.value !== item.value || entry.unit !== item.unit) return reject("stale_contract", "Comparison contract does not match the recorded metric and source fingerprints");
    evidence.push({...entry, url: document.url});
  }
  for (const [field, code, name] of [["dataset_id", "dataset_mismatch", "Dataset"], ["protocol_id", "protocol_mismatch", "Protocol"], ["quantity_id", "quantity_mismatch", "Quantity"]]) {
    if (evidence[0][field] !== evidence[1][field]) return reject(code, `${name} mismatch: ${evidence[0][field]} versus ${evidence[1][field]}`);
  }
  const difference = resolved[0][1].value - resolved[1][1].value;
  if (!Number.isFinite(difference)) return reject("non_finite_difference", "Difference exceeds finite numeric range");
  return {accepted: true, code: "compatible", reason: "Units, dataset, evaluation protocol and quantity match", difference, operation: "left minus right", unit: evidence[0].unit, left: evidence[0], right: evidence[1]};
}

async function initializeComparisons() {
  const el = id => document.getElementById(id);
  const panel = el("comparisons");
  const visibility = () => { panel.hidden = location.hash !== "#comparisons"; };
  window.addEventListener("hashchange", visibility);
  visibility();
  try {
    const responses = await Promise.all([fetch("registry.json"), fetch("comparison-contracts.json")]);
    if (responses.some(r => !r.ok)) throw Error("Comparison artifacts could not be loaded");
    const [registryText, contractsText] = await Promise.all(responses.map(r => r.text()));
    const registry = JSON.parse(registryText), contracts = JSON.parse(contractsText);
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(registryText));
    const hash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
    if (hash !== contracts.registry_sha256) throw Error("Comparison registry fingerprint mismatch; review contracts before reuse");
    const fill = (select, rows) => select.replaceChildren(...rows.map(([value, text]) => new Option(text, value)));
    for (const side of ["left", "right"]) {
      const source = el(`comparison-${side}-source`), metric = el(`comparison-${side}-metric`);
      fill(source, registry.documents.map(d => [d.id, d.id]));
      source.value = "statistical-learning-lab:stationary";
      const update = () => fill(metric, registry.documents.find(d => d.id === source.value).metrics.map(m => [m.label, m.label]));
      source.addEventListener("change", update);
      update();
      metric.value = side === "left" ? "Expanding ridge MAE" : "Frozen ridge MAE";
    }
    const compare = event => {
      event?.preventDefault();
      const selection = ["left-source", "left-metric", "right-source", "right-metric"].map(s => el(`comparison-${s}`).value);
      const result = compareMetrics(registry, contracts, ...selection);
      el("comparison-status").textContent = result.accepted ? `Accepted. Left minus right = ${result.difference} ${result.unit}. ${result.reason}.` : `Rejected (${result.code}). ${result.reason}. No difference computed.`;
      const details = el("comparison-evidence");
      details.replaceChildren();
      for (const [side, source, label] of [["Left", selection[0], selection[1]], ["Right", selection[2], selection[3]]]) {
        const d = registry.documents.find(d => d.id === source), m = d.metrics.find(m => m.label === label);
        const c = contracts.metrics.find(c => c.source_id === source && c.label === label);
        const block = document.createElement("details"), summary = document.createElement("summary"), link = document.createElement("a"), text = document.createElement("pre");
        summary.textContent = `${side}: ${source} / ${label} = ${m.value} ${m.unit}`;
        link.textContent = "Inspect source artifact"; link.href = d.url; link.target = "_blank"; link.rel = "noreferrer";
        text.textContent = JSON.stringify(c || {status: "No reviewed comparison metadata", source_id: d.id, sha256: d.sha256, artifact_sha256: d.artifact_sha256}, null, 2);
        text.style.whiteSpace = "pre-wrap"; text.style.overflowWrap = "anywhere";
        block.append(summary, link, text); details.append(block);
      }
    };
    el("comparison-form").addEventListener("submit", compare);
    compare();
  } catch (error) {
    el("comparison-status").textContent = `Comparison unavailable: ${error.message}`;
    el("comparison-form").querySelector("button").disabled = true;
  }
}
initializeComparisons();
