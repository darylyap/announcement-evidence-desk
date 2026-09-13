import io
import json
from datetime import timedelta

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from desk.analysis import GroundingError, analyze
from desk.db import Run, Session, now
from desk.documents import chunks, extract_pdf, retrieve
from desk.provider import ProviderError
from desk.runs import execute_run, expire_runs
from desk.schemas import Claims, Findings

ARTICLE = "Harbour Systems reported revenue of S$120 million for the first half of 2026. The board approved the financial statements in September 2026."
CASE = {
    "title": "First-half results review",
    "issuer": "Harbour Systems",
    "article": ARTICLE,
    "article_date": "2026-09-10",
    "source_url": None,
}
DOC = {
    "title": "First-half results filing",
    "text": ARTICLE,
    "published_date": "2026-09-09",
    "source_url": None,
}


class TestModel:
    def complete(self, system, user, schema):
        if schema is Claims:
            return Claims(
                claims=[
                    {
                        "text": "Revenue was S$120 million for the first half of 2026.",
                        "article_quote": "Harbour Systems reported revenue of S$120 million for the first half of 2026.",
                    }
                ]
            )
        claims = json.loads(user)["claims"]
        return Findings(
            findings=[
                {
                    "claim_id": c["claim_id"],
                    "verdict": "supported",
                    "explanation": "The quoted filing explicitly reports the same revenue and period.",
                    "citations": [
                        {
                            "chunk_id": c["passages"][0]["chunk_id"],
                            "quote": "Harbour Systems reported revenue of S$120 million for the first half of 2026.",
                        }
                    ],
                }
                for c in claims
            ]
        )


def process_one(provider):
    with Session.begin() as session:
        expire_runs(session)
        run = session.scalar(select(Run).where(Run.status == "queued"))
        run_id = run.id if run else None
    if run_id is None:
        return False
    execute_run(run_id, provider)
    return True


def sources():
    return [
        {
            "id": "d1",
            "title": DOC["title"],
            "source_url": None,
            "published_date": "2026-09-11",
            "pages": [{"page": 2, "text": DOC["text"]}],
            "sha256": "testhash",
        }
    ]


def create(client):
    c = client.post("/api/cases", json=CASE)
    assert c.status_code == 201
    cid = c.json()["id"]
    d = client.post(f"/api/cases/{cid}/documents", json=DOC)
    assert d.status_code == 201
    return cid, d.json()["id"]


def test_exact_quotes_and_later_filing_flag():
    r = analyze(CASE, sources(), TestModel())
    c = r["findings"][0]["citations"][0]
    assert c["page"] == 2 and c["after_article"] is True
    assert r["review_required"] is True


@pytest.mark.parametrize("failure", ["quote", "chunk", "empty", "duplicate", "article"])
def test_rejects_ungrounded_or_incomplete_output(failure):
    class BadModel(TestModel):
        def complete(self, system, user, schema):
            result = super().complete(system, user, schema)
            if schema is Claims and failure == "article":
                result.claims[0].article_quote = "Invented text that was never in the article."
            elif schema is Findings:
                f = result.findings[0]
                if failure == "quote":
                    f.citations[0].quote = "Invented source quotation, unrelated to the filing."
                if failure == "chunk":
                    f.citations[0].chunk_id = "other-case:secret-passage"
                if failure == "empty":
                    f.citations = []
                if failure == "duplicate":
                    result.findings.append(f)
            return result

    with pytest.raises(GroundingError):
        analyze(CASE, sources(), BadModel())


def test_retrieval_retains_page_and_document_boundaries():
    corpus = chunks(
        sources()
        + [
            {
                **sources()[0],
                "id": "d2",
                "pages": [
                    {"page": 1, "text": "Legal matters: a pending lawsuit concerns a supplier."}
                ],
            }
        ]
    )
    selected = retrieve("pending lawsuit supplier", corpus, k=1)
    assert selected[0]["document_id"] == "d2" and selected[0]["page"] == 1


def test_pdf_rejects_invalid_and_scanned_files():
    with pytest.raises(ValueError, match="Upload a PDF"):
        extract_pdf(b"not a pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="OCR"):
        extract_pdf(out.getvalue())


def test_pdf_page_limit():
    writer = PdfWriter()
    for _ in range(41):
        writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match="40 pages"):
        extract_pdf(out.getvalue())


