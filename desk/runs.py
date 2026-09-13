import logging
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import update

from .analysis import GroundingError, analyze
from .db import Case, Document, Run, Session, now
from .provider import Provider, ProviderError

log = logging.getLogger(__name__)


def expire_runs(session):
    session.execute(
        update(Run)
        .where(Run.status.in_(["queued", "running"]), Run.lease_until < now())
        .values(
            status="failed",
            active_key=None,
            owner=None,
            finished_at=now(),
            error="Analysis was interrupted. Start a new analysis to retry.",
        )
    )


def execute_run(run_id, provider=None):
    owner = str(uuid4())
    with Session.begin() as session:
        claimed = session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(
                status="running",
                started_at=now(),
                owner=owner,
                lease_until=now() + timedelta(minutes=5),
            )
        )
        if claimed.rowcount != 1:
            return
    started = time.monotonic()
    try:
        with Session() as session:
            run = session.get(Run, run_id)
            case = session.get(Case, run.case_id)
            inputs = {key: getattr(case, key) for key in ("issuer", "article", "article_date")}
            documents = [session.get(Document, doc_id) for doc_id in run.document_ids]
            sources = [
                {
                    key: getattr(doc, key)
                    for key in ("id", "title", "pages", "source_url", "published_date", "sha256")
                }
                for doc in documents
            ]
            model = provider or Provider(run.provider, run.model)
        result = analyze(inputs, sources, model)
        status, error = "succeeded", None
    except (GroundingError, ProviderError) as exc:
        status, result, error = "failed", None, str(exc)
    except Exception:
        log.error("Analysis %s failed internally", run_id)
        status, result, error = (
            "failed",
            None,
            "Analysis failed internally. Your sources are saved; retry.",
        )
    with Session.begin() as session:
        session.execute(
            update(Run)
            .where(Run.id == run_id, Run.owner == owner, Run.status == "running")
            .values(
                status=status,
                result=result,
                error=error,
                active_key=None,
                owner=None,
                finished_at=now(),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        )
