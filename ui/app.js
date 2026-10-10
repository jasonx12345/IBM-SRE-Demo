"use strict";
const $ = (selector) => document.querySelector(selector);
const number = (value, decimals = 0) =>
  value == null
    ? "—"
    : Number(value).toLocaleString(undefined, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals,
      });
const percent = (value) => (value == null ? "—" : `${number(value * 100)}%`);
const labels = {
  automate: "Automate",
  tune: "Tune",
  delete: "Delete",
  keep_human: "Keep human",
  unclassified: "Unclassified",
};
const state = {
  alerts: [],
  filter: "all",
  query: "",
  sort: "estimated_annual_toil_hours",
  direction: -1,
  detailRequest: 0,
};
function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function badge(category) {
  return el("span", `badge ${category}`, labels[category]);
}
async function get(path) {
  const response = await fetch(path, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}
function alertButton(row) {
  const button = el("button", "alert-title", row.alert_name);
  button.addEventListener("click", () => showDetail(row.alert_name));
  return button;
}
function metric(value, label, className = "") {
  const item = el("div", className);
  item.append(el("dd", "", value), el("dt", "", label));
  return item;
}
function recommendation(row, index, deletion = false) {
  const card = el("article", deletion ? "delete-card" : "recommendation-card");
  const top = el("div", "card-top");
  top.append(
    deletion
      ? alertButton(row)
      : el("span", "rank", `PRIORITY ${String(index + 1).padStart(2, "0")}`),
    badge(row.classification),
  );
  card.append(top);
  if (!deletion) {
    card.append(
      alertButton(row),
      el(
        "p",
        "card-service",
        `${row.services.join(" / ")} · ${row.modal_runbook_action || "No known runbook"}`,
      ),
    );
    const savings = el("div", "card-savings");
    const value = el("strong", "", number(row.estimated_annual_hours_saved, 1));
    value.append(el("small", "", "h"));
    savings.append(value, el("span", "", "estimated annual hours saved"));
    card.append(savings);
  }
  const metrics = el("dl", "card-metrics");
  metrics.append(
    metric(number(row.pages_per_month, 1), "pages / month"),
    metric(number(row.median_manual_minutes, 1), "median manual min"),
    metric(
      percent(row.runbook_repeat_rate),
      "runbook repeat",
      deletion ? "" : "repeat",
    ),
  );
  if (deletion)
    metrics.append(
      metric(
        `${number(row.estimated_annual_hours_saved, 1)} h`,
        "est. saved / year",
      ),
    );
  const button = el("button", "card-link", "Inspect evidence");
  button.append(el("span", "", "↗"));
  button.addEventListener("click", () => showDetail(row.alert_name));
  card.append(metrics, el("p", "reason", row.reason), button);
  return card;
}
function renderFilters() {
  const filters = $("#filters");
  filters.replaceChildren();
  for (const category of ["all", ...Object.keys(labels)]) {
    const count =
      category === "all"
        ? state.alerts.length
        : state.alerts.filter((row) => row.classification === category).length;
    const button = el(
      "button",
      `filter${state.filter === category ? " active" : ""}`,
      category === "all" ? "All alerts" : labels[category],
    );
    button.setAttribute("aria-pressed", String(state.filter === category));
    button.append(el("span", "", String(count)));
    button.addEventListener("click", () => {
      state.filter = category;
      renderFilters();
      renderTable();
    });
    filters.append(button);
  }
}
function renderTable() {
  const rows = state.alerts.filter(
    (row) =>
      (state.filter === "all" || row.classification === state.filter) &&
      `${row.alert_name} ${row.services.join(" ")}`
        .toLowerCase()
        .includes(state.query),
  );
  rows.sort((a, b) => {
    const av = a[state.sort],
      bv = b[state.sort];
    if (av == null || bv == null) return av == null ? (bv == null ? 0 : 1) : -1;
    return (
      (typeof av === "string" ? av.localeCompare(bv) : av - bv) *
      state.direction
    );
  });
  const body = $("#alert-rows");
  body.replaceChildren();
  for (const row of rows) {
    const tr = el("tr");
    const title = el("td");
    title.append(
      alertButton(row),
      el("span", "service-label", row.services.join(" / ")),
    );
    tr.append(title);
    const values = [
      number(row.occurrences),
      percent(row.manual_rate),
      percent(row.auto_resolve_rate),
      number(row.median_manual_minutes, 1),
      percent(row.runbook_repeat_rate),
      percent(row.incident_rate),
      number(row.estimated_annual_toil_hours, 1),
    ];
    values.forEach((value, index) =>
      tr.append(
        el(
          "td",
          index === 6
            ? "number-strong"
            : index === 4 && row.classification === "automate"
              ? "repeat-cell"
              : "",
          value,
        ),
      ),
    );
    const category = el("td");
    category.append(badge(row.classification));
    tr.append(category);
    body.append(tr);
  }
  if (!rows.length) {
    const tr = el("tr");
    const td = el(
      "td",
      "empty",
      "No alerts match this view. Try another filter or search.",
    );
    td.colSpan = 9;
    tr.append(td);
    body.append(tr);
  }
  $("#table-count").textContent =
    `Showing ${rows.length} of ${state.alerts.length} alert types`;
  document.querySelectorAll("th[data-key]").forEach((th) => {
    const active = th.dataset.key === state.sort;
    const button = th.querySelector("button");
    button.textContent =
      button.textContent.replace(/ [↑↓]$/, "") +
      (active ? (state.direction === 1 ? " ↑" : " ↓") : "");
    if (active)
      th.setAttribute(
        "aria-sort",
        state.direction === 1 ? "ascending" : "descending",
      );
    else th.removeAttribute("aria-sort");
  });
}
function render(summary, alerts, recommendations) {
  state.alerts = alerts;
  $("#total-hours").textContent = number(
    summary.estimated_annual_toil_hours,
    1,
  );
  $("#total-alerts").textContent = number(summary.alerts_analysed);
  $("#recoverable-hours").textContent = number(
    summary.top_three_automation_estimated_annual_hours_saved,
    1,
  );
  $("#alert-count-note").textContent =
    `${summary.alert_types_analysed} alert types · ${summary.window?.months || 0} months of history`;
  $("#after-hours-note").textContent =
    `${percent(summary.after_hours_page_rate)} of pages fired after hours`;
  if (summary.window) {
    const format = new Intl.DateTimeFormat("en", {
      month: "short",
      year: "numeric",
      timeZone: summary.window.timezone,
    });
    $("#window-label").textContent =
      `${format.format(new Date(summary.window.start))} — ${format.format(new Date(new Date(summary.window.end).getTime() - 1))}`;
    $("#window-meta").textContent =
      `${summary.window.months} complete months · ${summary.assumptions.timezone}`;
    $(".environment").lastChild.textContent =
      summary.window.source === "synthetic" ? "SYNTHETIC DATA" : "ALERT DATA";
  } else {
    $("#window-label").textContent = "No dataset loaded";
    $("#window-meta").textContent = "Seed data to start your analysis";
  }
  $("#automation-cards").replaceChildren(
    ...recommendations.automate.map((row, i) => recommendation(row, i)),
  );
  $("#delete-cards").replaceChildren(
    ...recommendations.delete.map((row, i) => recommendation(row, i, true)),
  );
  if (!recommendations.automate.length)
    $("#automation-cards").append(
      el(
        "div",
        "empty",
        "No automation candidates meet the configured thresholds.",
      ),
    );
  if (!recommendations.delete.length)
    $("#delete-cards").append(
      el(
        "div",
        "empty",
        "No deletion candidates meet the configured thresholds.",
      ),
    );
  $("#savings-note").textContent =
    `Savings assume ${percent(summary.assumptions.automation_savings_fraction)} automation and ${percent(summary.assumptions.deletion_savings_fraction)} deletion coverage. Build and maintenance costs are excluded.`;
  $("#assumption-detail").textContent =
    `After hours means before ${summary.assumptions.business_hours_start}:00 or at/after ${summary.assumptions.business_hours_end}:00 in ${summary.assumptions.timezone}, on any day. Classification shares count alert types. Data may be cached for ${summary.assumptions.cache_seconds} seconds.`;
  $("#quality-note").textContent =
    `${summary.manual_duration_missing} manual events lack a usable duration; ${summary.unestimable_alert_types} alert types cannot be estimated and are excluded from numeric totals. Auto-resolved events contribute no manual toil.`;
  renderFilters();
  renderTable();
  if (!summary.alerts_analysed) {
    const message = $("#message");
    message.hidden = false;
    message.append(
      document.createTextNode("Your workspace is ready. Run "),
      el("code", "", "make seed"),
      document.createTextNode(
        " to load six months of deterministic alert history, then refresh.",
      ),
    );
  }
}
async function load() {
  $("#refresh").disabled = true;
  $("#dashboard").setAttribute("aria-busy", "true");
  const message = $("#message");
  message.hidden = true;
  message.className = "message";
  message.replaceChildren();
  try {
    const [summary, alerts, recommendations] = await Promise.all([
      get("/api/summary"),
      get("/api/alerts"),
      get("/api/recommendations"),
    ]);
    render(summary, alerts, recommendations);
  } catch (error) {
    message.hidden = false;
    message.classList.add("error");
    message.append(
      document.createTextNode(
        `Analysis could not be loaded. ${error.message}. Check the service and database, then retry. `,
      ),
    );
    const retry = el("button", "", "Retry");
    retry.addEventListener("click", load);
    message.append(retry);
  } finally {
    $("#refresh").disabled = false;
    $("#dashboard").setAttribute("aria-busy", "false");
  }
}
function svgNode(tag, attributes, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes))
    node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function trendChart(series) {
  const svg = svgNode("svg", {
    viewBox: "0 0 650 185",
    class: "trend-chart",
    role: "img",
    "aria-label":
      "Monthly occurrences and manual actions. Exact values follow in the accessible table.",
  });
  const max = Math.max(1, ...series.map((month) => month.occurrences));
  const step = 610 / Math.max(1, series.length);
  for (const [index, month] of series.entries()) {
    const x = 25 + index * step;
    const height = (month.occurrences / max) * 125;
    const manualHeight = (month.manual_count / max) * 125;
    const group = svgNode("g", {});
    group.append(
      svgNode(
        "title",
        {},
        `${month.month}: ${month.occurrences} events, ${month.manual_count} manual`,
      ),
      svgNode("rect", {
        x,
        y: 145 - height,
        width: Math.max(1, step * 0.5),
        height,
        rx: 3,
        class: "bar",
      }),
      svgNode("rect", {
        x,
        y: 145 - manualHeight,
        width: Math.max(1, step * 0.5),
        height: manualHeight,
        rx: 3,
        class: "manual-bar",
      }),
    );
    if (series.length <= 12 || index % Math.ceil(series.length / 12) === 0)
      group.append(svgNode("text", { x, y: 168 }, month.month.slice(2)));
    if (series.length <= 12)
      group.append(
        svgNode("text", { x, y: 135 - height }, String(month.occurrences)),
      );
    svg.append(group);
  }
  return svg;
}
function actionRow(action, count, share) {
  const row = el("div", "breakdown-row");
  const bar = el("progress");
  bar.max = 1;
  bar.value = share;
  bar.setAttribute(
    "aria-label",
    `${action}: ${percent(share)} of manual resolutions`,
  );
  row.append(
    el("span", "action-label", action),
    bar,
    el("span", "share", `${count} · ${percent(share)}`),
  );
  return row;
}
async function showDetail(name) {
  const requestId = ++state.detailRequest;
  const dialog = $("#detail-dialog");
  const content = $("#detail-content");
  content.replaceChildren(
    el("h2", "", name),
    el("p", "muted", "Loading evidence…"),
  );
  content.firstChild.id = "detail-title";
  if (!dialog.open) dialog.showModal();
  try {
    const row = await get(`/api/alerts/${encodeURIComponent(name)}`);
    if (requestId !== state.detailRequest || !dialog.open) return;
    content.replaceChildren();
    const title = el("h2", "", row.alert_name);
    title.id = "detail-title";
    content.append(
      title,
      badge(row.classification),
      el("p", "detail-reason", row.reason),
    );
    const stats = el("dl", "detail-stats");
    for (const [label, value] of [
      ["Estimated toil h / year", number(row.estimated_annual_toil_hours, 1)],
      ["Runbook repeat", percent(row.runbook_repeat_rate)],
      [
        "Manual events",
        `${number(row.manual_count)} / ${number(row.occurrences)}`,
      ],
      ["Median manual min", number(row.median_manual_minutes, 1)],
      ["Median ack min", number(row.median_ack_minutes, 1)],
      ["Mean responders", number(row.mean_responders, 2)],
      ["After hours (all events)", percent(row.after_hours_rate)],
      ["Incident-linked", percent(row.incident_rate)],
    ]) {
      const stat = el("div");
      stat.append(el("dt", "", label), el("dd", "", value));
      stats.append(stat);
    }
    content.append(
      stats,
      el("h3", "", "Monthly alert activity"),
      trendChart(row.monthly_occurrences),
    );
    const legend = el("div", "chart-caption");
    legend.append(
      el("span", "", "All events"),
      el("span", "", "Manual actions"),
    );
    content.append(legend);
    const accessible = el("table", "sr-only");
    const header = el("tr");
    for (const label of ["Month", "Events", "Manual", "Pages"])
      header.append(el("th", "", label));
    accessible.append(header);
    for (const point of row.monthly_occurrences) {
      const tr = el("tr");
      for (const value of [
        point.month,
        point.occurrences,
        point.manual_count,
        point.pages,
      ])
        tr.append(el("td", "", String(value)));
      accessible.append(tr);
    }
    content.append(accessible);
    content.append(
      el("h3", "", "Runbook actions · share of all manual resolutions"),
    );
    const actions = row.runbook_actions.map((action) =>
      actionRow(action.action, action.count, action.share),
    );
    content.append(...actions.slice(0, 5));
    if (actions.length > 5) {
      const more = el("details");
      more.append(
        el(
          "summary",
          "detail-actions-toggle",
          `Show ${actions.length - 5} more actions`,
        ),
        ...actions.slice(5),
      );
      content.append(more);
    }
    if (row.unknown_runbook_count)
      content.append(
        actionRow(
          "Unknown / unrecorded",
          row.unknown_runbook_count,
          row.unknown_runbook_count / row.manual_count,
        ),
      );
    if (!row.manual_count)
      content.append(
        el(
          "p",
          "muted small",
          "No manual actions recorded. There is no runbook evidence to evaluate.",
        ),
      );
    content.append(
      el(
        "p",
        "detail-footnote",
        `${row.manual_duration_samples} usable manual duration samples; ${row.manual_duration_missing} missing. ${percent(row.auto_resolve_rate)} auto-resolved. Repeat rate is the automation-confidence proxy. All toil figures are estimates; correlated alerts and idle time can overstate the result.`,
      ),
    );
  } catch (error) {
    if (requestId === state.detailRequest)
      content.append(
        el(
          "p",
          "message error",
          `Could not load this alert: ${error.message}. Close and try again.`,
        ),
      );
  }
}
$("#refresh").addEventListener("click", load);
$("#search").addEventListener("input", (event) => {
  state.query = event.target.value.trim().toLowerCase();
  renderTable();
});
document.querySelectorAll("th[data-key] button").forEach((button) =>
  button.addEventListener("click", () => {
    const key = button.parentElement.dataset.key;
    state.direction =
      state.sort === key
        ? -state.direction
        : key === "alert_name" || key === "classification"
          ? 1
          : -1;
    state.sort = key;
    renderTable();
  }),
);
$("#close-detail").addEventListener("click", () => $("#detail-dialog").close());
$("#detail-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    )
      event.currentTarget.close();
  }
});
load();
