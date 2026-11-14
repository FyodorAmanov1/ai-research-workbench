// Separate from the frozen lexical retrieval implementation.
function structuredQuery(registry, snapshot, query) {
  let sources = [];
  const fail = (code, message) => ({status: "error", code, message, sources, registry_sha256: snapshot.registry_sha256});
  if (!query || typeof query !== "object" || Array.isArray(query)) return fail("invalid_query", "Query must be a JSON object");
  const fields = {project: ["kind", "project_id"], experiment: ["kind", "project_id", "experiment_id"], metric: ["kind", "project_id", "experiment_id", "metric_label"]};
  const kind = query.kind;
  if (typeof kind !== "string" || !Object.hasOwn(fields, kind)) return fail("invalid_query", "kind must be project, experiment or metric");
  if (Object.keys(query).some(k => !fields[kind].includes(k))) return fail("invalid_query", "Unknown query fields");
  const required = {project: [], experiment: ["project_id"], metric: ["project_id", "experiment_id"]}[kind];
  const q = {kind};
  for (const field of fields[kind].filter(k => k !== "kind")) {
    const value = query[field] ?? null;
    if ((required.includes(field) || value !== null) && (typeof value !== "string" || !value.trim())) return fail("invalid_query", field + " must be a nonempty string");
    q[field] = value;
  }
  let docs = registry.documents;
  if (q.project_id !== null) {
    docs = docs.filter(d => d.project === q.project_id);
    if (!docs.length) return fail("unknown_project", "Project is absent from this snapshot");
  }
  if (kind !== "project" && q.experiment_id !== null) {
    docs = docs.filter(d => d.id === q.project_id + ":" + q.experiment_id);
    if (!docs.length) return fail("unknown_experiment", "Experiment is absent from the selected project");
  }
  docs = [...docs].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  sources = docs.map(d => snapshot.sources.find(s => s.source_id === d.id));
  let data;
  if (kind === "project") {
    data = [...new Set(docs.map(d => d.project))].sort().map(p => ({project_id: p, experiment_ids: docs.filter(d => d.project === p).map(d => d.id.slice(p.length + 1))}));
  } else if (kind === "experiment") {
    data = docs.map(d => ({project_id: d.project, experiment_id: d.id.slice(d.project.length + 1), source_id: d.id, title: d.title, metric_labels: d.metrics.map(m => m.label)}));
  } else {
    data = docs.flatMap(d => d.metrics.filter(m => q.metric_label === null || m.label === q.metric_label).map(m => ({source_id: d.id, ...m})));
    if (!data.length) return fail("unknown_metric", "Metric is absent from the selected experiment");
  }
  return JSON.parse(JSON.stringify({status: "ok", code: "ok", query: q, data, sources, registry_sha256: snapshot.registry_sha256}));
}

async function initializeStructuredQuery() {
  const el = id => document.getElementById(id);
  const visible = () => { el("structured-query").hidden = location.hash !== "#structured-query"; };
  window.addEventListener("hashchange", visible);
  visible();
  try {
    const responses = await Promise.all([fetch("registry.json"), fetch("study.json")]);
    if (responses.some(r => !r.ok)) throw Error("Saved query artifacts unavailable");
    const raw = await responses[0].arrayBuffer();
    const study = await responses[1].json();
    const snapshot = study.cases.find(c => c.id === "structured-query").query_snapshot;
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", raw)), b => b.toString(16).padStart(2, "0")).join("");
    if (digest !== snapshot.registry_sha256) throw Error("Registry differs from the query snapshot; regenerate the study");
    const registry = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(raw));
    if (registry.documents.some(d => snapshot.sources.filter(s => s.source_id === d.id && s.sha256 === d.sha256 && s.artifact_sha256 === d.artifact_sha256).length !== 1)) throw Error("Source boundary missing from study snapshot");
    const fill = (id, values) => el(id).replaceChildren(...values.map(value => new Option(value, value)));
    fill("sq-projects", [...new Set(registry.documents.map(d => d.project))].sort());
    const options = () => {
      const kind = el("sq-kind").value, project = el("sq-project").value;
      el("sq-experiment").disabled = kind === "project";
      el("sq-metric").disabled = kind !== "metric";
      fill("sq-experiments", registry.documents.filter(d => d.project === project).map(d => d.id.slice(project.length + 1)));
      const doc = registry.documents.find(d => d.id === project + ":" + el("sq-experiment").value);
      fill("sq-metrics", doc ? doc.metrics.map(m => m.label) : []);
    };
    for (const id of ["sq-kind", "sq-project", "sq-experiment"]) el(id).addEventListener("input", options);
    const run = event => {
      event?.preventDefault();
      const kind = el("sq-kind").value;
      const query = {kind, project_id: el("sq-project").value || null};
      if (kind !== "project") query.experiment_id = el("sq-experiment").value || null;
      if (kind === "metric") query.metric_label = el("sq-metric").value || null;
      const result = structuredQuery(registry, snapshot, query);
      el("sq-status").textContent = result.status === "ok" ? `Returned ${result.data.length} saved ${kind} record(s).` : `${result.code}: ${result.message}`;
      el("sq-result").textContent = JSON.stringify(result, null, 2);
    };
    el("structured-query-form").addEventListener("submit", run);
    el("sq-unknown").onclick = () => {
      el("sq-kind").value = "metric"; el("sq-project").value = "quantum-estimation-lab";
      el("sq-experiment").value = "risk-1"; el("sq-metric").value = "99% value at risk confidence interval";
      options(); run();
    };
    options(); run();
  } catch (error) {
    el("sq-status").textContent = `Query unavailable: ${error.message}`;
    el("structured-query-form").querySelectorAll("button").forEach(b => { b.disabled = true; });
  }
}
initializeStructuredQuery();
