// Inspect the saved fault-injection measurement; no remote freshness assertion.
async function initializeFreshness() {
  const panel = document.getElementById("freshness");
  const select = document.getElementById("freshness-scenario");
  const status = document.getElementById("freshness-status");
  const details = document.getElementById("freshness-details");
  const visibility = () => { panel.hidden = location.hash !== "#freshness"; };
  window.addEventListener("hashchange", visibility);
  visibility();
  try {
    const response = await fetch("freshness-study.json");
    if (!response.ok) throw Error("Saved freshness measurement could not be loaded");
    const study = await response.json();
    select.replaceChildren(...study.rows.map(r => new Option(r.scenario, r.scenario)));
    const inspect = () => {
      const row = study.rows.find(r => r.scenario === select.value);
      status.textContent = `Artifact: ${row.status}. Text-only baseline: ${row.text_only_baseline}. ${row.ready ? "Refresh allowed" : "Refresh blocked; active snapshot preserved"}. Exact prior registry retained: ${row.exact_prior_snapshot_retained}.`;
      details.textContent = JSON.stringify(row, null, 2);
    };
    select.addEventListener("change", inspect);
    select.value = "source_metadata_only";
    inspect();
    document.getElementById("freshness-audit-file").addEventListener("change", async event => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        const audit = JSON.parse(await file.text());
        if (!Array.isArray(audit.sources) || typeof audit.ready !== "boolean" ||
            !audit.sources.every(r => typeof r.project === "string" && typeof r.status === "string")) {
          throw Error("Expected a refresh audit with source rows and a readiness decision");
        }
        const matches = audit.old_registry_sha256 === study.registry_sha256;
        status.textContent = `Imported audit (user-provided): ${audit.ready ? "refresh allowed" : "refresh blocked"}. Prior registry fingerprint ${matches ? "matches the bundled study" : "differs from the bundled study"}. This browser does not check current source files or authenticate this audit.`;
        details.textContent = JSON.stringify(audit, null, 2);
      } catch (error) {
        status.textContent = `Could not inspect audit: ${error.message}`;
      }
    });
  } catch (error) {
    status.textContent = `Audit unavailable: ${error.message}`;
    select.disabled = true;
  }
}
initializeFreshness();
