import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from . import config
from .assessments import assessment_summary
from .db import (
    Base,
    Case,
    CaseWorkflow,
    Decision,
    DecisionClaim,
    Document,
    RetiredDocument,
    Run,
    Session,
    SourceFile,
    Workspace,
    engine,
    now,
)
from .documents import digest, extract_pdf
from .imports import ALLOWED_DOMAINS, fetch_link, parse_file
from .provider import Provider, ProviderError, provider_status
from .runs import execute_run, expire_runs
from .schemas import (
    AnalysisIn,
    CaseIn,
    DecisionIn,
    DocumentEditIn,
    DocumentIn,
    DocumentLinkIn,
    LinkIn,
    WorkflowIn,
    WorkspaceIn,
)


@asynccontextmanager
async def lifespan(app):
    config.validate_hosting()
    Base.metadata.create_all(engine)
    with Session.begin() as s:
        for wid, name in [("general", "General"), ("examples", "Source examples")]:
            if not s.get(Workspace, wid):
                s.add(Workspace(id=wid, name=name))
    yield


app = FastAPI(
    title="Announcement Evidence Desk", version="0.1.0", lifespan=lifespan, docs_url="/api/docs"
)
app.mount("/static", StaticFiles(directory=config.ROOT / "web"), name="static")


@app.middleware("http")
async def guard(request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin != str(request.base_url).rstrip("/")
    ):
        return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
    if length > config.MAX_UPLOAD + 65536:
        return JSONResponse(
            {"detail": "Request too large. Maximum PDF size is 4 MB."}, status_code=413
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path == "/api/docs":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none'"
        )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unexpected(request, exc):
    return JSONResponse(
        {"detail": "An internal error occurred. Saved data has been retained."}, status_code=500
    )


def auth(x_access_key: str = Header(default="")):
    if config.REQUIRE_KEY and not config.ACCESS_KEY:
        raise HTTPException(503, "Access is not configured")
    if config.ACCESS_KEY and not secrets.compare_digest(
        x_access_key.encode(), config.ACCESS_KEY.encode()
    ):
        raise HTTPException(401, "Enter the workspace access key in Settings")


def record(obj):
    return {
        c.name: getattr(obj, c.name)
        for c in obj.__table__.columns
        if c.name not in ("owner", "active_key")
    }


def get_case(s, cid, *, lock=False):
    query = select(Case).where(Case.id == cid)
    c = s.scalar(query.with_for_update() if lock else query)
    if c is None:
        raise HTTPException(404, "Case not found")
    return c


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.ROOT / "web" / "index.html")


@app.get("/api/health")
def health():
    with Session() as s:
        s.scalar(select(func.count()).select_from(Case))
    return {
        "ok": True,
        "app": "Announcement Evidence Desk",
        "storage": engine.url.get_backend_name(),
        "access_required": bool(config.ACCESS_KEY),
        "execution": "request",
        "model": {"provider": config.PROVIDER, "name": config.MODEL},
    }


@app.get("/api/provider", dependencies=[Depends(auth)])
def check_provider():
    return {
        **provider_status(),
        "hosted": config.HOSTED,
        "choices": ["gemini"] if config.HOSTED else ["ollama", "gemini"],
        "import_domains": ALLOWED_DOMAINS,
    }


def workflow(s, cid):
    item = s.get(CaseWorkflow, cid)
    return (
        {c.name: getattr(item, c.name) for c in item.__table__.columns}
        if item
        else WorkflowIn().model_dump()
    )


@app.get("/api/workspaces", dependencies=[Depends(auth)])
def workspaces():
    with Session() as s:
        return [record(w) for w in s.scalars(select(Workspace).order_by(Workspace.name))]


@app.post("/api/workspaces", dependencies=[Depends(auth)], status_code=201)
def add_workspace(body: WorkspaceIn):
    try:
        with Session.begin() as s:
            w = Workspace(name=body.name)
            s.add(w)
            s.flush()
            return record(w)
    except IntegrityError as e:
        raise HTTPException(409, "A workspace with that name already exists") from e


