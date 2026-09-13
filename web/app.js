"use strict";
const $ = (s) => document.querySelector(s);
const esc = (x) =>
  String(x ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const state = {
  view: "review",
  cases: [],
  current: null,
  runId: null,
  key: sessionStorage.getItem("evidenceKey") || "",
  provider: null,
  analyzingId: null,
  workspaces: [],
  localProvider: sessionStorage.getItem("localProvider") || null,
  pageUrl: null,
  briefText: "",
};
const human = (v) =>
  ({
    reviewed: "Claims reviewed",
    partially_reviewed: "Partly assessed",
    draft: "Not analyzed",
    queued: "Queued",
    running: "Analyzing",
    succeeded: "Analysis complete",
    failed: "Needs attention",
    supported: "Supported",
    contradicted: "Contradicted",
    insufficient: "Insufficient evidence",
    accept: "Findings accepted",
    reject: "Findings rejected",
    needs_evidence: "More evidence needed",
  })[v] || v;
const date = (v) =>
  v
    ? new Date(v.endsWith("Z") ? v : v + "Z").toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
const badge = (s) => `<span class="badge ${esc(s)}">${esc(human(s))}</span>`;
function message(text = "") {
  $("#message").hidden = !text;
  $("#message").textContent = text;
}
async function api(path, options = {}) {
  const headers = { "X-Access-Key": state.key, ...options.headers };
  if (options.body && !(options.body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const r = await fetch(path, { ...options, headers });
  if (!r.ok) {
    let b = {};
    try {
      b = await r.json();
    } catch {}
    const detail = Array.isArray(b.detail)
      ? b.detail.map((e) => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join("; ")
      : b.detail;
    throw new Error(detail || `Request failed (${r.status})`);
  }
  return r;
}
async function json(path, options) {
  return (await api(path, options)).json();
}
function busy(form, yes) {
  const b = form.querySelector("[type=submit]");
  if (b) b.disabled = yes;
}
function renderCases() {
  const workspace = $("#workspaceFilter").value;
  const company = $("#companyFilter").value;
  const query = $("#caseSearch").value.toLowerCase();
  const stage = $("#stageFilter").value;
  const topic = $("#topicFilter").value;
  const cases = state.cases.filter(
    (c) =>
      (!workspace || c.workflow.workspace_id === workspace) &&
      (!company || c.issuer === company) &&
      (!topic || c.workflow.topic === topic) &&
      (!stage ||
        (stage === "active"
          ? !["closed", "archived"].includes(c.workflow.stage)
          : c.workflow.stage === stage)) &&
      `${c.issuer} ${c.title} ${c.workflow.owner} ${c.workflow.queue}`
        .toLowerCase()
        .includes(query),
  );
  $("#caseCount").textContent = cases.length;
  $("#cases").innerHTML =
    cases
      .map(
        (c) =>
          `<button class="case-link ${state.current?.id === c.id ? "selected" : ""}" data-case="${esc(c.id)}"><strong>${esc(c.title)}</strong><small>${esc(c.issuer)} · ${esc(human(c.status))}</small><small>${esc(c.workflow.queue)}${c.workflow.owner ? " · " + esc(c.workflow.owner) : ""}</small></button>`,
      )
      .join("") || '<p class="muted">No reviews match these filters.</p>';
}
async function refreshCases() {
  state.cases = await json("/api/cases");
  const selected = $("#companyFilter").value;
  $("#companyFilter").innerHTML =
    '<option value="">All companies</option>' +
    [...new Set(state.cases.map((c) => c.issuer))]
      .sort()
      .map((x) => `<option>${esc(x)}</option>`)
      .join("");
  $("#companyFilter").value = selected;
  renderCases();
}
async function openCase(id, render = true) {
  const c = await json(`/api/cases/${id}`);
  state.view = "review";
  state.current = c;
  if (!c.runs.some((r) => r.id === state.runId))
    state.runId = c.runs[0]?.id || null;
  if (render) renderCase();
  await refreshCases();
}
function citationHTML(c) {
  return `<div class="citation"><div class="citation-title"><span>${esc(c.title)}</span><span>p. ${c.page}</span></div><blockquote>“${esc(c.quote)}”</blockquote><div class="citation-footer"><button class="text-button" data-document="${esc(c.document_id)}" data-page="${c.page}">View evidence page / source</button>${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">Original filing ↗</a>` : ""} · published ${esc(c.published_date || "Unknown · timing not checked")}</div>${c.after_article ? '<div class="late">Published after the article — does not establish prior disclosure.</div>' : ""}</div>`;
}
function findingHTML(f, i, run) {
  return `<article class="claim"><div class="claim-head"><div><span class="claim-number">CLAIM ${String(i + 1).padStart(2, "0")}</span>${badge(f.verdict)}</div><h3>${esc(f.text)}</h3></div><div class="claim-body"><div class="quote-label">Claim input</div><blockquote>“${esc(f.article_quote)}”</blockquote><p class="explanation">${esc(f.explanation)}</p><div class="quote-label">Filing evidence</div>${f.citations.map(citationHTML).join("") || '<p class="muted">No verified supporting or contradicting passage cited. Inspect the supplied sources before deciding.</p>'}<div class="context-actions"><button class="text-button" data-context-claim="${esc(f.claim_id)}">Model context (${f.passages.length} excerpts)</button>${helpTip("Three is a retrieval limit, not a requirement. One clear passage can be enough; extra excerpts can clarify context or conflicts. They may come from the same PDF and are not independent confirmations. The citations above are the passages the model actually used to justify its finding.", "About model context")}</div>${claimAssessmentHTML(f, run)}</div></article>`;
}
function renderCase() {
  const c = state.current;
  if (!c || state.view !== "review") return;
  const r = c.runs.find((r) => r.id === state.runId);
  const active =
    state.analyzingId === c.id ||
    c.runs.some((r) => ["queued", "running"].includes(r.status));
  $("#heading").textContent = c.title;
  $("#headerActions").innerHTML =
    '<button class="danger secondary" id="deleteCurrent">Delete review</button><button class="secondary" id="exportButton">Review brief</button><button class="primary new-case">+ New review</button>';
  let content = "";
  if (state.analyzingId === c.id)
    content =
      '<div class="run-progress"><span class="spinner" aria-hidden="true"></span><h2>Reading and comparing…</h2><p>Extracting claims, retrieving source passages and validating quotations. Keep this page open until it finishes.</p></div>';
  else if (!r && c.documents.length)
    content = `<div class="empty-state"><h2>Ready to compare.</h2><p>${c.documents.length} source document(s) attached. Check the claims and sources, then run the model.</p><button class="primary" id="analyzeReady">Analyze these sources</button></div>`;
  else if (!r)
    content = `<div class="empty-state"><span class="eyebrow">READY WHEN YOUR SOURCES ARE</span><h2>Build the evidence set.</h2><p>Add an evidence document, then run the comparison. Each claim will be paired with the passages the model actually used.</p><button class="primary" id="emptyAddDocument">+ Add evidence</button></div>`;
  else if (["queued", "running"].includes(r.status))
    content = `<div class="run-progress"><span class="spinner" aria-hidden="true"></span><h2>${r.status === "queued" ? "Waiting for the model…" : "Reading and comparing…"}</h2><p class="muted">Extracting article claims, retrieving passages and checking citations.<br>Keep this page open until analysis finishes. Results are saved when complete.</p><p class="muted">Local models can take a few minutes. This page updates automatically.</p></div>`;
  else if (r.status === "failed")
    content = `<div class="empty-state"><h2>Analysis needs attention.</h2><p>${esc(r.error)}</p><p class="muted">No unverified findings were accepted. Your article and documents are saved.</p><button class="primary" id="retryButton">Retry analysis</button></div>`;
  else
    content = `<p class="footnote">${r.result.findings.length} selected claim${r.result.findings.length === 1 ? "" : "s"} (maximum 4) · Human review required</p>${r.result.findings.map((f, i) => findingHTML(f, i, r)).join("")}<div class="notice">A verified quote establishes where the words came from. It does not prove that the model interpreted them correctly. This review does not determine disclosure compliance.</div>`;
  const runNav = c.runs.length
    ? `<div class="run-strip"><label title="Each analysis retains its source set, model findings and human assessments. Rerun after adding evidence; older results remain inspectable.">Analysis history ⓘ<select id="runSelect">${c.runs.map((v, i) => `<option value="${esc(v.id)}" ${r?.id === v.id ? "selected" : ""}>Analysis ${c.runs.length - i} · Started ${date(v.created_at)} · ${esc(human(v.status))}</option>`).join("")}</select></label>${r ? badge(r.status) : ""}</div>`
    : "";
  $("#workspace").innerHTML =
    `<div class="review-help">${helpTip("Enter a statement, supply independent documents, then compare. The claim-origin link records who said it; it is not proof and is not automatically searched as evidence. Checking a document against itself only shows consistency. Use Help for examples and the full walkthrough.", "Review flow")}</div><div class="meta-line"><span>${esc(c.issuer)}</span><span>Claim date / as of · ${esc(c.article_date)}</span><span>${c.documents.length} source document${c.documents.length === 1 ? "" : "s"}</span></div><div class="review-grid"><section>${c.title.startsWith("Test claims ·") ? '<div class="notice">Test article: these claims are synthetic and may be deliberately false. The attached issuer PDF is a real public source.</div>' : ""}${runNav}${c.runs.length ? helpTip("Each attempt keeps its original documents, findings and assessments. Retry uses the current evidence; old results stay unchanged. Select an earlier attempt only when you need to inspect it.", "Analysis history") : ""}${r && r.id !== c.runs[0]?.id ? '<div class="notice">Viewing an earlier analysis. Its evidence set and assessment are preserved; the brief will use this selected analysis.</div>' : ""}${r && (c.documents.length !== r.document_ids.length || c.documents.some((d) => !r.document_ids.includes(d.id))) ? '<div class="notice">Evidence has changed since this analysis. These findings use the earlier documents; run again to check the current set.</div>' : ""}${content}</section><aside class="side-evidence">${workflowPanel(c)}<section class="panel"><div class="panel-top"><h3>Claims to check</h3><span class="count">01</span></div><p class="muted">${esc(c.title)}</p>${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">Claim origin ↗</a>` : ""}<details><summary>Read claim input</summary><div class="article-text">${esc(c.article)}</div></details></section><section class="panel"><div class="panel-top"><h3>Current evidence</h3><button class="text-button" id="addDocument" ${active ? "disabled" : ""}>+ Add</button></div>${c.documents.map((d) => `<div class="document"><strong>${esc(d.title)}</strong><small>${esc(d.published_date || "Date unknown")} · ${d.pages.length} ${d.kind === "pdf" ? "page(s)" : "text section(s)"} · ${d.kind.toUpperCase()}</small><br><button class="text-button" data-document="${esc(d.id)}">${d.kind === "pdf" && d.has_file ? "View PDF pages" : "Read source text"}</button><button class="text-button" data-edit-document="${esc(d.id)}" ${active ? "disabled" : ""}>Edit / replace</button><button class="text-button danger" data-remove-document="${esc(d.id)}" ${active ? "disabled" : ""}>Remove</button></div>`).join("") || '<p class="muted">No evidence attached yet. Upload a file or import an official link.</p>'}<button class="primary" id="analyzeButton" ${active || !c.documents.length ? "disabled" : ""}>${active ? "Analysis in progress…" : c.runs.length ? "Run new analysis" : "Analyze evidence"}</button>${helpTip("Run again after changing evidence. Each attempt retains its original sources and assessment.", "Rerun help")}</section>${
      r?.status === "succeeded" ? assessmentSummaryHTML(r) : ""
    }${
      r
        ? `<section class="panel"><h3>Analysis record</h3><details><summary>Documents used in this analysis</summary>${r.document_ids
            .map((id) => {
              const d = [
                ...c.documents,
                ...(c.historical_documents || []),
              ].find((d) => d.id === id);
              return d
                ? `<button class="text-button history-source" data-document="${esc(id)}">${esc(d.title)}</button>`
                : "";
            })
            .join(
              "",
            )}</details><p class="muted">${esc(r.provider)} · ${esc(r.model)}<br>Prompt ${esc(r.prompt_version)}<br>${r.document_ids.length} document${r.document_ids.length === 1 ? "" : "s"} in this run<br>${r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)} seconds · ` : ""}Started ${date(r.created_at)} (local time)</p><details><summary>Run identifier</summary><p class="muted">${esc(r.id)}</p></details></section>`
        : ""
    }</aside></div>`;
}
function showCaseForm() {
  const form = $("#caseForm");
  form.reset();
  $("#newCaseWorkspace").innerHTML = workspaceOptions(
    (state.view === "manage"
      ? state.managerWorkspace
      : $("#workspaceFilter").value) || "general",
  );
  $("#caseError").textContent = "";
  $("#articleImportStatus").textContent = "";
  form.elements.article_date.value = new Date().toISOString().slice(0, 10);
  $("#caseDialog").showModal();
}
function showDocForm(id = null) {
  $("#docForm").reset();
  $("#docError").textContent = "";
  state.editDocumentId = id;
  const d = state.current.documents.find((d) => d.id === id);
  $("#docDialog h2").textContent = d
    ? "Edit evidence document"
    : "Add evidence document";
  if (d) {
    $("#docForm").elements.title.value = d.title;
    $("#docForm").elements.published_date.value = d.published_date;
  }
  $("#documentEditHint").textContent = d
    ? "Edit the title or publication date. To replace the content, choose a new file OR enter a new link. Leave both empty to keep the existing content. Earlier analyses retain their original evidence."
    : "Upload a document OR enter its official link. Text is extracted automatically; no pasted text is needed.";
  $("#clearEvidenceFile").hidden = true;
  $("#linkTools").hidden = true;
  $("#linkAttachments").textContent = "";
  $("#docDialog").showModal();
}
async function runAnalysis() {
  if (!state.current) return;
  const cid = state.current.id;
  if (state.analyzingId === cid) return;
  state.analyzingId = cid;
  renderCase();
  try {
    message(
      "Analyzing selected claims. Keep this page open; local models can take a few minutes.",
    );
    const r = await json(`/api/cases/${cid}/runs`, {
      method: "POST",
      body: JSON.stringify({
        provider: state.provider?.hosted ? "gemini" : state.localProvider,
      }),
    });
    state.analyzingId = null;
    if (state.current?.id === cid && state.view === "review") {
      state.runId = r.id;
      await openCase(cid);
    } else await refreshCases();
    message(
      r.status === "failed"
        ? r.error
        : "Analysis complete. Review the findings below.",
    );
  } catch (e) {
    state.analyzingId = null;
    message(e.message);
    try {
      if (state.current?.id === cid && state.view === "review")
        await openCase(cid);
    } catch {}
  }
}

async function showSource(id, page = 1) {
  const d = [
    ...state.current.documents,
    ...(state.current.historical_documents || []),
  ].find((d) => d.id === id);
  if (!d) return;
  $("#sourceTitle").textContent = d.title;
  $("#sourceBody").innerHTML =
    `<p class="muted">Published ${esc(d.published_date || "Date unknown")} · ${esc(d.kind.toUpperCase())}</p>${d.source_url ? `<a href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a>` : ""}${d.kind === "pdf" && d.has_file ? `<div class="page-toolbar"><label>Actual PDF page<select id="sourcePage" data-source="${esc(id)}">${d.pages.map((p) => `<option value="${p.page}" ${p.page === Number(page) ? "selected" : ""}>Page ${p.page}</option>`).join("")}</select></label></div><div id="pagePreview" aria-live="polite">Loading page…</div>` : '<p class="muted">Extracted text view. PDF page images are available for newly attached PDFs.</p>'}<details ${d.kind !== "pdf" ? "open" : ""}><summary>Read extracted text</summary>${d.pages.map((p) => `<div class="source-heading">${d.kind === "pdf" ? "PAGE" : "TEXT SECTION"} ${p.page}</div><div class="source-page">${esc(p.text)}</div>`).join("")}</details>`;
  if (!$("#sourceDialog").open) $("#sourceDialog").showModal();
  if (d.kind === "pdf" && d.has_file) await loadPage(id, Number(page));
}
async function loadPage(id, page) {
  try {
    const response = await api(`/api/documents/${id}/pages/${page}.png`);
    if (state.pageUrl) URL.revokeObjectURL(state.pageUrl);
    state.pageUrl = URL.createObjectURL(await response.blob());
    $("#pagePreview").innerHTML =
      `<img class="pdf-page" src="${state.pageUrl}" alt="Actual attached PDF, page ${page}">`;
  } catch (e) {
    if ($("#pagePreview")) $("#pagePreview").textContent = e.message;
  }
}
async function checkProvider() {
  try {
    state.provider = await json("/api/provider");
    const p = state.provider;
    if (!state.localProvider) state.localProvider = p.provider;
    $("#providerBadge").textContent = p.hosted
      ? "Gemini"
      : state.localProvider === "gemini"
        ? "Gemini"
        : "Ollama";
    $("#modelDetails").textContent = p.hosted
      ? "Gemini powers analyses on this hosted workspace. Connection issues appear on the affected analysis."
      : "Choose the model connection for new analyses on this local app. Ollama must be running; Gemini requires a server-side API key.";
    $("#localProviderChoice").hidden = p.hosted;
    $("#localProvider").value = state.localProvider;
  } catch (e) {
    $("#providerBadge").textContent = "Access key required";
    $("#modelDetails").textContent = e.message;
  }
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.close) {
    $("#" + b.dataset.close).close();
    return;
  }
  if (b.classList.contains("new-case")) showCaseForm();
  if (["sampleButton", "examplesButton"].includes(b.id)) await showExamples();
  if (b.dataset.case) {
    state.runId = null;
    try {
      await openCase(b.dataset.case);
      message();
    } catch (err) {
      message(err.message);
    }
  }
  if (b.dataset.contextClaim) showModelContext(b.dataset.contextClaim);
  if (b.dataset.editDocument) showDocForm(b.dataset.editDocument);
  if (b.id === "clearEvidenceFile") {
    $("#docForm").elements.file.value = "";
    b.hidden = true;
    $("#docError").textContent = "";
    $("#linkTools").hidden = !$("#docForm").elements.source_url.value.trim();
  }
  if (b.dataset.document)
    await showSource(b.dataset.document, b.dataset.page || 1);
  if (["addDocument", "emptyAddDocument"].includes(b.id)) showDocForm();
  if (["analyzeButton", "retryButton", "analyzeReady"].includes(b.id)) {
    b.disabled = true;
    await runAnalysis();
    b.disabled = false;
  }
  if (b.id === "settingsButton") {
    $("#accessKey").value = state.key;
    await checkProvider();
    $("#settingsDialog").showModal();
  }
  if (b.id === "exportButton") await showBrief();
});
document.addEventListener("change", (e) => {
  if (e.target.id === "runSelect") {
    state.runId = e.target.value;
    renderCase();
  }
});
$("#caseForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  busy(form, true);
  $("#caseError").textContent = "";
  try {
    const body = Object.fromEntries(new FormData(form));
    if (!body.source_url) body.source_url = null;
    const c = await json("/api/cases", {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("#caseDialog").close();
    state.runId = null;
    await openCase(c.id);
    message();
  } catch (err) {
    $("#caseError").textContent = err.message;
  } finally {
    busy(form, false);
  }
});
$("#docForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  busy(form, true);
  $("#docError").textContent = "";
  try {
    const file = form.elements.file.files[0];
    const url = form.elements.source_url.value.trim();
    if (file && url)
      throw new Error(
        "Use one input: clear the selected file or remove the link.",
      );
    const fields = {
      title: form.elements.title.value,
      published_date: form.elements.published_date.value || null,
    };
    let path,
      body,
      method = "POST";
    if (file) {
      path = `/api/cases/${state.current.id}/documents/file`;
      body = new FormData(form);
      if (!body.get("published_date")) body.delete("published_date");
      if (state.editDocumentId)
        body.append("replace_document_id", state.editDocumentId);
    } else if (url) {
      path = `/api/cases/${state.current.id}/documents/url`;
      body = JSON.stringify({
        ...fields,
        url,
        replace_document_id: state.editDocumentId,
      });
    } else if (state.editDocumentId) {
      path = `/api/documents/${state.editDocumentId}`;
      method = "PATCH";
      body = JSON.stringify(fields);
    } else
      throw new Error(
        "Choose an evidence file or enter an official document link.",
      );
    await json(path, { method, body });
    $("#docDialog").close();
    await openCase(state.current.id);
    message("Document saved. Start a new analysis to include it.");
  } catch (err) {
    $("#docError").textContent = err.message;
  } finally {
    busy(form, false);
  }
});
$("#settingsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  state.key = $("#accessKey").value.trim();
  state.localProvider = $("#localProvider").value;
  sessionStorage.setItem("localProvider", state.localProvider);
  sessionStorage.setItem("evidenceKey", state.key);
  try {
    await refreshWorkspaces();
    await refreshCases();
    await checkProvider();
    $("#settingsDialog").close();
    message();
    if (state.cases.length) await openCase(state.cases[0].id);
  } catch (err) {
    $("#settingsError").textContent = err.message;
  }
});
async function poll() {
  try {
    if (
      state.current?.runs.some((r) => ["running", "queued"].includes(r.status))
    ) {
      const cid = state.current.id;
      const next = await json(`/api/cases/${cid}`);
      if (state.current?.id === cid) {
        const before = state.current.runs.map((r) => r.status).join();
        state.current = next;
        if (before !== next.runs.map((r) => r.status).join()) {
          renderCase();
          await refreshCases();
        }
      }
    }
  } catch (e) {
    message(e.message);
  } finally {
    setTimeout(poll, 2500);
  }
}
(async () => {
  try {
    await refreshWorkspaces();
    await refreshCases();
    if (state.cases.length) await openCase(state.cases[0].id);
    await checkProvider();
  } catch (e) {
    message(e.message);
    await checkProvider();
  }
  poll();
})();
