import io
from zipfile import ZipFile

import httpx
import pytest
from test_evidence import TestModel, create

from desk import config
from desk.imports import parse_file, validate_link
from desk.runs import execute_run


def test_workspace_routing_archive_and_restore(client):
    cid, _ = create(client)
    w = client.post("/api/workspaces", json={"name": "Bank coverage"}).json()
    payload = {
        "workspace_id": w["id"],
        "topic": "Results",
        "owner": "Analyst A",
        "queue": "Second review",
        "stage": "archived",
        "next_action": "Check the reporting period.",
    }
    assert client.patch(f"/api/cases/{cid}/workflow", json=payload).status_code == 200
    case = client.get(f"/api/cases/{cid}").json()
    assert case["workflow"]["owner"] == "Analyst A"
    assert client.get("/api/cases").json()[0]["workflow"]["stage"] == "archived"
    assert (
        client.patch(f"/api/cases/{cid}/workflow", json={**payload, "stage": "open"}).status_code
        == 200
    )
    assert (
        client.patch("/api/workspaces/" + w["id"], json={"name": "Financials"}).status_code == 200
    )
    assert (
        client.patch(
            f"/api/cases/{cid}/workflow", json={**payload, "workspace_id": "missing"}
        ).status_code
        == 422
    )


def test_bundled_pdf_original_page_and_access(client):
    c = client.post("/api/examples/dbs-supported").json()
    detail = client.get("/api/cases/" + c["id"]).json()
    doc = detail["documents"][0]
    original = (config.ROOT / "examples/dbs-fy2025-results.pdf").read_bytes()
    assert doc["has_file"] and len(doc["pages"]) == 8
    assert client.get(f"/api/documents/{doc['id']}/file").content == original
    page = client.get(f"/api/documents/{doc['id']}/pages/1.png")
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG")
    assert client.get(f"/api/documents/{doc['id']}/pages/100.png").status_code == 404
    assert (
        client.get(f"/api/documents/{doc['id']}/file", headers={"X-Access-Key": ""}).status_code
        == 401
    )
    assert client.get("/api/examples/dbs/file").content == original


def test_file_upload_and_article_preview(client):
    cid, _ = create(client)
    text = b"An issuer reported annual revenue of S$123 million in the year ended 31 December 2025. This is test source text."
    preview = client.post("/api/imports/file", files={"file": ("news.txt", text, "text/plain")})
    assert preview.status_code == 200 and preview.json()["text"] == text.decode()
    upload = client.post(
        f"/api/cases/{cid}/documents/file",
        data={"title": "Source text file", "published_date": "2026-01-01"},
        files={"file": ("source.txt", text, "text/plain")},
    )
    assert upload.status_code == 201
    assert client.get(f"/api/documents/{upload.json()['id']}/file").content == text
    assert (
        client.post(
            "/api/imports/file", files={"file": ("old.doc", text, "application/msword")}
        ).status_code
        == 422
    )


def test_docx_extraction_and_unsupported_files():
    b = io.BytesIO()
    with ZipFile(b, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + ("Public issuer statement. " * 10)
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    pages, kind, _ = parse_file(b.getvalue(), "filing.docx")
    assert kind == "docx" and "Public issuer statement." in pages[0]["text"]
    with pytest.raises(ValueError):
        parse_file(b"not an image document", "image.png")
    with pytest.raises(ValueError):
        parse_file(b"x" * (config.MAX_UPLOAD + 1), "large.txt")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.dbs.com/news",
        "https://127.0.0.1/",
        "https://dbs.com.evil.example/",
        "https://user:password@www.dbs.com/",
        "https://www.dbs.com:444/",
    ],
)
def test_link_import_denies_unapproved_destinations(url):
    with pytest.raises(ValueError):
        validate_link(url)