@app.patch("/api/workspaces/{wid}", dependencies=[Depends(auth)])
def rename_workspace(wid: str, body: WorkspaceIn):
    try:
        with Session.begin() as s:
            w = s.get(Workspace, wid)
            if not w:
                raise HTTPException(404, "Workspace not found")
            w.name = body.name
            s.flush()
            return record(w)
    except IntegrityError as e:
        raise HTTPException(409, "A workspace with that name already exists") from e


@app.delete("/api/workspaces/{wid}", dependencies=[Depends(auth)])
def delete_workspace(wid: str):
    if wid in ("general", "examples"):
        raise HTTPException(
            409, "Built-in workspaces cannot be deleted. Their reviews can be deleted."
        )
    with Session.begin() as s:
        w = s.get(Workspace, wid)
        if not w:
            raise HTTPException(404, "Workspace not found")
        s.execute(
            update(CaseWorkflow)
            .where(CaseWorkflow.workspace_id == wid)
            .values(workspace_id="general", updated_at=now())
        )
        s.delete(w)
    return {"deleted": True, "reviews_moved_to": "general"}


@app.delete("/api/cases/{cid}", dependencies=[Depends(auth)])
def delete_case(cid: str):
    with Session.begin() as s:
        c = get_case(s, cid, lock=True)
        expire_runs(s)
        runs = list(s.scalars(select(Run).where(Run.case_id == cid)))
        if any(r.status in ("queued", "running") for r in runs):
            raise HTTPException(
                409, "Wait for the current analysis to finish before deleting this review."
            )
        ids = select(Document.id).where(Document.case_id == cid)
        s.execute(delete(RetiredDocument).where(RetiredDocument.document_id.in_(ids)))
        s.execute(delete(SourceFile).where(SourceFile.document_id.in_(ids)))
        decision_ids = select(Decision.id).where(Decision.run_id.in_([r.id for r in runs]))
        s.execute(delete(DecisionClaim).where(DecisionClaim.decision_id.in_(decision_ids)))
        s.execute(delete(Decision).where(Decision.run_id.in_([r.id for r in runs])))
        s.execute(delete(Run).where(Run.case_id == cid))
        s.execute(delete(Document).where(Document.case_id == cid))
        s.execute(delete(CaseWorkflow).where(CaseWorkflow.case_id == cid))
        s.delete(c)
    return {"deleted": True}


def active_documents(cid):
    return select(Document).where(
        Document.case_id == cid, Document.id.not_in(select(RetiredDocument.document_id))
    )


def ensure_sources_editable(s, cid):
    expire_runs(s)
    if s.scalar(select(Run.id).where(Run.case_id == cid, Run.status.in_(["queued", "running"]))):
        raise HTTPException(
            409, "Wait for the current analysis to finish before changing its evidence."
        )


def source_used(s, document):
    return any(
        document.id in r.document_ids
        for r in s.scalars(select(Run).where(Run.case_id == document.case_id))
    )


def retire_source(s, document):
    if source_used(s, document):
        s.add(RetiredDocument(document_id=document.id))
    else:
        s.execute(delete(SourceFile).where(SourceFile.document_id == document.id))
        s.delete(document)


@app.delete("/api/documents/{did}", dependencies=[Depends(auth)])
def delete_document(did: str):
    with Session.begin() as s:
        d = s.get(Document, did)
        if not d or s.get(RetiredDocument, did):
            raise HTTPException(404, "Current document not found")
        get_case(s, d.case_id, lock=True)
        ensure_sources_editable(s, d.case_id)
        retire_source(s, d)
    return {"removed": True}


