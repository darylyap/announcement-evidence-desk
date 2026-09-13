import json

from sqlalchemy import select
from test_evidence import TestModel, create

from desk.db import Decision, DecisionClaim, Session
from desk.runs import execute_run
from desk.schemas import Claims, Findings


class TwoClaimModel(TestModel):
    def complete(self, system, user, schema):
        if schema is Claims:
            result = super().complete(system, user, schema)
            result.claims.append(
                type(result.claims[0])(
                    text="The board approved the financial statements in September 2026.",
                    article_quote="The board approved the financial statements in September 2026.",
                )
            )
            return result
        claims = json.loads(user)["claims"]
        return Findings(
            findings=[
                {
                    "claim_id": c["claim_id"],
                    "verdict": "supported",
                    "explanation": "The filing states this fact explicitly.",
                    "citations": [
                        {"chunk_id": c["passages"][0]["chunk_id"], "quote": c["article_quote"]}
                    ],
                }
                for c in claims
            ]
        )


def setup_review(client):
    cid, _ = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(rid, TwoClaimModel())
    run = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert run["status"] == "succeeded", run["error"]
    return cid, rid, [f["claim_id"] for f in run["result"]["findings"]]


def assess(client, rid, claim_id, verdict="accept", note="Revenue checked against the filing."):
    return client.post(
        f"/api/runs/{rid}/decisions",
        json={
            "claim_id": claim_id,
            "verdict": verdict,
            "reviewer": "Analyst A",
            "note": note,
        },
    )


def test_claim_assessments_progress_revisions_and_brief(client):
    cid, rid, claims = setup_review(client)
    assert assess(client, rid, claims[0]).status_code == 201
    case = client.get("/api/cases").json()[0]
    assert case["status"] == "partially_reviewed"
    assert case["assessment"]["pending"] == 1
    brief = client.get(f"/api/cases/{cid}/brief").text
    first, second = brief.split("Claim 2 —")
    assert "Revenue checked" in first and "Revenue checked" not in second
    assert "Pending human review" in second
    assert (
        assess(client, rid, claims[1], "needs_evidence", "Confirm the approval date.").status_code
        == 201
    )
    case = client.get("/api/cases").json()[0]
    assert case["status"] == "needs_evidence" and case["assessment"]["assessed"] == 2
    assert (
        assess(
            client, rid, claims[1], "accept", "Approval date confirmed in the filing."
        ).status_code
        == 201
    )
    detail = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert detail["assessment"]["status"] == "reviewed"
    assert len(detail["decisions"]) == 3
    assert detail["assessment"]["needs_evidence"] == 0
    brief = client.get(f"/api/cases/{cid}/brief").text
    assert "Approval date confirmed" in brief and "Confirm the approval date." not in brief


def test_claim_required_for_multiple_findings_and_validated(client):
    _, rid, claims = setup_review(client)
    assert assess(client, rid, None).status_code == 422
    assert assess(client, rid, "claim-does-not-exist").status_code == 422
    assert assess(client, rid, claims[0]).json()["claim_id"] == claims[0]


def test_overall_history_is_preserved_without_applying_to_claims(client):
    cid, rid, claims = setup_review(client)
    with Session.begin() as s:
        s.add(
            Decision(
                run_id=rid,
                verdict="accept",
                reviewer="Earlier reviewer",
                note="Earlier overall judgement.",
            )
        )
    run = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert run["decisions"][0]["claim_id"] is None
    assert run["assessment"]["assessed"] == 0
    assert "earlier overall assessment" in client.get(f"/api/cases/{cid}/brief").text
    assess(client, rid, claims[0])
    assert client.get(f"/api/cases/{cid}").json()["runs"][0]["assessment"]["assessed"] == 1


def test_assessments_do_not_carry_into_retry_and_delete_cleans_mapping(client):
    cid, rid, claims = setup_review(client)
    decision = assess(client, rid, claims[0]).json()
    second = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(second, TwoClaimModel())
    runs = client.get(f"/api/cases/{cid}").json()["runs"]
    assert runs[0]["assessment"]["assessed"] == 0
    assert runs[1]["assessment"]["assessed"] == 1
    assert client.delete(f"/api/cases/{cid}").status_code == 200
    with Session() as s:
        assert s.get(Decision, decision["id"]) is None
        assert s.scalar(select(DecisionClaim)) is None
