# Research: alert retirement as a change-review problem

Reviewed 9 October 2026. This is a bounded review of public documentation, not a claim of worldwide novelty or a patent search.

## Decision

Focus Toil Budget on this question: **If we retire these alerts together, which recorded incidents lose their warning, or receive a later warning?**

Two alerts may each have a replacement when evaluated separately. Retire both and that replacement disappears. An independent incident ledger also exposes incidents that never had a recorded page, instead of silently excluding them from the denominator.

The implementation is an explainable historical regression check for a proposed batch of alert removals. It reports individual versus combined outcomes, first-page delay, concrete incident timelines, evidence gaps, and a downloadable review record. This is a useful project distinction, not an assertion that competitors cannot do it.

## What already exists

| Primary source | Documented capability | Consequence for this project |
| --- | --- | --- |
| [PagerDuty AI Orchestrations](https://support.pagerduty.com/main/docs/ai-orchestrations) | Uses historical events and incidents to recommend orchestration rules, with expected impact and explanations. | Historical recommendations and noise reduction are not new. |
| [Datadog monitor audit guidance](https://www.datadoghq.com/blog/how-to-audit-and-clean-up-monitors/) | Describes both noisy monitors and coverage gaps, and a structured monitoring audit. | Noise volume alone is an inadequate retirement criterion. |
| [Rootly noisy alerts](https://rootly.com/changelog/minimizing-noisy-alerts) | Marks noisy alerts and surfaces signal-to-noise reporting for review. | Another noise dashboard would overlap directly. |
| [Nobl9 SLO Backtesting](https://www.nobl9.com/features/slo-backtesting) | Evaluates proposed SLOs against historical metrics. | Backtesting itself is established. |
| [CausalReplay project](https://github.com/opencausality/CausalReplay) | Models incident cascades and counterfactual interventions. | Counterfactual incident analysis also has prior art. Our calculation does not model causal recovery. |
| [Google SRE: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) | Evaluates alerting through precision, recall, detection time and reset time. | Preserve detection evidence alongside the reduction in page events. |

I did not find an explicit description of this exact combined-removal review workflow in those reviewed sources. That is a limited search finding, not proof that the capability does not exist. Product behavior beyond the public documentation was not tested.

## Specific user and workflow

An on-call engineer is preparing a pull request to remove two noisy paging rules. They load exported page events plus a separately maintained incident ledger, select the rules, choose an acceptable increase in first-page delay, and review the combined result before making the configuration change.

The optional synthetic teaching dataset includes two worker alerts that individually preserve historical coverage, but jointly remove the only recorded pages for two incidents. It also includes a twelve-minute fallback, a sole warning, an incident with no page, and an alert with no incident evidence. These are authored cases. The default dataset now uses measured alerts from two IBM Research ITBench-Lite experiments; its source and limits are documented in [IBM_DATA.md](IBM_DATA.md).

## Honest scope

- This is event-removal replay, not evaluation of PromQL or changed metric thresholds.
- A retained page is recorded evidence of a notification candidate, not proof that an engineer noticed or acted on it.
- Later alerts and incident outcomes are held fixed. They may have changed if an earlier page had been removed in reality.
- Unlinked pages are not assumed to be false positives. Incident labels and the ledger can be incomplete.
- Zero observed regressions is not a safety guarantee. No model estimates the probability of a future missed incident.
- The tool prepares a review; it does not modify production alert rules.

## Remaining product validation

Interview SREs about how they review multiple alert removals today; obtain anonymized exports and independently reviewed incident links; compare with the actual workflow in their paid monitoring tools. Those steps are needed before claiming an unmet commercial need.

## IBM-specific follow-up

[IBM_RESEARCH.md](IBM_RESEARCH.md) records public Instana APIs, the documented Instana-to-Maximo IT incident integration, existing Instana historical alert previews, and a concrete adapter proposal. Native IBM-format import is not yet implemented.
