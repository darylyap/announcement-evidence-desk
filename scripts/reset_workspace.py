"""Back up shared review records, clear reviews/custom workspaces and add one DBS example."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8012")
    parser.add_argument(
        "--confirm-reset", required=True, help="Exact target hostname, including port if present"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        required=True,
        help="Private directory outside the public repository",
    )
    args = parser.parse_args()
    if args.confirm_reset != urlparse(args.url).netloc:
        parser.error("--confirm-reset must match the target hostname and port")
    root = Path(__file__).resolve().parent.parent
    dest = args.backup_dir.resolve()
    if dest == root or root in dest.parents:
        parser.error("Keep backups outside this public repository")
    values = dotenv_values(root / ".env")
    key = os.getenv("APP_ACCESS_KEY") or values.get("APP_ACCESS_KEY") or ""
    with httpx.Client(
        base_url=args.url.rstrip("/"), headers={"X-Access-Key": key}, timeout=90
    ) as c:

        def get(path):
            r = c.get(path)
            r.raise_for_status()
            return r

        cases = get("/api/cases").json()
        details = [get(f"/api/cases/{x['id']}").json() for x in cases]
        if any(r["status"] in ("queued", "running") for d in details for r in d["runs"]):
            raise SystemExit("An analysis is active. Wait for it to finish before resetting.")
        workspaces = get("/api/workspaces").json()
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = dest / f"reviews-{stamp}.zip"
        with ZipFile(backup, "x", ZIP_DEFLATED) as z:
            z.writestr(
                "records.json",
                json.dumps({"url": args.url, "workspaces": workspaces, "cases": details}, indent=2),
            )
            for d in details:
                for doc in d["documents"] + d.get("historical_documents", []):
                    if doc["has_file"]:
                        z.writestr(
                            f"files/{doc['id']}", get(f"/api/documents/{doc['id']}/file").content
                        )
        backup.chmod(0o600)
        with ZipFile(backup) as z:
            assert z.testzip() is None
        for case in cases:
            r = c.delete(f"/api/cases/{case['id']}")
            r.raise_for_status()
        for workspace in workspaces:
            if workspace["id"] not in ("general", "examples"):
                r = c.delete(f"/api/workspaces/{workspace['id']}")
                r.raise_for_status()
        r = c.post("/api/examples/dbs-two-claims")
        r.raise_for_status()
        assert len(get("/api/cases").json()) == 1
        print(f"Reset complete. One DBS two-claim example, ready to analyze. Backup: {backup}")


if __name__ == "__main__":
    main()
