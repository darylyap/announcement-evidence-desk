def latest_by_claim(decisions):
    latest = {}
    for decision in decisions:
        if decision.get("claim_id"):
            latest[decision["claim_id"]] = decision
    return latest


def assessment_summary(findings, decisions):
    latest = latest_by_claim(decisions)
    ids = {f["claim_id"] for f in findings}
    assessed = [latest[cid] for cid in ids if cid in latest]
    pending = len(ids) - len(assessed)
    follow_up = sum(d["verdict"] == "needs_evidence" for d in assessed)
    status = (
        "succeeded"
        if not assessed
        else "partially_reviewed"
        if pending
        else "needs_evidence"
        if follow_up
        else "reviewed"
    )
    return {
        "total": len(ids),
        "assessed": len(assessed),
        "pending": pending,
        "needs_evidence": follow_up,
        "status": status,
    }
