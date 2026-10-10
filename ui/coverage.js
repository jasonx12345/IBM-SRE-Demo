const $ = (id) => document.getElementById(id);
let report;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusLabel(status) {
  return { observed: 'Observed', not_observed: 'Not observed', unknown: 'Unknown' }[status];
}

function render() {
  const choice = $('filter').value;
  const matches = report.scenarios.filter(s => choice === 'all' || s.expected.some(a => a.status === choice));
  const root = $('scenarios');
  root.replaceChildren();
  $('scenario-count').textContent = `${matches.length} of ${report.scenarios.length}`;
  if (!matches.length) {
    root.append(element('p', 'empty', 'No experiments match this filter.'));
    return;
  }
  for (const scenario of matches) {
    const details = element('details', 'scenario');
    const summary = element('summary');
    const title = element('span', 'scenario-title');
    title.append(element('strong', '', scenario.id), element('span', '', scenario.fault));
    const counts = element('span', 'counts');
    for (const status of ['observed', 'not_observed', 'unknown']) {
      const n = scenario.expected.filter(a => a.status === status).length;
      if (n) counts.append(element('span', `pill ${status}`, `${n} ${statusLabel(status)}`));
    }
    if (!scenario.expected.length) counts.append(element('span', 'pill unknown', 'No expected alerts declared'));
    summary.append(title, counts);
    details.append(summary);
    const body = element('div', 'scenario-body');
    const lead = scenario.snapshot_count
      ? `${scenario.snapshot_count} alert snapshots · ${scenario.alert_rows} recorded rows`
      : 'No alert snapshots published';
    body.append(element('p', 'capture', lead));
    const list = element('div', 'alert-list');
    for (const alert of scenario.expected) {
      const item = element('div', 'alert-row');
      const main = element('div');
      main.append(element('strong', '', alert.name), element('span', 'service', `${alert.service || alert.group_id} · ${alert.namespace || 'no namespace'}`));
      const result = element('div', 'alert-result');
      result.append(element('span', `pill ${alert.status}`, statusLabel(alert.status)));
      if (alert.evidence_url) {
        const link = element('a', '', 'View first matching snapshot ↗');
        link.href = alert.evidence_url;
        link.target = '_blank';
        link.rel = 'noopener';
        result.append(link);
      } else if (alert.reason) result.append(element('small', '', alert.reason));
      item.append(main, result);
      list.append(item);
    }
    if (!scenario.expected.length) list.append(element('p', 'empty', 'Ground truth declares no expected alerts to assess.'));
    body.append(list);
    const truth = element('a', 'truth-link', 'View original ground truth ↗');
    truth.href = scenario.ground_truth_url;
    truth.target = '_blank';
    truth.rel = 'noopener';
    body.append(truth);
    details.append(body);
    root.append(details);
  }
}

async function start() {
  try {
    const response = await fetch('/api/coverage/report');
    if (!response.ok) throw new Error('Coverage report is unavailable.');
    report = await response.json();
    for (const id of ['expected', 'observed', 'not-observed', 'unknown']) $(id).textContent = report.totals[id.replace('-', '_')].toLocaleString();
    $('source-link').href = report.source.url;
    $('filter').addEventListener('change', render);
    render();
  } catch (error) {
    $('error').textContent = error.message;
    $('error').hidden = false;
    $('scenarios').replaceChildren();
  }
}
start();