def test_link_import_checks_dns_and_redirect(monkeypatch):
    from desk import imports

    monkeypatch.setattr(
        imports.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError):
        validate_link("https://www.dbs.com/")
    monkeypatch.setattr(
        imports.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))]
    )
    original = httpx.Client
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/private"})

    monkeypatch.setattr(
        imports.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(ValueError):
        imports.fetch_link("https://www.dbs.com/start")
    assert len(calls) == 1


def test_selected_history_brief_and_cross_case_guard(client):
    cid, _ = create(client)
    first = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(first, TestModel())
    client.post(
        f"/api/runs/{first}/decisions",
        json={
            "verdict": "accept",
            "reviewer": "First reviewer",
            "note": "Source figure confirmed.",
        },
    )
    second = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(second, TestModel())
    result = client.get(f"/api/cases/{cid}/brief?run_id={first}")
    assert first in result.text and "First reviewer" in result.text and "4. HANDOFF" in result.text
    assert "First reviewer" not in client.get(f"/api/cases/{cid}/brief?run_id={second}").text
    other, _ = create(client)
    assert client.get(f"/api/cases/{other}/brief?run_id={first}").status_code == 404


def test_hosted_provider_cannot_select_local_ollama(client, monkeypatch):
    monkeypatch.setattr(config, "HOSTED", True)
    cid, _ = create(client)
    assert client.post(f"/api/cases/{cid}/runs", json={"provider": "ollama"}).status_code == 422


def test_html_form_wrapper_does_not_hide_announcement_text():
    text = "SGX Group reported net revenue of S$1,298.2 million for FY2025. " + (
        "Public financial statement. " * 5
    )
    raw = (
        '<html><body><form><input value="ignore"><h1>Announcement</h1><p>'
        + text
        + "</p></form></body></html>"
    ).encode()
    pages, kind, _ = parse_file(raw, "announcement.html", "text/html")
    assert kind == "html" and "S$1,298.2 million" in pages[0]["text"]


def test_delete_review_removes_history_and_files_only_for_that_review(client):
    from sqlalchemy import select

    from desk.db import Decision, Document, Run, Session, SourceFile

    c = client.post("/api/examples/dbs-supported").json()
    other, _ = create(client)
    cid = c["id"]
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(rid, TestModel())
    # The model fixture need not match this PDF; deletion must also handle failed runs.
    assert client.delete(f"/api/cases/{cid}", headers={"X-Access-Key": ""}).status_code == 401
    assert client.delete(f"/api/cases/{cid}").status_code == 200
    assert client.get(f"/api/cases/{cid}").status_code == 404
    assert client.get(f"/api/cases/{other}").status_code == 200
    with Session() as s:
        assert not s.scalars(select(SourceFile)).all()
        assert not s.scalars(select(Run).where(Run.case_id == cid)).all()
        assert not s.scalars(select(Document).where(Document.case_id == cid)).all()
        assert not s.scalars(select(Decision).where(Decision.run_id == rid)).all()


def test_active_review_cannot_be_deleted(client):
    cid, _ = create(client)
    client.post(f"/api/cases/{cid}/runs")
    assert client.delete(f"/api/cases/{cid}").status_code == 409
    assert client.get(f"/api/cases/{cid}").status_code == 200


def test_delete_workspace_moves_reviews_and_preserves_sources(client):
    cid, _ = create(client)
    wid = client.post("/api/workspaces", json={"name": "Temporary coverage"}).json()["id"]
    client.patch(f"/api/cases/{cid}/workflow", json={"workspace_id": wid, "owner": "Analyst A"})
    assert client.delete(f"/api/workspaces/{wid}").status_code == 200
    c = client.get(f"/api/cases/{cid}").json()
    assert c["workflow"]["workspace_id"] == "general"
    assert c["workflow"]["owner"] == "Analyst A"
    assert len(c["documents"]) == 1
    assert client.delete("/api/workspaces/general").status_code == 409
    assert client.delete("/api/workspaces/examples").status_code == 409


def test_remove_unused_source_but_preserve_analyzed_evidence(client):
    cid, _ = create(client)
    doc = client.get(f"/api/cases/{cid}").json()["documents"][0]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert client.get(f"/api/cases/{cid}").json()["documents"] == []
    cid, _ = create(client)
    doc = client.get(f"/api/cases/{cid}").json()["documents"][0]
    client.post(f"/api/cases/{cid}/runs")
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 409


def test_unknown_publication_date_can_be_uploaded_and_has_no_timing_claim(client):
    from test_evidence import ARTICLE, CASE, sources

    from desk.analysis import analyze

    cid, _ = create(client)
    r = client.post(
        f"/api/cases/{cid}/documents/file",
        data={"title": "Undated source"},
        files={"file": ("undated.txt", (ARTICLE + " More context.").encode(), "text/plain")},
    )
    assert r.status_code == 201 and r.json()["published_date"] == ""
    docs = sources()
    docs[0]["published_date"] = ""
    result = analyze(CASE, docs, TestModel())
    assert result["findings"][0]["citations"][0]["after_article"] is False
    assert result["findings"][0]["citations"][0]["published_date"] == ""


def test_edit_metadata_preserves_original_analysis_and_retry_uses_current_source(client):
    cid, did = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(rid, TestModel())
    original = client.get(f"/api/cases/{cid}").json()
    edited = client.patch(
        f"/api/documents/{did}",
        json={"title": "Corrected filing title", "published_date": "2026-09-12"},
    )
    assert edited.status_code == 200
    replacement = edited.json()["id"]
    assert replacement != did
    current = client.get(f"/api/cases/{cid}").json()
    assert [d["id"] for d in current["documents"]] == [replacement]
    assert current["historical_documents"][0]["id"] == did
    assert current["runs"][0]["result"] == original["runs"][0]["result"]
    assert current["historical_documents"][0]["published_date"] == "2026-09-09"
    assert "current evidence set differs" in client.get(f"/api/cases/{cid}/brief").text
    retry = client.post(f"/api/cases/{cid}/runs").json()
    assert retry["document_ids"] == [replacement]
    assert (
        client.patch(f"/api/documents/{replacement}", json={"title": "Another title"}).status_code
        == 409
    )


def test_failed_replacement_keeps_current_evidence_and_cross_review_is_rejected(client):
    cid, did = create(client)
    other, other_did = create(client)
    data = {"title": "Replacement", "replace_document_id": did}
    bad = client.post(
        f"/api/cases/{cid}/documents/file",
        data=data,
        files={"file": ("broken.pdf", b"bad pdf", "application/pdf")},
    )
    assert bad.status_code == 422
    assert client.get(f"/api/cases/{cid}").json()["documents"][0]["id"] == did
    from test_evidence import ARTICLE

    wrong = client.post(
        f"/api/cases/{cid}/documents/file",
        data={**data, "replace_document_id": other_did},
        files={"file": ("valid.txt", (ARTICLE + " Updated context.").encode(), "text/plain")},
    )
    assert wrong.status_code == 404
    assert client.get(f"/api/cases/{other}").json()["documents"][0]["id"] == other_did


def test_replacement_and_removal_keep_historical_pdf_available(client):
    from desk.db import Run, Session

    c = client.post("/api/examples/dbs-supported").json()
    cid = c["id"]
    old = client.get(f"/api/cases/{cid}").json()["documents"][0]
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    with Session.begin() as s:
        r = s.get(Run, rid)
        r.status = "failed"
        r.active_key = None
    data = (config.ROOT / "examples/sgx-fy2025-results.pdf").read_bytes()
    replacement = client.post(
        f"/api/cases/{cid}/documents/file",
        data={"title": "SGX replacement", "replace_document_id": old["id"]},
        files={"file": ("sgx.pdf", data, "application/pdf")},
    )
    assert replacement.status_code == 201
    current = client.get(f"/api/cases/{cid}").json()
    assert len(current["documents"]) == 1 and len(current["historical_documents"]) == 1
    assert current["runs"][0]["document_ids"] == [old["id"]]
    assert client.get(f"/api/documents/{old['id']}/pages/1.png").status_code == 200
    assert client.get(f"/api/documents/{replacement.json()['id']}/file").content == data
    assert client.delete(f"/api/documents/{replacement.json()['id']}").status_code == 200
    assert client.post(f"/api/cases/{cid}/runs").status_code == 422
    assert client.delete(f"/api/cases/{cid}").status_code == 200
    assert client.get(f"/api/documents/{old['id']}/file").status_code == 404


def test_remove_used_source_excludes_it_from_next_attempt(client):
    cid, did = create(client)
    rid = client.post(f"/api/cases/{cid}/runs").json()["id"]
    execute_run(rid, TestModel())
    assert client.delete(f"/api/documents/{did}").status_code == 200
    current = client.get(f"/api/cases/{cid}").json()
    assert current["documents"] == []
    assert current["historical_documents"][0]["id"] == did
    assert current["runs"][0]["result"]["findings"][0]["citations"][0]["document_id"] == did
    assert client.post(f"/api/cases/{cid}/runs").status_code == 422


def test_official_link_is_sufficient_input_and_can_replace_evidence(client, monkeypatch):
    from test_evidence import ARTICLE

    cid, did = create(client)
    raw = (ARTICLE + " This is additional official source context.").encode()
    monkeypatch.setattr(
        "desk.main.fetch_link",
        lambda url: {
            "pages": [{"page": 1, "text": raw.decode()}],
            "source_url": url,
            "kind": "text",
            "raw": raw,
            "filename": "release.txt",
            "mime": "text/plain",
        },
    )
    response = client.post(
        f"/api/cases/{cid}/documents/url",
        json={
            "url": "https://www.dbs.com/release",
            "title": "Linked release",
            "replace_document_id": did,
        },
    )
    assert response.status_code == 201
    detail = client.get(f"/api/cases/{cid}").json()
    assert len(detail["documents"]) == 1
    doc = detail["documents"][0]
    assert doc["source_url"] == "https://www.dbs.com/release"
    assert client.get(f"/api/documents/{doc['id']}/file").content == raw


def test_two_claim_example_uses_real_pdf_without_precomputed_results(client):
    examples = client.get("/api/examples").json()
    item = next(e for e in examples if e["id"] == "dbs-two-claims")
    assert len(item["expected_findings"]) == 2
    result = client.post("/api/examples/dbs-two-claims")
    assert result.status_code == 201
    detail = client.get("/api/cases/" + result.json()["id"]).json()
    assert "11.0 billion" in detail["article"] and "28.9 billion" in detail["article"]
    assert detail["runs"] == []
    assert len(detail["documents"]) == 1
    assert detail["documents"][0]["sha256"]
    assert "expected_findings" not in detail
    assert "Supported + contradicted" not in detail["article"]
