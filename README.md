# Announcement Evidence Desk

[Open the application](https://announcement-evidence-desk.vercel.app) · [Source code](https://github.com/darylyap/announcement-evidence-desk)

**Check company-related claims against issuer documents and record the evidence behind each judgement.**

## The problem

News reports and draft summaries can misstate figures, reporting periods or qualifications. Reviewing them requires locating the source evidence and documenting a decision.

## How it works

1. **Provide claims and documents** — upload filings or import official links.
2. **Inspect AI findings** — supported, contradicted or insufficient evidence, with quotations and PDF page references.
3. **Assess each claim** — record your judgement and copy a structured review brief.

## Example

A summary claims annual income of **$28.9bn**, but the filing reports **$22.9bn**. The app highlights the conflict for human review.

Findings concern the supplied evidence; the reviewer makes the final judgement.

## Try it

1. Open the application and enter the supplied **workspace key** in **Settings**, without quotation marks. Reviewers do not need Gemini credentials or a local installation.
2. Open the prepared **DBS · two claims, mixed findings** review. Its evidence is the real DBS FY2025 results PDF; its claim input is labelled test text.
3. Select **Analyze evidence**. The expected findings are supported for SGD 11.0bn net profit and contradicted for the deliberately altered SGD 28.9bn total income (the filing reports SGD 22.9bn). Every new analysis calls the model; outcomes are not precomputed.
4. Read each finding and open its cited PDF page. Under each claim, choose **Agree with AI finding**, **Disagree with AI finding**, or **Need more evidence**, then select a reviewer and give a reason. Agreeing with a contradicted finding means accepting that the evidence conflicts with the claim.
5. Use **Manage** to record the queue, owner and next action. **Review brief** copies or saves a structured handoff containing each claim's assessment.

The initial shared workspace contains one unanalysed example. Other examples remain available through **Real-source examples**; opening one creates a review. Reviewers share saved data, so the initial state changes as they use it.

## Your own review

Create a review with a company, title, claim date/as-of date and a factual statement or short excerpt in **Claims to check**. Importing text from a file or an official link is optional. The optional origin link records who made the claim; it is not automatically fetched as evidence.

Add evidence by dragging/selecting a file **or** entering an official document URL. Format detection and text extraction are automatic; uploading a document does not require pasting its text again. A direct link does not require another attachment. **Find linked PDFs** is optional for announcement cover pages. Publication date is optional; an unknown date does not establish timing.

Supported uploads: PDF, DOCX, TXT and MD. Official web-page imports also extract HTML text. Files are limited to 4 MB and 100,000 extracted characters; PDFs to 40 pages. Each review supports eight documents and 250,000 extracted characters. Claim input is limited to 12,000 characters. Scanned PDFs need OCR outside this app; legacy DOC is unsupported.

**Manage workspaces** opens a full-page list with search, rename, review moves and deletion. General and Source examples are built-in folders. Deleting a custom workspace moves its reviews to General. Deleting a review removes its files and history; archive it if you want to restore it later.

Evidence can be edited, replaced or removed before rerunning. Earlier analyses retain their original documents, findings and assessments. A new analysis starts with pending assessments. Saving one claim preserves unfinished input in another while the page stays open; unsaved input is not durable storage. Filters organise reviews by company, topic and workflow.

## Run locally

Requirements: Python 3.12 and Ollama with the selected model installed. Node.js is needed only for JavaScript tests and the Vercel CLI.

```bash
git clone https://github.com/darylyap/announcement-evidence-desk.git
cd announcement-evidence-desk
./setup.sh
ollama pull gemma4:e4b
./run.sh
```

Start Ollama before analysing. Open http://127.0.0.1:8012; use `./run.sh --port 8013` if the port is occupied. Setup copies `.env.example` to `.env` only when absent. The local default is Ollama; SQLite stores data in `data/evidence.db`. `REQUIRE_ACCESS_KEY=1` enables local workspace-key protection.

To enable Gemini locally, add `GEMINI_API_KEY` to `.env`, restart the server and select **Gemini** in Settings. Set `LLM_PROVIDER=gemini` if you also want it as the server default. `GEMINI_MODEL` selects the model; `OLLAMA_MODEL` selects the local model. Keys belong on the server, never in the frontend. Simple key values do not require quotes in `.env`; do not include quotes when entering the workspace key in Settings.

Vercel runs the same application with **Gemini and PostgreSQL**. It cannot access Ollama running on your Mac. See [deployment and provider setup](docs/DEPLOYMENT.md).

## Architecture

Browser → FastAPI → claim extraction → BM25 retrieval → model comparison → citation validation → stored analysis → per-claim human assessment.

| Component | Responsibility |
|---|---|
| HTML/CSS/JavaScript | Inputs, workspace management, source viewing, assessment forms, tooltips and copyable brief |
| FastAPI | REST endpoints, authentication, bounded imports, analysis execution and persistence |
| Ollama / Gemini | Extract up to four claims and compare each with supplied passages using structured output |
| BM25 + validation | Retrieve up to three candidate excerpts per claim; reject unknown citations, altered quotations and incomplete output |
| SQLAlchemy | SQLite locally; PostgreSQL on Vercel; retain documents, original bytes, runs and assessment revisions |
| PyMuPDF / document parsers | Render retained PDF pages and extract supported file text |

Analysis runs within the HTTP request. Vercel is configured for a 300-second maximum function duration. There is no detached background worker or simulated-success fallback. Failed/interrupted attempts remain visible and can be retried. Docker is unnecessary for this setup.

## Key decisions and limits

- Three excerpts is a retrieval cap, not a requirement for three proofs. One clear passage can be enough. Excerpts may come from the same PDF; they are not independent confirmations. Main findings show actual citations; Model context exposes candidate passages.
- Exact quotation validation establishes provenance, not correct interpretation. BM25 can miss paraphrases and table relationships. Insufficient evidence does not prove a claim false. The app selects at most four claims and does not promise exhaustive document review.
- Origin is attribution. Comparing a news report or draft summary with an underlying filing can reveal errors; checking a document against itself adds little independent assurance.
- All workspaces share one access key. Reviewer and owner names are labels, not authenticated identities or role permissions. Queues record internal handoff; no external assignment or notification is sent.
- Official-link imports use HTTPS, an allowlist and address/redirect checks. Supported issuer domains cover SGX, DBS, Singtel, OCBC and UOB. Exa, general web search, paywall access and continuous monitoring are not included.
- Original PDF pages are shown without automatic quote highlighting. DOCX uses an extracted-text view. Use public, non-sensitive documents; hosted analysis sends claim text and selected evidence to Gemini.
- Value is a hypothesis: less time locating evidence and preparing handoffs. Measure full review time, corrections, missed claims and model cost with analysts before claiming ROI.

## Verify and operate

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
node --test tests/forms.test.cjs
.venv/bin/python scripts/check_app.py --provider ollama
# One live example, or omit --example to check all five:
.venv/bin/python scripts/check_examples.py --example dbs-two-claims --provider ollama
```

Live checks call the real provider and remove newly created test reviews unless `--keep` is specified. `check_examples.py --reuse` retains reused records. Browser Settings does not change a script's provider: use `--provider` or the server default. These illustrative examples are not an accuracy benchmark.

Tests cover source provenance, authentication, limits/imports, retained PDF pages, workspace operations, per-claim progress/revisions, history isolation, deletion and draft preservation. [Deployment](docs/DEPLOYMENT.md) includes hosted verification and an explicit backup-before-reset command.

With more time: analyst-controlled claim selection, table-aware retrieval, individual identity and permissions, representative evaluation, and controlled external routing.

[Product FAQ](docs/FAQ.md) · [AI-assisted development](docs/AI_TOOLS.md) · [Source provenance](examples/README.md)
