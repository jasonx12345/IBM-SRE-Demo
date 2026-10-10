"use strict";
const $ = (id) => document.getElementById(id);
const presets = {conflict: ["queue-depth", "worker-lag"], delay: ["checkout-latency"], clean: ["cache-evictions"], unknown: ["disk-usage"]};
const state = {dataset: null, report: null, selected: new Set(), delay: 5, request: 0, controller: null};
const number = (value) => new Intl.NumberFormat("en", {maximumFractionDigits: 1}).format(value);
const recorded = () => state.dataset?.source.event_kind === "recorded_alert";
const ibm = () => recorded() && state.dataset.source.url === "https://huggingface.co/datasets/ibm-research/ITBench-Lite";
const units = () => recorded() ? "episodes" : "pages";
const cases = () => state.dataset?.source.incident_kind === "benchmark_scenario" ? "scenarios" : "incidents";
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function error(message) { $("error").textContent = message; $("error").hidden = !message; }
function setPreset(active) {
  document.querySelectorAll("[data-preset]").forEach((button) => {
    const selected = button.dataset.preset === active;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}
function renderDataset() {
  const data = state.dataset;
  $("source-badge").textContent = data.source.synthetic ? "SYNTHETIC DATA" : ibm() ? "IBM RECORDED DATA" : "IMPORTED HISTORY";
  $("source-label").textContent = data.source.label;
  $("source-description").textContent = data.source.description;
  const date = (value) => new Date(value).toLocaleDateString("en", {month: "short", day: "numeric", year: "numeric", timeZone: "UTC"});
  $("window-label").textContent = `${date(data.window.start)} → ${date(data.window.end)}`;
  $("data-note").textContent = data.source.synthetic ? "Authored examples. No customer or IBM data." : ibm() ? "IBM Research ITBench-Lite · Apache-2.0 · controlled experiments" : "Imported locally for this session. Completeness is user-declared.";
  $("ibm-evidence").hidden = !ibm();
  $("benchmark-actions").hidden = !ibm();
  $("synthetic-actions").hidden = !data.source.synthetic;
  if (ibm()) {
    const counts = data.provenance?.import_counts;
    $("import-summary").textContent = counts ? `${counts.snapshot_files} snapshots → ${data.events.length} distinct alert episodes across ${data.incidents.length} experiments. ${counts.duplicate_rows} repeated observations collapsed; ${counts.excluded_rows} pending or non-warning/critical rows excluded. Ground-truth matches require alert name, namespace and service.` : "Source metadata supplied by the importer.";
    $("window-label").textContent = `${data.incidents.length} experiment captures · ${date(data.window.start)}`;
  }
  $("removed-label").textContent = recorded() ? "Alert episodes removed" : "Page events removed";
  $("lost-label").textContent = `${cases() === "scenarios" ? "Scenarios" : "Incidents"} losing all warnings`;
  $("incidents-heading").textContent = cases() === "scenarios" ? "Experiment replay" : "Incident replay";
  $("policy-help").textContent = recorded() ? "Remove an alert scope across both captures. Each scope includes name, namespace, service, job and severity; it is not a verified rule configuration. Each row shows the result of removing it alone." : "Select paging rules to remove. Each row shows the result of removing it alone.";
  $("delay-label").textContent = recorded() ? "Allowed extra observed delay" : "Allowed extra first-page delay";
  $("timeline-help").textContent = recorded() ? "Expand a scenario to see ground-truth-matched alerts and source records. Times are relative to the first observed firing snapshot, not fault onset or pager delivery." : "Expand an incident to see the original page sequence and what remains. Times are relative to its original first page.";
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.disabled = !presets[button.dataset.preset].every((id) => data.alerts.some((alert) => alert.id === id)) || !data.source.synthetic;
  });
}
function renderCandidates(report) {
  const focusId = document.activeElement?.dataset?.alert;
  const fragment = document.createDocumentFragment();
  const candidates = recorded() ? [...report.candidates].sort((a, b) => Number(b.linked_events > 0) - Number(a.linked_events > 0) || b.event_count - a.event_count || a.id.localeCompare(b.id)) : report.candidates;
  for (const item of candidates) {
    const label = node("label", `candidate${state.selected.has(item.id) ? " selected" : ""}`);
    const input = node("input"); input.type = "checkbox"; input.dataset.alert = item.id;
    input.checked = state.selected.has(item.id);
    input.setAttribute("aria-label", `Retire ${item.name} for ${item.service}${item.scope?.severity ? ` (${item.scope.severity})` : ""}`);
    input.addEventListener("change", () => {
      if (input.checked) state.selected.add(item.id); else state.selected.delete(item.id);
      setPreset(null); run();
    });
    const info = node("div"); info.append(node("strong", null, item.name));
    const meta = node("div", "candidate-meta");
    meta.append(node("span", null, `${item.service}${item.scope?.severity ? ` · ${item.scope.severity}` : ""}`), node("span", null, `${number(item.event_count)} ${units()} · ${item.incident_count} ${cases()}`));
    if (recorded()) meta.append(node("span", null, `namespace: ${item.scope?.namespace || "none"}`));
    info.append(meta);
    const text = item.isolated_verdict === "regression" ? `Alone: ${item.isolated_lost} lost · ${item.isolated_late} beyond budget` : item.isolated_verdict === "insufficient_evidence" ? "Alone: no linked warning evidence" : "Alone: no observed regression";
    info.append(node("span", `candidate-note ${item.isolated_verdict}`, text));
    label.append(input, info); fragment.append(label);
  }
  $("candidates").replaceChildren(fragment);
  if (focusId) [...$("candidates").querySelectorAll("input")].find((input) => input.dataset.alert === focusId)?.focus();
  $("selection").textContent = `${state.selected.size} selected`;
}
function renderVerdict(report) {
  const summary = report.summary;
  let title, description;
  if (report.verdict === "no_changes") {
    title = "Baseline: no removals selected";
    description = `Choose alerts on the left to review their combined effect on recorded ${cases()}.`;
  } else if (report.verdict === "regression") {
    title = summary.combination_conflicts ? "Combined removals erase a warning path." : "This change removes or delays a recorded warning.";
    description = summary.combination_conflicts ? `${summary.combination_conflicts} of ${summary.incidents_total} ${cases()} lose coverage or exceed the delay budget only when these removals are combined.` : `${summary.lost_incidents} ${cases()} lose all linked warnings; ${summary.late_incidents} exceed your ${number(state.delay)}-minute extra-delay budget.`;
  } else if (report.verdict === "insufficient_evidence") {
    title = "No regression found, but evidence is incomplete.";
    description = `A selected alert has no linked warnings, or the ledger is incomplete.${recorded() ? " These two experiments are only a small sample of possible failures." : " This replay cannot establish its detection value."}`;
  } else {
    title = "No observed regression in this history.";
    description = `All ${summary.baseline_covered} previously covered ${cases()} retain a warning within the ${number(state.delay)}-minute extra-delay budget. Review the evidence limits below.`;
  }
  $("verdict").className = `verdict ${report.verdict}`;
  $("verdict").replaceChildren(node("strong", null, title), node("p", null, description));
  $("removed").textContent = number(summary.removed_events);
  $("removed-note").textContent = `${summary.event_reduction_rate === null ? "—" : number(summary.event_reduction_rate * 100) + "%"} of ${number(summary.baseline_events)} ${units()}`;
  $("lost").textContent = summary.lost_incidents;
  $("lost").classList.toggle("bad-number", summary.lost_incidents > 0);
  $("lost-note").textContent = `${summary.baseline_covered} ${cases()} had linked warnings`;
  $("late").textContent = summary.late_incidents;
  $("late").classList.toggle("bad-number", summary.late_incidents > 0);
  $("late-note").textContent = `More than ${number(state.delay)} extra minutes to first ${recorded() ? "observation" : "page"}`;
}
function renderRestorations(report) {
  $("repair").hidden = !report.restoration_options.length;
  $("restorations").replaceChildren(...report.restoration_options.slice(0, 3).map((item) => {
    const row = node("div", "restore-option"), info = node("div");
    info.append(node("strong", null, `Keep ${item.name} · ${item.service}`), node("p", null, `Restores ${item.resolves_incidents.join(", ")} · ${item.events_restored} ${units()} retained · ${item.remaining_regressions} regressions remain`));
    const button = node("button", null, "Try keeping it");
    button.addEventListener("click", () => {state.selected.delete(item.id); setPreset(null); run();});
    row.append(info, button); return row;
  }));
}
function renderIncidents(report) {
  const s = report.summary;
  $("coverage").textContent = `Coverage ${s.baseline_covered} → ${s.proposed_covered} / ${s.incidents_total}`;
  const labels = {lost: "All warnings lost", late: "Beyond budget", delayed: "Later, within budget", unchanged: "Unchanged", baseline_gap: "No baseline warning"};
  const order = {lost: 0, late: 1, delayed: 2, unchanged: 3, baseline_gap: 4};
  const rows = [...report.incidents].sort((a, b) => order[a.status] - order[b.status] || a.id.localeCompare(b.id));
  $("incidents").replaceChildren(...rows.map((item) => {
    const details = node("details", "incident"), summary = node("summary");
    details.open = item.status === "lost" || item.status === "late";
    summary.append(node("span", "incident-id", item.id), node("span", "incident-title", item.title), node("span", `pill ${item.status}`, labels[item.status]));
    details.append(summary);
    const explanation = item.status === "baseline_gap" ? "This case has no linked warning. It stays in the denominator; this change did not create the gap." : item.status === "lost" ? "Every linked warning belongs to a selected alert scope. No linked warning remains in this capture." : `First ${recorded() ? "observed firing snapshot" : "recorded page"} ${new Date(item.baseline_first_event).toISOString().replace("T", " ").replace(".000Z", " UTC")}. Extra delay after this change: ${number(item.added_delay_minutes)} minutes.`;
    details.append(node("p", "incident-explanation", explanation));
    if (item.combination_conflict) details.append(node("p", "incident-explanation", "Combination conflict: none of these individual removals fails this case's replay."));
    const timeline = node("div", "timeline");
    for (const event of item.timeline) {
      const row = node("div", `timeline-event${event.removed ? " removed" : ""}`);
      row.append(node("span", null, `+${number(event.minutes_from_first_event)}m`), node("span", "timeline-name", `${event.alert_name} · ${event.service}`), node("span", "timeline-status", event.removed ? "removed" : "retained"));
      timeline.append(row);
    }
    if (item.timeline.length) details.append(timeline);
    if (recorded()) {
      const raw = node("details", "raw-evidence");
      raw.append(node("summary", null, "Inspect original labels & source timestamps"));
      const records = state.dataset.events.filter((event) => event.incident_id === item.id).map((event) => event.provenance);
      raw.append(node("pre", null, JSON.stringify(records, null, 2)));
      details.append(raw);
    }
    return details;
  }));
  if (!rows.length) $("incidents").append(node("p", "empty", "No incidents supplied. Detection coverage cannot be evaluated."));
}
function renderEvidence(report) {
  const s = report.summary, gaps = report.evidence.selected_without_incident_events;
  const names = gaps.map((id) => report.candidates.find((item) => item.id === id).name);
  $("evidence-summary").textContent = `${s.unlinked_events} of ${s.baseline_events} ${units()} have no ${cases() === "scenarios" ? "ground-truth" : "incident"} link; their usefulness is unknown. ${s.baseline_gaps} of ${s.incidents_total} ${cases()} had no baseline warning. The supplied ledger is ${report.evidence.ledger_declared_complete ? "declared complete" : "incomplete"}.${names.length ? ` No linked evidence for selected alert(s): ${names.join(", ")}.` : ""}${recorded() ? " Capture boundaries are not incident start/end times. Observed delay is limited by snapshot sampling and does not measure exact detection latency." : ""}`;
  $("fingerprint").textContent = `Dataset SHA-256 ${report.dataset_sha256.slice(0, 12)}…`;
  $("fingerprint").title = report.dataset_sha256;
}
async function requestReplay(dataset, selected, delay, signal) {
  const response = await fetch("/api/retirement/replay", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({dataset, retire: [...selected], max_delay_minutes: delay}), signal});
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Replay could not be completed.");
  return result;
}
function render(report) {
  state.report = report;
  renderDataset(); renderCandidates(report); renderVerdict(report); renderRestorations(report); renderIncidents(report); renderEvidence(report);
}
async function run() {
  const generation = ++state.request;
  state.controller?.abort(); state.controller = new AbortController();
  $("workspace").setAttribute("aria-busy", "true"); $("export").disabled = true;
  document.querySelector(".results").classList.add("stale"); error("");
  try {
    const result = await requestReplay(state.dataset, state.selected, state.delay, state.controller.signal);
    if (generation !== state.request) return;
    render(result); $("export").disabled = false;
    document.querySelector(".results").classList.remove("stale");
  } catch (failure) {
    if (failure.name !== "AbortError" && generation === state.request) error(`Replay failed: ${failure.message} Previous results are dimmed until a replay succeeds.`);
  } finally {
    if (generation === state.request) $("workspace").setAttribute("aria-busy", "false");
  }
}
function download(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + "\n"], {type: "application/json"}));
  const a = node("a"); a.href = url; a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => {
  state.selected = new Set(presets[button.dataset.preset]); setPreset(button.dataset.preset); run();
}));
$("clear").addEventListener("click", () => {state.selected.clear(); setPreset(null); run();});
$("delay").addEventListener("change", () => {
  if (!$("delay").reportValidity() || $("delay").value === "") {$("delay").value = state.delay; return;}
  state.delay = Number($("delay").value); run();
});
$("export").addEventListener("click", () => {if (state.report) download("alert-retirement-review.json", {...state.report, input_dataset: state.dataset});});
$("sample").addEventListener("click", () => {if (state.dataset) download("alert-history.json", state.dataset);});
$("import").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", async () => {
  const file = $("file").files[0]; if (!file) return;
  const button = $("import"); button.disabled = true; $("dataset-choice").disabled = true;
  try {
    if (file.size > 8 * 1024 * 1024) throw new Error("Use a dataset smaller than 8 MB.");
    const dataset = JSON.parse(await file.text());
    // Validate before replacing the current dataset or its visible report.
    await requestReplay(dataset, [], state.delay);
    state.dataset = dataset; state.selected.clear(); $("dataset-choice").value = "imported"; setPreset(null); await run();
  } catch (failure) {error(`Could not load dataset: ${failure.message}`);}
  finally {button.disabled = false; $("dataset-choice").disabled = false; $("file").value = "";}
});
function selectIbmProxy() {
  state.selected = new Set(state.dataset.alerts.filter((alert) => alert.service === "frontend-proxy" && ["RequestLatency", "RequestErrorRate"].includes(alert.name)).map((alert) => alert.id));
}
$("ibm-conflict").addEventListener("click", () => {selectIbmProxy(); run();});
$("ibm-unknown").addEventListener("click", () => {state.selected = new Set(state.dataset.alerts.filter((alert) => alert.name === "KubeClientCertificateExpiration").map((alert) => alert.id)); run();});
async function loadBuiltIn(choice = "default") {
  const chooser = $("dataset-choice"); chooser.disabled = true; $("import").disabled = true;
  $("export").disabled = true;
  state.controller?.abort(); ++state.request;
  try {
    const response = await fetch(`/api/retirement/dataset${choice === "synthetic" ? "?example=synthetic" : ""}`);
    if (!response.ok) throw new Error("Dataset is unavailable. Refresh to retry.");
    state.dataset = await response.json();
    chooser.value = choice;
    if (choice === "default") chooser.options[0].textContent = ibm() ? "IBM recorded experiments" : "Configured dataset";
    state.selected.clear();
    if (state.dataset.source.synthetic && presets.conflict.every((id) => state.dataset.alerts.some((alert) => alert.id === id))) {state.selected = new Set(presets.conflict); setPreset("conflict");}
    else setPreset(null);
    if (ibm()) selectIbmProxy();
    await run();
  } catch (failure) {error(failure.message); $("workspace").setAttribute("aria-busy", "false");}
  finally {chooser.disabled = false; $("import").disabled = false;}
}
$("dataset-choice").addEventListener("change", () => loadBuiltIn($("dataset-choice").value));
loadBuiltIn();
