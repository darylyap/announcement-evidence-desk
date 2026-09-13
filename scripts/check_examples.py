"""Live checks using bundled public PDFs and labelled test claims."""

import argparse
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8012")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse existing example reviews; retry only failed analyses",
    )
    parser.add_argument("--example", help="Check one example ID instead of all five")
    parser.add_argument("--provider", choices=["ollama", "gemini"])
    parser.add_argument("--keep", action="store_true", help="Keep newly created example reviews")
    args = parser.parse_args()
    values = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("APP_ACCESS_KEY") or values.get("APP_ACCESS_KEY") or ""
    failures = []
    with httpx.Client(
        base_url=args.url.rstrip("/"), headers={"X-Access-Key": key}, timeout=280
    ) as client:
        examples = client.get("/api/examples")
        examples.raise_for_status()
        selected = [e for e in examples.json() if not args.example or e["id"] == args.example]
        if not selected:
            parser.error("Unknown example ID")
        for example in selected:
            case = None
            if args.reuse:
                items = client.get("/api/cases")
                items.raise_for_status()
                case = next(
                    (x for x in items.json() if x["title"] == "Test claims · " + example["title"]),
                    None,
                )
            created = not case
            if not case:
                result = client.post("/api/examples/" + example["id"])
                result.raise_for_status()
                case = result.json()
            try:
                result = client.get("/api/cases/" + case["id"])
                result.raise_for_status()
                detail = result.json()
                run = detail["runs"][0] if detail["runs"] else None
                if not run or run["status"] == "failed":
                    result = client.post(
                        f"/api/cases/{case['id']}/runs", json={"provider": args.provider}
                    )
                    result.raise_for_status()
                    run = result.json()
                findings = (run.get("result") or {}).get("findings", [])
                if "expected_findings" in example:
                    expected = example["expected_findings"]
                    good = (
                        run["status"] == "succeeded"
                        and len(findings) == len(expected)
                        and all(
                            sum(
                                e["subject"] in f["text"].lower() and f["verdict"] == e["verdict"]
                                for f in findings
                            )
                            == 1
                            for e in expected
                        )
                    )
                else:
                    expected = {
                        "Supported": "supported",
                        "Contradicted": "contradicted",
                        "Insufficient evidence": "insufficient",
                    }[example["expected"]]
                    good = (
                        run["status"] == "succeeded"
                        and len(findings) == 1
                        and findings[0]["verdict"] == expected
                    )
                print(
                    f"{'PASS' if good else 'FAIL'}: {example['id']}; case={case['id']}; model={run['model']}",
                    flush=True,
                )
                if not good:
                    print(run.get("error") or [f["verdict"] for f in findings], flush=True)
                    failures.append(example["id"])
                doc = detail["documents"][0]
                image = client.get(f"/api/documents/{doc['id']}/pages/1.png")
                image.raise_for_status()
                assert image.content.startswith(b"\x89PNG"), "Original PDF page preview failed"
            finally:
                if created and not args.keep:
                    deleted = client.delete(f"/api/cases/{case['id']}")
                    deleted.raise_for_status()

    if failures:
        raise SystemExit("Inspect failed examples: " + ", ".join(failures))
    print(
        "Verified all selected live examples and original PDF page rendering. These are illustrative checks, not an accuracy benchmark."
    )


if __name__ == "__main__":
    main()
