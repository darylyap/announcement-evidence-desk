from .assessments import assessment_summary, latest_by_claim

LABELS = {
    "accept": "Agrees with AI finding",
    "reject": "Disagrees with AI finding",
    "needs_evidence": "More evidence needed",
}


def make_brief(case, run):
    flow = case["workflow"]
    findings = run["result"]["findings"] if run and run["status"] == "succeeded" else []
    decisions = run["decisions"] if run else []
    latest = latest_by_claim(decisions)
    review = assessment_summary(findings, decisions)
    lines = [
        "REVIEW BRIEF",
        case["title"],
        "=" * 60,
        "",
        "1. REVIEW CONTEXT",
        f"Company: {case['issuer']}",
        f"Claim date / as-of date: {case['article_date']}",
        f"Claim origin: {case['source_url'] or 'Supplied text / labelled test claims'}",
        f"Topic: {flow['topic']}",
        "",
        "2. HUMAN ASSESSMENT",
        f"Claims assessed: {review['assessed']} of {review['total']} | Pending: {review['pending']} | More evidence needed: {review['needs_evidence']}",
    ]
    if any(not d.get("claim_id") for d in decisions):
        lines.append(
            "An earlier overall assessment exists; it is not counted as a claim assessment."
        )
    lines += ["", "3. FINDINGS AND EVIDENCE"]
    if run and run["status"] == "succeeded":
        for i, item in enumerate(findings, 1):
            decision = latest.get(item["claim_id"])
            lines += [
                "",
                f"Claim {i} — {item['verdict'].replace('_', ' ').upper()}",
                item["text"],
                f"Claim input quote: {item['article_quote']}",
                f"Explanation: {item['explanation']}",
            ]
            lines += [
                f"Human assessment: {LABELS[decision['verdict']] if decision else 'Pending human review'}"
            ]
            if decision:
                lines += [
                    f"Reviewer: {decision['reviewer']}",
                    f"Reason: {decision['note']}",
                    f"Assessment saved: {decision['created_at']} UTC",
                ]
            for cite in item["citations"]:
                lines += [
                    f"Source: {cite['title']} | page/section {cite['page']} | {cite['published_date'] or 'Publication date unknown; timing not checked'}",
                    f"Evidence quote: {cite['quote']}",
                    f"Original link: {cite['source_url'] or 'Attached file / supplied text'}",
                ]
            if not item["citations"]:
                lines.append(
                    "No supporting or contradicting passage was cited; more evidence may be needed."
                )
    else:
        lines.append(
            "This analysis has no accepted findings." if run else "Analysis has not been run."
        )
    lines += [
        "",
        "4. HANDOFF",
        f"Queue: {flow['queue']}",
        f"Owner: {flow['owner'] or 'Unassigned'}",
        f"Workflow: {flow['stage'].replace('_', ' ').capitalize()}",
        f"Next action: {flow['next_action'] or 'Not recorded'}",
        "Routing is an internal queue record. No email or external assignment has been sent.",
        "",
        "5. TRACEABILITY",
    ]
    if run:
        lines += [
            f"Analysis ID: {run['id']}",
            f"Created: {run['created_at']} UTC",
            f"Model: {run['provider']} / {run['model']}",
            f"Documents in this analysis: {len(run['document_ids'])}",
        ]
        if set(run["document_ids"]) != {d["id"] for d in case["documents"]}:
            lines.append(
                "The current evidence set differs from this analysis. Run again to use the current documents."
            )
    lines += [
        "",
        "6. SCOPE",
        "Selected claims compared with supplied passages. Exact quotes establish provenance, not model correctness. This is not a disclosure-compliance determination.",
    ]
    return "\n".join(lines)