@app.patch("/api/documents/{did}", dependencies=[Depends(auth)])
def edit_document(did: str, body: DocumentEditIn):
    with Session.begin() as s:
        d = s.get(Document, did)
        if not d or s.get(RetiredDocument, did):
            raise HTTPException(404, "Current document not found")
        get_case(s, d.case_id, lock=True)
        ensure_sources_editable(s, d.case_id)
        if d.title == body.title and d.published_date == (
            body.published_date.isoformat() if body.published_date else ""
        ):
            return record(d)
        if source_used(s, d):
            old = d
            d = Document(
                **{
                    key: getattr(old, key)
                    for key in (
                        "case_id",
                        "title",
                        "source_url",
                        "published_date",
                        "kind",
                        "sha256",
                        "pages",
                    )
                }
            )
            s.add(d)
            s.flush()
            raw = s.get(SourceFile, old.id)
            if raw:
                s.add(
                    SourceFile(
                        document_id=d.id, data=raw.data, filename=raw.filename, mime=raw.mime
                    )
                )
            s.add(RetiredDocument(document_id=old.id))
        d.title = body.title
        d.published_date = body.published_date.isoformat() if body.published_date else ""
        s.flush()
        return record(d)


@app.patch("/api/cases/{cid}/workflow", dependencies=[Depends(auth)])
def update_workflow(cid: str, body: WorkflowIn):
    with Session.begin() as s:
        get_case(s, cid, lock=True)
        if not s.get(Workspace, body.workspace_id):
            raise HTTPException(422, "Select an existing workspace")
        item = s.get(CaseWorkflow, cid)
        if item is None:
            item = CaseWorkflow(case_id=cid)
            s.add(item)
        for key, value in body.model_dump().items():
            setattr(item, key, value)
        item.updated_at = now()
        s.flush()
        return workflow(s, cid)


@app.get("/api/cases", dependencies=[Depends(auth)])
def cases():
    with Session.begin() as s:
        expire_runs(s)
        items = list(s.scalars(select(Case).order_by(Case.created_at.desc()).limit(1000)))
        ids = [c.id for c in items]
        latest_runs = {}
        for r in s.scalars(select(Run).where(Run.case_id.in_(ids)).order_by(Run.created_at.desc())):
            latest_runs.setdefault(r.case_id, r)
        decisions = {}
        for d, claim_id in s.execute(
            select(Decision, DecisionClaim.claim_id)
            .outerjoin(DecisionClaim, Decision.id == DecisionClaim.decision_id)
            .where(Decision.run_id.in_([r.id for r in latest_runs.values()]))
            .order_by(Decision.created_at, Decision.id)
        ):
            decisions.setdefault(d.run_id, []).append({**record(d), "claim_id": claim_id})
        flows = {
            w.case_id: {col.name: getattr(w, col.name) for col in w.__table__.columns}
            for w in s.scalars(select(CaseWorkflow).where(CaseWorkflow.case_id.in_(ids)))
        }
        result = []
        for c in items:
            r = latest_runs.get(c.id)
            review = (
                assessment_summary(r.result["findings"], decisions.get(r.id, []))
                if r and r.status == "succeeded"
                else None
            )
            result.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "issuer": c.issuer,
                    "article_date": c.article_date,
                    "created_at": c.created_at,
                    "status": review["status"] if review else r.status if r else "draft",
                    "assessment": review,
                    "workflow": flows.get(c.id, WorkflowIn().model_dump()),
                }
            )
        return result


@app.post("/api/cases", dependencies=[Depends(auth)], status_code=201)
def create_case(body: CaseIn):
    with Session.begin() as s:
        if not s.get(Workspace, body.workspace_id):
            raise HTTPException(422, "Select an existing workspace")
        c = Case(
            **body.model_dump(exclude={"source_url", "article_date", "workspace_id", "topic"}),
            article_date=body.article_date.isoformat(),
            source_url=str(body.source_url) if body.source_url else None,
        )
        s.add(c)
        s.flush()
        s.add(CaseWorkflow(case_id=c.id, workspace_id=body.workspace_id, topic=body.topic))
        return record(c)


def decisions_for_run(s, rid):
    return [
        {**record(d), "claim_id": claim_id}
        for d, claim_id in s.execute(
            select(Decision, DecisionClaim.claim_id)
            .outerjoin(DecisionClaim, Decision.id == DecisionClaim.decision_id)
            .where(Decision.run_id == rid)
            .order_by(Decision.created_at, Decision.id)
        )
    ]


def run_record(s, run):
    decisions = decisions_for_run(s, run.id)
    return {
        **record(run),
        "decisions": decisions,
        "assessment": assessment_summary(run.result["findings"], decisions)
        if run.status == "succeeded"
        else None,
    }


