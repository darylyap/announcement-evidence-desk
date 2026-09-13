"""Run one real two-claim review; remove test records unless --keep is set."""

import argparse
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8012")
    parser.add_argument("--provider", choices=["ollama", "gemini"])
    parser.add_argument("--require-hosted", action="store_true")
    parser.add_argument(
        "--keep", action="store_true", help="Keep the real-source example and saved assessments"
    )
    args = parser.parse_args()
    values = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("APP_ACCESS_KEY") or values.get("APP_ACCESS_KEY") or ""
    with httpx.Client(
        base_url=args.url.rstrip("/"), headers={"X-Access-Key": key}, timeout=280
    ) as c:
        health = c.get("/api/health")
        health.raise_for_status()
        if args.require_hosted:
            assert health.json()["storage"] == "postgresql"
            assert health.json()["access_required"]
            assert health.json()["model"]["provider"] == "gemini"
        response = c.post("/api/examples/dbs-two-claims")
        response.raise_for_status()
        cid = response.json()["id"]
        try:
            print("Running real DBS two-claim comparison…", flush=True)
            response = c.post(f"/api/cases/{cid}/runs", json={"provider": args.provider})
            response.raise_for_status()
            run = response.json()
            assert run["status"] == "succeeded", run.get("error")
            findings = run["result"]["findings"]
            assert len(findings) == 2
            assert any(
                "net profit" in f["text"].lower() and f["verdict"] == "supported" for f in findings
            )
            assert any(
                "total income" in f["text"].lower() and f["verdict"] == "contradicted"
                for f in findings
            )
            for index, finding in enumerate(findings):
                response = c.post(
                    f"/api/runs/{run['id']}/decisions",
                    json={
                        "claim_id": finding["claim_id"],
                        "verdict": "accept",
                        "reviewer": "Analyst A",
                        "note": f"Automated workflow check: expected example finding for claim {index + 1}.",
                    },
                )
                response.raise_for_status()
                response = c.get(f"/api/cases/{cid}")
                response.raise_for_status()
                detail = response.json()
                assert detail["runs"][0]["assessment"]["assessed"] == index + 1
            doc = detail["documents"][0]
            page = c.get(f"/api/documents/{doc['id']}/pages/1.png")
            page.raise_for_status()
            assert page.content.startswith(b"\x89PNG")
            brief = c.get(f"/api/cases/{cid}/brief")
            brief.raise_for_status()
            assert "Claims assessed: 2 of 2" in brief.text
            assert brief.text.count("Human assessment: Agrees with AI finding") == 2
            if health.json()["access_required"]:
                assert c.get("/api/cases", headers={"X-Access-Key": ""}).status_code == 401
            print(
                f"PASS: {run['provider']} / {run['model']}; {run['latency_ms'] / 1000:.1f}s; separate assessments, PDF page and brief verified."
            )
        finally:
            if not args.keep:
                response = c.delete(f"/api/cases/{cid}")
                response.raise_for_status()
                print("Temporary verification review removed.")


if __name__ == "__main__":
    main()
