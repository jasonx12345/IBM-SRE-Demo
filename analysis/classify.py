"""Ordered, explainable classification. All decision thresholds come from YAML."""


def classify(metrics: dict, thresholds: dict) -> tuple[str, str]:
    m = metrics
    t = thresholds["delete"]
    if (
        m["occurrences"] >= t["min_occurrences"]
        and m["manual_rate"] <= t["max_manual_rate"]
        and m["incident_rate"] <= t["max_incident_rate"]
    ):
        return "delete", (
            f"{m['occurrences']} events; {m['manual_rate']:.0%} needed manual action, "
            f"{m['incident_rate']:.0%} linked to incidents."
        )
    t = thresholds["tune"]
    if (
        m["occurrences"] >= t["min_occurrences"]
        and m["incident_rate"] <= t["max_incident_rate"]
        and m["auto_resolve_rate"] >= t["min_auto_resolve"]
    ):
        return "tune", (
            f"{m['auto_resolve_rate']:.0%} self-resolved; "
            f"{m['auto_resolve_under_3_minutes_rate']:.0%} of all events self-resolved within 3 min; "
            f"{m['incident_rate']:.0%} linked to incidents."
        )
    t = thresholds["automate"]
    if (
        m["manual_rate"] >= t["min_manual_rate"]
        and m["runbook_repeat_rate"] >= t["min_runbook_repeat"]
        and m["occurrences"] >= t["min_occurrences"]
    ):
        return "automate", (
            f"{m['runbook_repeat_rate']:.0%} of manual resolutions used "
            f"{m['modal_runbook_action']}; {m['manual_rate']:.0%} of {m['occurrences']} events needed action."
        )
    if m["occurrences"] <= thresholds["keep_human"]["max_occurrences"]:
        return "keep_human", (
            f"Only {m['occurrences']} events in this window; "
            f"{m['incident_rate']:.0%} linked to incidents. Retain human review."
        )
    return "unclassified", (
        f"{m['occurrences']} events; {m['manual_rate']:.0%} manual, "
        f"{m['runbook_repeat_rate']:.0%} runbook repeat, {m['incident_rate']:.0%} incident-linked; "
        "no configured rule matched."
    )
