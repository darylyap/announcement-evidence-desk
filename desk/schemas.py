from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CaseIn(Strict):
    title: str = Field(min_length=3, max_length=300)
    issuer: str = Field(min_length=2, max_length=200)
    article: str = Field(min_length=20, max_length=12000)
    source_url: HttpUrl | None = None
    article_date: date
    workspace_id: str = "general"
    topic: Literal["Results", "Corporate action", "Acquisition", "Governance", "Other"] = "Other"


class DocumentIn(Strict):
    title: str = Field(min_length=3, max_length=300)
    text: str = Field(min_length=80, max_length=100000)
    source_url: HttpUrl | None = None
    published_date: date | None = None


class DecisionIn(Strict):
    claim_id: str | None = Field(default=None, max_length=40)
    verdict: Literal["accept", "reject", "needs_evidence"]
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=5, max_length=2000)


class Claim(Strict):
    text: str = Field(min_length=10, max_length=500)
    article_quote: str = Field(min_length=15, max_length=700)


class Claims(Strict):
    claims: list[Claim] = Field(min_length=0, max_length=4)


class Citation(Strict):
    chunk_id: str
    quote: str = Field(min_length=15, max_length=700)


class Finding(Strict):
    claim_id: str
    verdict: Literal["supported", "contradicted", "insufficient"]
    explanation: str = Field(min_length=10, max_length=1000)
    citations: list[Citation] = Field(max_length=3)


class Findings(Strict):
    findings: list[Finding] = Field(min_length=1, max_length=4)


class WorkspaceIn(Strict):
    name: str = Field(min_length=2, max_length=80)


class WorkflowIn(Strict):
    workspace_id: str = "general"
    topic: Literal["Results", "Corporate action", "Acquisition", "Governance", "Other"] = "Other"
    owner: str = Field(default="", max_length=80)
    queue: str = Field(default="Analyst review", min_length=2, max_length=80)
    stage: Literal["open", "in_review", "follow_up", "closed", "archived"] = "open"
    next_action: str = Field(default="", max_length=2000)


class LinkIn(Strict):
    url: HttpUrl


class DocumentLinkIn(LinkIn):
    replace_document_id: str | None = None
    title: str = Field(min_length=3, max_length=300)
    published_date: date | None = None


class AnalysisIn(Strict):
    provider: Literal["ollama", "gemini"] | None = None


class DocumentEditIn(Strict):
    title: str = Field(min_length=3, max_length=300)
    published_date: date | None = None