def case_detail(s, cid):
    c = get_case(s, cid)
    runs = s.scalars(select(Run).where(Run.case_id == cid).order_by(Run.created_at.desc())).all()
    retired = set(s.scalars(select(RetiredDocument.document_id)))
    return {
        **record(c),
        "workflow": workflow(s, cid),
        "historical_documents": [
            {
                **record(d),
                "has_file": s.scalar(
                    select(SourceFile.document_id).where(SourceFile.document_id == d.id)
                )
                is not None,
            }
            for d in s.scalars(
                select(Document).where(Document.case_id == cid, Document.id.in_(retired))
            )
        ],
        "documents": [
            {
                **record(d),
                "has_file": s.scalar(
                    select(SourceFile.document_id).where(SourceFile.document_id == d.id)
                )
                is not None,
            }
            for d in s.scalars(active_documents(cid).order_by(Document.created_at))
        ],
        "runs": [run_record(s, r) for r in runs],
    }


@app.get("/api/cases/{cid}", dependencies=[Depends(auth)])
def detail(cid: str):
    with Session.begin() as s:
        expire_runs(s)
        return case_detail(s, cid)


def save_doc(
    cid,
    title,
    pages,
    source_url,
    published_date,
    kind,
    raw=None,
    filename="source.pdf",
    mime="application/pdf",
    replace_document_id=None,
):
    with Session.begin() as s:
        get_case(s, cid, lock=True)
        ensure_sources_editable(s, cid)
        previous = s.get(Document, replace_document_id) if replace_document_id else None
        if replace_document_id and (
            not previous or previous.case_id != cid or s.get(RetiredDocument, replace_document_id)
        ):
            raise HTTPException(404, "Current document not found in this review")
        existing = [d for d in s.scalars(active_documents(cid)) if d.id != replace_document_id]
        sha = digest(pages)
        if any(d.sha256 == sha for d in existing):
            raise HTTPException(409, "This document text is already attached to the case")
        size = sum(len(p["text"]) for d in existing for p in d.pages) + sum(
            len(p["text"]) for p in pages
        )
        if len(existing) >= 8 or size > 250000:
            raise HTTPException(422, "Limit each case to 8 documents and 250,000 total characters")
        if previous:
            retire_source(s, previous)
        d = Document(
            case_id=cid,
            title=title,
            pages=pages,
            source_url=source_url,
            published_date=published_date,
            kind=kind,
            sha256=sha,
        )
        s.add(d)
        s.flush()
        if raw is not None:
            s.add(SourceFile(document_id=d.id, data=raw, filename=filename[:200], mime=mime))
        return record(d)


@app.post("/api/cases/{cid}/documents", dependencies=[Depends(auth)], status_code=201)
def add_document(cid: str, body: DocumentIn):
    return save_doc(
        cid,
        body.title,
        [{"page": 1, "text": body.text}],
        str(body.source_url) if body.source_url else None,
        body.published_date.isoformat() if body.published_date else "",
        "text",
    )


@app.post("/api/cases/{cid}/documents/pdf", dependencies=[Depends(auth)], status_code=201)
def upload_document(
    cid: str,
    file: UploadFile = File(...),
    title: str = Form(min_length=3, max_length=300),
    published_date: date | None = Form(default=None),
    source_url: str = Form(default=""),
):
    raw = file.file.read(config.MAX_UPLOAD + 1)
    if len(raw) > config.MAX_UPLOAD:
        raise HTTPException(413, "Maximum PDF size is 4 MB")
    try:
        url = str(TypeAdapter(HttpUrl).validate_python(source_url)) if source_url.strip() else None
        pages = extract_pdf(raw)
    except (ValueError, ValidationError) as e:
        raise HTTPException(
            422,
            str(e)
            if isinstance(e, ValueError) and not isinstance(e, ValidationError)
            else "Source link must be an http or https URL",
        ) from e
    return save_doc(
        cid,
        title.strip(),
        pages,
        url,
        published_date.isoformat() if published_date else "",
        "pdf",
        raw,
        file.filename or "source.pdf",
    )


