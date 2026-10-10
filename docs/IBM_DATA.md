# IBM data used by this demo

The default retirement lab uses measured alerts published by **IBM Research in ITBench-Lite**, recorded while faults were deliberately injected into test systems. These are real observations from controlled experiments, not IBM customer production incidents, Maximo telemetry, or an authenticated Instana integration.

Source: https://huggingface.co/datasets/ibm-research/ITBench-Lite

Pinned revision: `d0916b08ba421ce5e672e9ad68aa947d938dfef0`.

Upstream directory: `snapshots/sre/v0.2-B96DF826-4BB2-4B62-97AB-6D84254C53D7/`.

## What is included

Only Scenario-1 (frontend proxy overload) and Scenario-2 (cart failure feature flag) are included. These are the first two numbered SRE scenarios, selected to keep this demo small and its service-based joins inspectable; they are not a representative sample of production incidents. Display titles are local summaries of IBM's ground truth.

| Evidence | Count |
| --- | ---: |
| Timestamped alert snapshots | 82 |
| Raw snapshot rows | 772 |
| Pending or non-warning/critical rows excluded | 287 |
| Repeated observations of existing episodes collapsed | 448 |
| Distinct observed firing episodes | 37 |
| Alert scopes | 13 |
| Episodes matched to ground truth | 8 |
| Episodes with unknown association | 29 |

Both captures are dated December 15, 2025. Scenario-1 spans approximately 17:30–18:17 UTC; Scenario-2 spans 17:30–18:03 UTC. These are separate experiments even though their clock ranges overlap. The overall window does not imply continuous monitoring between independent runs.

Original snapshots, ground-truth YAML and the upstream dataset card are preserved in `seed/itbench/` (approximately 0.6 MB total). `manifest.json` records upstream paths, sizes and SHA-256 hashes. `seed/itbench-replay.json` is the derived input used by the app. Every derived event retains source labels, original `activeAt`, first/last observation, repeat count, source filename and ground-truth matching basis. The UI exposes these under each experiment; the downloadable dataset and review contain them too.

## How normalization works

1. Include only rows whose top-level state is `firing` and whose source severity is `warning` or `critical`. Pending alerts and support signals such as Watchdog/InfoInhibitor are excluded from this warning replay, without claiming they are useless operationally.
2. Within each experiment, deduplicate the complete label set plus the original `activeAt`. Repeated values and snapshot appearances are observations of the same episode. A different `activeAt` is a different episode. Experiments are kept separate.
3. Use the **first snapshot observing that episode firing** as the replay timestamp. Snapshot filename clocks are interpreted as UTC, consistent with the companion timestamped export. `activeAt` is preserved but is not treated as firing or delivery time: Prometheus can hold alerts pending before they fire. See https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/.
4. Group candidate removals by alert name, namespace, service name, job and source severity. This is an explicit scope applied across the two captures, not a recovered rule definition. Warning and critical variants remain separate; instance/pod differences can produce multiple episodes within a scope.
5. Link to a scenario only when the alert name matches a declared ground-truth alert, the namespace matches its Service group, and `service_name` fully matches that group's filter. All five declared service-alert combinations in these two scenarios have observations. No time-only or name-only joins are used. Unmatched warnings remain unlinked, even if they might plausibly be related.
6. Evidence intervals are snapshot capture boundaries, not fault onset or recovery times. Alerts already firing in the first snapshot are marked `present_at_capture_start`; their earlier firing order is unknown. Changes in first-observation time are sample-based, not exact detection latency.

## What the replay shows

Removing `RequestErrorRate` and `RequestLatency` for `frontend-proxy` removes six episodes across the captures. The overload scenario loses both ground-truth-linked warnings. Removing either scope alone leaves a warning in that capture. The cart-failure scenario still has warnings, but the earliest remaining observation is approximately 19 minutes later, beyond the default five-minute budget.

Keeping the error-rate scope restores both scenarios within the delay budget while still removing the one latency episode. Keeping only the latency scope repairs the overload case but leaves the cart case delayed. The app ranks the error-rate restoration first because it checks the entire batch, not only one scenario.

The verdict after restoration still says evidence is incomplete. Two short experiments do not supply a complete incident ledger or establish production safety. The 29 unlinked episodes are unknown, not proven noise. The report does not infer pager deliveries, acknowledgement times, engineer effort, monetary savings or annual frequency.

The synthetic teaching examples remain available through the evidence selector. The original `/toil` dashboard also remains synthetic because the IBM subset does not contain the human-response fields required by that model.

## Reproduce offline or refresh from the pinned source

```powershell
# Verify every original file hash and regenerate the same derived dataset offline:
.venv\Scripts\python.exe -m ingest.itbench

# Re-download only the pinned subset, then normalize:
.venv\Scripts\python.exe -m ingest.itbench --download
```

No IBM account, Docker, Kubernetes or live cloud service is required. The importer caps downloads at 200 files and 2 MB per file; it does not fetch the multi-gigabyte metrics, logs or traces. The app uses the checked-in derived file and does not call IBM or Hugging Face at startup.

## Attribution

IBM Research, **ITBench-Lite**, licensed Apache-2.0 according to its dataset card. Original attribution is retained in `seed/itbench/README.md`; see `seed/itbench/LICENSE` and the root `THIRD_PARTY_NOTICES.md`. Derived normalization code and scenario titles are local project additions. Dataset publication: Jha et al., *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks*, 2025, https://arxiv.org/abs/2502.05352.