def test_all_case_data_requires_key(client):
    cid, _ = create(client)
    client.headers.pop("X-Access-Key")
    for path in ["/api/cases", f"/api/cases/{cid}", f"/api/cases/{cid}/brief"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/cases", json=CASE).status_code == 401
    assert client.get("/api/health").status_code == 200


def test_arbitrary_case_persists_with_sources(client):
    cid, did = create(client)
    fetched = client.get(f"/api/cases/{cid}").json()
    assert fetched["article"] == ARTICLE and fetched["documents"][0]["id"] == did
    assert fetched["documents"][0]["pages"][0]["text"] == ARTICLE


def test_documents_duplicate_and_url_validation(client):
    cid, _ = create(client)
    assert client.post(f"/api/cases/{cid}/documents", json=DOC).status_code == 409
    assert (
        client.post("/api/cases", json={**CASE, "source_url": "javascript:alert(1)"}).status_code
        == 422
    )


def test_missing_docs_and_invalid_pdf_are_actionable(client):
    cid = client.post("/api/cases", json=CASE).json()["id"]
    assert client.post(f"/api/cases/{cid}/runs").status_code == 422
    r = client.post(
        f"/api/cases/{cid}/documents/pdf",
        data={"title": "Bad file", "published_date": "2026-09-09"},
        files={"file": ("bad.pdf", b"not a PDF", "application/pdf")},
    )
    assert r.status_code == 422 and "Upload a PDF" in r.text


def test_active_run_unique_and_document_snapshot_frozen(client):
    cid, did = create(client)
    r = client.post(f"/api/cases/{cid}/runs")
    assert r.status_code == 201 and r.json()["document_ids"] == [did]
    assert client.post(f"/api/cases/{cid}/runs").status_code == 409
    client.post(
        f"/api/cases/{cid}/documents",
        json={
            **DOC,
            "title": "New document",
            "text": DOC["text"] + " Additional details were published later.",
        },
    )
    assert process_one(TestModel())
    old = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert old["status"] == "succeeded" and old["document_ids"] == [did]


def test_new_runs_never_delete_decisions(client):
    cid, _ = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    process_one(TestModel())
    d = {
        "verdict": "accept",
        "reviewer": "Test reviewer",
        "note": "Verified the exact revenue and period in the filing.",
    }
    assert client.post(f"/api/runs/{rid}/decisions", json=d).status_code == 201
    new = client.post(f"/api/cases/{cid}/runs").json()["id"]
    assert new != rid
    process_one(TestModel())
    runs = client.get(f"/api/cases/{cid}").json()["runs"]
    assert len(runs) == 2 and len(next(r for r in runs if r["id"] == rid)["decisions"]) == 1


def test_outage_is_saved_and_not_replaced_with_fake_results(client):
    class Offline(TestModel):
        def complete(self, *args):
            raise ProviderError("Provider temporarily unavailable")

    cid, _ = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    process_one(Offline())
    r = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert r["status"] == "failed" and r["result"] is None
    assert (
        client.post(
            f"/api/runs/{rid}/decisions",
            json={"verdict": "accept", "reviewer": "a", "note": "Test reason"},
        ).status_code
        == 409
    )
    assert client.post(f"/api/cases/{cid}/runs").status_code == 201


def test_expired_job_is_recoverable_without_losing_history(client):
    cid, _ = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    with Session.begin() as s:
        r = s.get(Run, rid)
        r.status = "running"
        r.lease_until = now() - timedelta(seconds=1)
        r.owner = "old-worker"
    assert process_one(TestModel()) is False
    r = client.get(f"/api/cases/{cid}").json()["runs"][0]
    assert r["status"] == "failed" and "interrupted" in r["error"]
    assert client.post(f"/api/cases/{cid}/runs").status_code == 201


def test_key_check_configuration_failure(client, monkeypatch):
    from desk import config

    monkeypatch.setattr(config, "ACCESS_KEY", "")
    assert client.get("/api/cases").status_code == 503


def test_page_and_basic_security_headers(client):
    r = client.get("/")
    assert r.status_code == 200 and "Evidence Desk" in r.text
    assert r.headers["x-content-type-options"] == "nosniff"


def test_real_text_pdf_upload_extracts_pages(client):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 30 740 Td ({ARTICLE}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    cid = client.post("/api/cases", json=CASE).json()["id"]
    r = client.post(
        f"/api/cases/{cid}/documents/pdf",
        data={"title": "Results PDF", "published_date": "2026-09-09"},
        files={"file": ("results.pdf", output.getvalue(), "application/pdf")},
    )
    assert r.status_code == 201 and r.json()["pages"][0]["page"] == 1
    assert "S$120 million" in r.json()["pages"][0]["text"]


def test_cross_origin_writes_rejected(client):
    assert (
        client.post(
            "/api/cases", json=CASE, headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/cases", json=CASE, headers={"Origin": "http://testserver"}).status_code
        == 201
    )


def test_request_completes_analysis_without_a_background_worker(client, monkeypatch):
    monkeypatch.setattr("desk.main.execute_run", lambda rid: execute_run(rid, TestModel()))
    cid, _ = create(client)
    response = client.post(f"/api/cases/{cid}/runs")
    assert response.status_code == 201
    assert response.json()["status"] == "succeeded"
    assert response.json()["result"]["findings"][0]["verdict"] == "supported"


def test_latest_assessment_controls_case_status_and_brief(client):
    cid, _ = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(rid, TestModel())
    for verdict in ["accept", "needs_evidence"]:
        response = client.post(
            f"/api/runs/{rid}/decisions",
            json={
                "verdict": verdict,
                "reviewer": "Analyst",
                "note": "Check the complete filing for the same period.",
            },
        )
        assert response.status_code == 201
    assert client.get("/api/cases").json()[0]["status"] == "needs_evidence"
    brief = client.get(f"/api/cases/{cid}/brief")
    assert brief.status_code == 200 and "More evidence needed" in brief.text
    assert "Harbour Systems reported revenue" in brief.text
    client.headers.pop("X-Access-Key")
    assert client.get(f"/api/cases/{cid}/brief").status_code == 401


def test_nonfactual_text_produces_an_actionable_failure():
    class NoClaims(TestModel):
        def complete(self, *args):
            return Claims(claims=[])

    with pytest.raises(GroundingError, match="No checkable factual claims"):
        analyze(CASE, sources(), NoClaims())


def test_vercel_requires_database_key_and_cloud_model(monkeypatch):
    from desk import config

    monkeypatch.setattr(config, "HOSTED", True)
    monkeypatch.setattr(config, "REQUIRE_KEY", True)
    monkeypatch.setattr(config, "ACCESS_KEY", "test-key")
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///local.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        config.validate_hosting()
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://test/database")
    monkeypatch.setattr(config, "PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="Gemini"):
        config.validate_hosting()
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    config.validate_hosting()


@pytest.mark.parametrize("failure", [None, 429, 503])
def test_gemini_adapter_uses_schema_timeout_and_no_hidden_retries(monkeypatch, failure):
    from types import SimpleNamespace

    from google import genai

    from desk import config
    from desk.provider import Provider

    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            captured.update(kwargs)
            if failure:
                error = RuntimeError("Private provider response: test-key")
                error.code = failure
                raise error
            return SimpleNamespace(text='{"claims": []}')

    monkeypatch.setattr(genai, "Client", Client)
    if failure:
        with pytest.raises(ProviderError) as caught:
            Provider("gemini", "test-model").complete("system", "input", Claims)
        assert "test-key" not in str(caught.value)
        assert ("quota" if failure == 429 else "temporarily unavailable") in str(caught.value)
    else:
        assert Provider("gemini", "test-model").complete("system", "input", Claims).claims == []
    assert captured["config"]["response_json_schema"] == Claims.model_json_schema()
    assert captured["http_options"].retry_options.attempts == 1
    assert captured["http_options"].timeout == int(config.TIMEOUT * 1000)


def test_loopback_access_is_open_unless_explicitly_protected():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "from desk import config; print(bool(config.ACCESS_KEY))"],
        env={
            **os.environ,
            "VERCEL": "0",
            "REQUIRE_ACCESS_KEY": "0",
            "APP_ACCESS_KEY": "test-value",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