def import_link(url):
    try:
        return fetch_link(str(url))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            422,
            "Could not fetch this source. It may block automated access; download and upload it instead.",
        ) from exc


@app.post("/api/imports/url", dependencies=[Depends(auth)])
def preview_link(body: LinkIn):
    result = import_link(body.url)
    text = "\n\n".join(p["text"] for p in result["pages"])
    return {
        "title": result["title"],
        "text": text[:12000],
        "truncated": len(text) > 12000,
        "source_url": result["source_url"],
        "attachments": result["attachments"],
    }


@app.post("/api/imports/file", dependencies=[Depends(auth)])
def preview_file(file: UploadFile = File(...)):
    try:
        pages, kind, mime = parse_file(file.file.read(config.MAX_UPLOAD + 1), file.filename or "")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    text = "\n\n".join(p["text"] for p in pages)
    return {"text": text[:12000], "truncated": len(text) > 12000}


@app.post("/api/cases/{cid}/documents/url", dependencies=[Depends(auth)], status_code=201)
def import_document(cid: str, body: DocumentLinkIn):
    with Session() as s:
        get_case(s, cid)
    result = import_link(body.url)
    return save_doc(
        cid,
        body.title,
        result["pages"],
        result["source_url"],
        body.published_date.isoformat() if body.published_date else "",
        result["kind"],
        result["raw"],
        result["filename"],
        result["mime"],
        replace_document_id=body.replace_document_id,
    )


@app.post("/api/cases/{cid}/documents/file", dependencies=[Depends(auth)], status_code=201)
def upload_file(
    cid: str,
    file: UploadFile = File(...),
    title: str = Form(min_length=3, max_length=300),
    published_date: date | None = Form(default=None),
    source_url: str = Form(default=""),
    replace_document_id: str | None = Form(default=None),
):
    raw = file.file.read(config.MAX_UPLOAD + 1)
    try:
        url = str(TypeAdapter(HttpUrl).validate_python(source_url)) if source_url.strip() else None
        pages, kind, mime = parse_file(raw, file.filename or "")
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            422,
            "Check the source URL and file. "
            + (str(exc) if not isinstance(exc, ValidationError) else "Use an HTTP or HTTPS URL."),
        ) from exc
    return save_doc(
        cid,
        title.strip(),
        pages,
        url,
        published_date.isoformat() if published_date else "",
        kind,
        raw,
        file.filename or "source",
        mime,
        replace_document_id=replace_document_id,
    )


@app.get("/api/documents/{did}/file", dependencies=[Depends(auth)])
def original_file(did: str):
    with Session() as s:
        source = s.get(SourceFile, did)
        if not source:
            raise HTTPException(
                404,
                "Original file was not retained. Open the source link or attach the file in a new review.",
            )
        suffix = {"application/pdf": "pdf", "text/html": "html", "text/plain": "txt"}.get(
            source.mime, "docx"
        )
        return Response(
            source.data,
            media_type=source.mime,
            headers={"Content-Disposition": f'attachment; filename="source-{did}.{suffix}"'},
        )


@app.get("/api/documents/{did}/pages/{page}.png", dependencies=[Depends(auth)])
def page_image(did: str, page: int):
    import pymupdf

    with Session() as s:
        source = s.get(SourceFile, did)
        if not source or source.mime != "application/pdf":
            raise HTTPException(
                404, "Page images require a retained PDF. Extracted text remains available."
            )
        raw = source.data
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        if not 1 <= page <= len(pdf):
            raise HTTPException(404, "Page not found")
        p = pdf[page - 1]
        scale = min(1.7, 1200 / max(p.rect.width, p.rect.height))
        return Response(
            p.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png"),
            media_type="image/png",
        )


