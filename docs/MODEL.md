# The estimation model

**Alert duration is not engineer time. Every toil figure is an estimate.** An alert can self-resolve, remain open while nobody works on it, overlap another alert for the same incident, or involve multiple responders in parallel. The calculations below describe a prioritization model, not time tracking or billing.

## Observation window

The source declares a start (inclusive), end (exclusive), number of complete calendar months, and timezone. The dataset metadata is saved in the same transaction as its events. Annualization uses this declared coverage, including quiet months, rather than the gap between the first and last alert. The synthetic source defaults to six complete months, April 1 through October 1, 2026, in America/Toronto; the clock does not affect the generated data.

## Per-alert metrics

Events are grouped by `alert_name` across services. Let N be all events in the group and M be the number with `manual_action = true`. Rates are numeric fractions in the API, displayed as percentages in the dashboard. Timestamps are timezone-aware; durations use elapsed UTC time.

| Metric | Formula and treatment |
| --- | --- |
| `occurrences` | N = count of all events, regardless of severity or resolution |
| `manual_count` | M = count where manual_action is true |
| `manual_rate` | M / N |
| `auto_resolve_rate` | Count where auto_resolved is true / N |
| `incident_rate` | Count with non-NULL incident_id / N; not a count of distinct incidents |
| `median_ack_minutes` | Median of (acknowledged_at − fired_at) / 60 seconds, over valid acknowledged events, including events that required no action |
| `median_manual_minutes` | Median of (resolved_at − acknowledged_at) / 60 seconds, **only over manual-action events** with both timestamps present and nonnegative intervals |
| `mean_responders` | Sum of responder_count over manual-action events / M; zero when M = 0 |
| `after_hours_rate` | Count of all events fired before business_hours_start or at/after business_hours_end in the configured local timezone / N |
| `runbook_repeat_rate` | Count of the most common known, nonempty runbook action among manual events / M; zero when M = 0 |
| `pages_per_month` | Count where severity = page / declared months; tickets and info events are not pages |
| `occurrences_per_month` | N / declared months |
| `after_hours_page_rate` | After-hours page count / page count; null when there are no pages |
| `auto_resolve_under_3_minutes_rate` | Count of auto-resolved events with a firing-to-resolution duration of 0–180 seconds / N |

The default business window is **09:00 inclusive to 17:00 exclusive, America/Toronto**, respecting daylight saving time. Weekends use the same clock-hour rule; the spec does not define a working-week calendar. Monthly buckets use the source window's timezone. If the model timezone is changed independently, the dashboard reports that after-hours evaluation timezone explicitly.

Missing manual durations are excluded from the median, but the resulting median is multiplied by **all** manual events, exactly as the model specifies. `manual_duration_samples` and `manual_duration_missing` expose this extrapolation. With manual events but no usable durations, estimated toil is unknown (`null`) and excluded from totals; the summary reports the number of unestimable alert types. With no manual events, estimated toil is zero and the manual median is `null`. Invalid timestamps are rejected by ingestion; the scoring function also excludes negative durations defensively.

Unknown runbook actions remain in the denominator of runbook repeat rate, but cannot win the mode. If actions tie, their names break the tie lexically. The breakdown lists known actions, their counts and shares of all manual events, plus a separate unknown count. The denominator includes manual events with an unresolved or incompletely recorded duration: `manual_action` is the available proxy for having performed a resolution action.

## Toil estimate and annualization

```text
estimated_toil_minutes
    = manual_count × median_manual_minutes × max(mean_responders, 1)

estimated_annual_toil_hours
    = estimated_toil_minutes / 60 × (12 / months_of_data)
```

Example: 100 manual events, median 12 minutes, 1.5 mean responders, and six months of coverage produce 1,800 estimated toil minutes and **60 estimated annual toil hours**. Acknowledgement delay is displayed but never added to the estimate. Auto-resolved events contribute no manual toil. At least one responder is assumed for an event marked manual, even when responder counts are missing as zero.

This formula assumes the median is representative of every manual event and that each responder works for the same modeled duration. It multiplies the median duration by a separate mean responder count rather than pairing durations with responders event-by-event. It does not deduplicate incidents, cap long resolutions, add context-switch penalties, or forecast seasonality.

## Why runbook repeat rate is the automation-confidence proxy

A repeated, recorded action provides direct evidence that a recurring manual resolution has a scriptable shape. For example, 87 of 100 manual events using `flush_cache` gives a repeat rate of 87%. Unknown or varied actions lower that rate, instead of being treated as evidence for automation. Repetition does not prove an action is safe to automate, but it is a transparent, inspectable signal; no separate confidence score or statistical probability is invented.

## Classification

All thresholds are tunable in `config/thresholds.yaml`. Every comparison is inclusive, and occurrence thresholds refer to **the entire observation window**, not a monthly rate. First match wins:

1. **delete**: occurrences ≥ 30, manual_rate ≤ 0.10, incident_rate ≤ 0.05.
2. **tune**: occurrences ≥ 30, incident_rate ≤ 0.20, auto_resolve_rate ≥ 0.50.
3. **automate**: manual_rate ≥ 0.60, runbook_repeat_rate ≥ 0.70, occurrences ≥ 10.
4. **keep_human**: occurrences ≤ 10.
5. **unclassified**: none of the above.

Reasons interpolate observed metrics and the actual modal action. The tune reason's within-three-minute share uses all occurrences as its denominator; it does not infer that every auto-resolution happened quickly. Recommendations are suggestions for review, and the tool never edits an alert or executes a remediation.

The database saturation archetype occurs about four times a month, or 24 times in six months. It can therefore be `unclassified`, not `keep_human`, under the exact specified default. Neither mixed pod failures nor database incidents are artificially forced into a class. With seed 42, the default fixture has three automate candidates, two delete candidates, and three unclassified types; tune/keep_human can legitimately be empty.

## Ranking and estimated savings

```text
automation_estimated_annual_hours_saved
    = estimated_annual_toil_hours × automation_savings_fraction

deletion_estimated_annual_hours_saved
    = estimated_annual_toil_hours × deletion_savings_fraction

top_three_automation_estimated_annual_hours_saved
    = sum(estimated_annual_hours_saved for top three automate candidates)

summary_estimated_annual_toil_hours
    = sum(known estimated_annual_toil_hours across alert types)

classification_share(category)
    = count(alert types classified category) / total alert types
```

Savings fractions are tunable in `config/model.yaml`, both defaulting to **1.0**. These are gross upper-bound estimates assuming intervention removes all modeled manual work for a selected alert type, even when some recorded actions differ from the mode. They exclude implementation effort, maintenance, rollout risk and residual review. Lower the fractions to explore partial coverage. Runbook repeat rate affects eligibility; it is not multiplied into savings as an undocumented second confidence model.

Automation recommendations rank by estimated annual toil hours descending; because the configured fraction is global, this is also savings order. Deletion recommendations rank by **event volume descending**, breaking ties by alert name. This puts the largest noise source first even when it records zero manual work; deleting a no-action alert has zero modeled hours saved. Tuning has no savings formula because the data cannot justify how much a threshold change would save. The API returns up to three candidates per recommended category, without filling vacant places from other categories.

An empty dataset produces zero numeric totals, zero shares, empty recommendations and no observation window. Means/medians with no usable observations remain null where appropriate. Estimates are cached for up to 15 seconds per process, a configurable operational choice rather than a modeling assumption.
