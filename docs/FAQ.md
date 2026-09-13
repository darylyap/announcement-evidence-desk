# Product questions

**Who is the user, and why do this analysis?** An analyst preparing an evidence review of company-related news. The tool locates passages, compares selected claims and preserves the reviewer’s rationale.

**What is the potential business impact?** Less searching and review preparation when several claims/documents need checking.

**How do I start?** Select New review and enter a factual sentence or news excerpt in Claims to check, plus the company and claim date / as-of date. A full article is unnecessary. Optional file/link import populates an editable claim preview. Then add independent evidence documents.

**Are the examples real?** The bundled DBS and SGX PDFs are real public issuer publications. Test articles are explicitly labelled and include matching, altered and invented statements. The model still runs; the expected outcome is not supplied to it.

**Which examples should I try?** Start with DBS · two claims, mixed findings to assess supported and contradicted claims separately. DBS annual profit illustrates support; the altered DBS income figure illustrates contradiction; SGX's invented acquisition claim illustrates insufficient evidence. SGX net revenue provides another company example. All original PDFs are downloadable from the example cards.

**Which files work?** PDF, DOCX, UTF-8 TXT and MD, up to 4 MB each. PDFs: at most 40 pages; text extraction: at most 100,000 characters per document. Drop/select one file at a time, up to eight per review. Scans, images and legacy DOC need conversion or manual text extraction first.

**Do I need to paste announcement text or provide a date?** Upload a file OR enter its official link; either extracts the evidence automatically. No pasted announcement text or format selection is required. Published on is optional and an unknown date cannot establish timing. Claim date / as-of date anchors the statement being checked.

**Can I see the actual document?** For retained PDFs, View evidence page / source displays the actual cited PDF page. Extracted text is separately available. Text and DOCX inputs have text views, not reconstructed page images. Page images are not AI generated or automatically highlighted.

**Can the app fetch links?** It directly fetches supported official HTTPS pages/PDFs from SGX, DBS, Singtel, OCBC and UOB. An SGX landing page can expose PDF attachments for selection.

**What do findings mean?** Supported: retrieved evidence agrees. Contradicted: it explicitly conflicts for the same entity/event/period. Insufficient: it does not settle the claim. Silence is not contradiction; a verified quotation does not guarantee a correct interpretation.

**How are workspaces and companies organised?** Workspaces group projects; filters narrow company, topic and workflow. One review holds one article/company, so different news items remain separate. All workspaces share access; they are not security-isolated tenants.

**How do I manage or delete entries?** Manage workspaces opens the main screen with workspace search, review search, rename, move and delete controls. Deleting a workspace moves its reviews to General. General and Source examples are built-in folders. Deleting a review permanently removes its files, analyses and assessments after confirmation; archive instead to preserve history. Remove excludes an attachment from the next analysis. Sources already used in history remain inspectable.

**Where does a decision go?** Each assessment stays attached to one claim in one analysis. Assess every claim separately; a mixed review can contain different judgements. Revised assessments preserve earlier reasons. A new analysis starts with pending claim assessments. Manage sets a queue, owner, workflow stage and next action for internal handoff. Queue, reviewer and team dropdowns provide standard sample choices. Names are unverified labels; no email, notification or external case assignment is sent. Copy the structured brief for an external handoff through the normal process.

**Why keep history?** It records what evidence was available, what the model concluded and what the reviewer decided. Changed evidence requires a new analysis. The selector opens earlier analyses without overwriting them; the brief uses the selected record and flags changes to the evidence set. Archive the overall review to tidy the queue; it can be restored.

**Should Settings switch models?** The local app defaults to Ollama. Settings can choose Ollama or Gemini for new analyses using server-side setup. Hosted Vercel uses Gemini; it cannot reach the developer's local Ollama. Reviewers never enter a provider API key. Model details remain in the analysis record for traceability.

**Why are there two kinds of source links?** The claim-origin link records where a statement came from. It does not automatically become evidence. The official evidence link fetches a document against which that statement is compared. Supplying the same document on both sides checks consistency with that document, not independent truth.

**Where is verification performed?** The app selects up to four claims from Claims to check, searches the current attached documents, and retrieves up to three relevant passages per claim. The LLM compares each claim with those passages. Code checks the cited source IDs and exact quotations against stored text. The reviewer checks the interpretation, entity, reporting period and figures. No automatic external search is performed.

**Can I edit an announcement and retry?** Edit / replace changes its title/date or accepts a new file/link. Leave both replacement inputs empty to keep its content. Failed replacements keep existing evidence. A retry uses the current set; earlier attempts retain the old sources. Input changes are blocked while an analysis is running. Use Documents used in this analysis to inspect the exact previous set.

**If a claim has an origin, why compare it?** Origin is attribution: it shows where a statement was made. Comparison is useful when checking a news report or draft summary against an underlying filing, because figures, periods or qualifications can be misreported. If the input is already the official filing and no other source is being checked, the comparison may add little value. This is a document comparison tool, not independent proof of truth.

**Why several retrieved passages?** Three is a retrieval ceiling, not a requirement. Each claim gets up to three relevant candidate excerpts, possibly from the same PDF. One clear passage can be enough; additional passages can clarify context or conflicting details. These give the model relevant context; they are not three independent confirmations. The main finding shows its actual citations. Model context opens the additional excerpts only when needed.

**What does Agree mean?** Agree with AI finding accepts the displayed supported, contradicted or insufficient finding for that claim. It does not always mean the claim is true. Each claim has its own reviewer, reason and assessment history. The overview counts completed assessments; a claim marked Need more evidence remains flagged for follow-up.