@app.post("/api/cases/{cid}/runs", dependencies=[Depends(auth)], status_code=201)
def queue_analysis(cid: str, body: AnalysisIn = Body(default=AnalysisIn())):
    name = body.provider or config.PROVIDER
    if config.HOSTED and name != "gemini":
        raise HTTPException(
            422, "The hosted workspace uses Gemini. Ollama is available when running locally."
        )
    import os

    model = (
        os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        if name == "gemini"
        else os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    )
    try:
        Provider(name, model).check()
    except ProviderError as e:
        raise HTTPException(503, str(e)) from e
    try:
        with Session.begin() as s:
            expire_runs(s)
            get_case(s, cid, lock=True)
            docs = list(
                s.scalars(
                    active_documents(cid)
                    .with_only_columns(Document.id)
                    .order_by(Document.created_at)
                )
            )
            if not docs:
                raise HTTPException(422, "Add at least one announcement document before analyzing")
            r = Run(
                case_id=cid,
                active_key=cid,
                document_ids=docs,
                provider=name,
                model=model,
                prompt_version=config.PROMPT_VERSION,
                lease_until=now() + timedelta(minutes=5),
            )
            s.add(r)
            s.flush()
            run_id = r.id
        execute_run(run_id)
        with Session() as s:
            return record(s.get(Run, run_id))
    except IntegrityError as e:
        raise HTTPException(409, "This case already has an analysis queued or running") from e


@app.post("/api/runs/{rid}/decisions", dependencies=[Depends(auth)], status_code=201)
def decision(rid: str, body: DecisionIn):
    with Session.begin() as s:
        r = s.get(Run, rid)
        if r is None:
            raise HTTPException(404, "Analysis not found")
        if r.status != "succeeded":
            raise HTTPException(409, "Only a completed analysis can receive a review decision")
        findings = r.result["findings"]
        claim_id = body.claim_id
        if claim_id is None and len(findings) == 1:
            claim_id = findings[0]["claim_id"]
        if not any(f["claim_id"] == claim_id for f in findings):
            raise HTTPException(
                422, "Select a claim from this analysis. Each claim needs its own assessment."
            )
        d = Decision(run_id=rid, **body.model_dump(exclude={"claim_id"}))
        s.add(d)
        s.flush()
        s.add(DecisionClaim(decision_id=d.id, claim_id=claim_id))
        return {**record(d), "claim_id": claim_id}


@app.get("/api/cases/{cid}/brief", dependencies=[Depends(auth)])
def brief(cid: str, run_id: str | None = None):
    from .briefs import make_brief

    with Session() as session:
        case = case_detail(session, cid)
    run = (
        next((r for r in case["runs"] if r["id"] == run_id), None)
        if run_id
        else (case["runs"][0] if case["runs"] else None)
    )
    if run_id and run is None:
        raise HTTPException(404, "Analysis does not belong to this review")
    return Response(
        make_brief(case, run),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="evidence-brief-{cid}.txt"'},
    )


@app.get("/api/examples", dependencies=[Depends(auth)])
def examples():
    from .examples import EXAMPLES, SOURCES

    return [{**item, "document": SOURCES[item["source"]]} for item in EXAMPLES]


@app.get("/api/examples/{source_id}/file", dependencies=[Depends(auth)])
def example_file(source_id: str):
    from .examples import SOURCES

    source = SOURCES.get(source_id)
    if not source:
        raise HTTPException(404, "Example source not found")
    return FileResponse(
        config.ROOT / "examples" / source["file"],
        media_type="application/pdf",
        filename=source["file"],
    )


@app.post("/api/examples/{example_id}", dependencies=[Depends(auth)], status_code=201)
def create_example(example_id: str):
    from .examples import EXAMPLES, SOURCES

    item = next((x for x in EXAMPLES if x["id"] == example_id), None)
    if not item:
        raise HTTPException(404, "Example not found")
    source = SOURCES[item["source"]]
    raw = (config.ROOT / "examples" / source["file"]).read_bytes()
    pages = extract_pdf(raw)
    case = create_case(
        CaseIn(
            title="Test claims · " + item["title"],
            issuer=source["issuer"],
            article=item["article"],
            article_date=source["date"],
            workspace_id="examples",
            topic="Results" if "acquisition" not in item["title"] else "Acquisition",
        )
    )
    save_doc(
        case["id"],
        source["title"],
        pages,
        source["url"],
        source["date"],
        "pdf",
        raw,
        source["file"],
    )
    return case
