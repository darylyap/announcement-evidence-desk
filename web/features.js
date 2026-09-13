const stageLabel = (value) =>
  value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
function choiceOptions(choices, selected) {
  return [...new Set([...choices, ...(selected ? [selected] : [])])]
    .map(
      (x) =>
        `<option value="${esc(x)}" ${x === selected ? "selected" : ""}>${esc(x)}</option>`,
    )
    .join("");
}
function reviewerOptions(selected = "", allowUnassigned = true) {
  const labels = {
    "Analyst A": "Analyst A — first reviewer",
    "Analyst B": "Analyst B — second reviewer",
    "Review lead": "Review lead — coordinator",
    "Research team": "Research team",
    "Compliance team": "Compliance team",
  };
  const names = [
    ...new Set([...Object.keys(labels), ...(selected ? [selected] : [])]),
  ];
  return (
    `<option value="">${allowUnassigned ? "Unassigned" : "Choose a reviewer"}</option>` +
    names
      .map(
        (x) =>
          `<option value="${esc(x)}" ${x === selected ? "selected" : ""}>${esc(labels[x] || x)}</option>`,
      )
      .join("")
  );
}
function workspaceOptions(selected) {
  return state.workspaces
    .map(
      (w) =>
        `<option value="${esc(w.id)}" ${w.id === selected ? "selected" : ""}>${esc(w.name)}</option>`,
    )
    .join("");
}
async function refreshWorkspaces() {
  state.workspaces = await json("/api/workspaces");
  const selected = $("#workspaceFilter").value;
  $("#workspaceFilter").innerHTML =
    '<option value="">All workspaces</option>' + workspaceOptions(selected);
}
function feature(title, html) {
  $("#featureTitle").textContent = title;
  $("#featureBody").innerHTML = html;
  if (!$("#featureDialog").open) $("#featureDialog").showModal();
}
function workflowPanel(c) {
  const w = c.workflow;
  const workspace =
    state.workspaces.find((x) => x.id === w.workspace_id)?.name || "General";
  return `<section class="panel"><div class="panel-top"><h3>Review queue</h3><button class="text-button" id="editWorkflow" title="Move this review, set an owner, record a next action, or archive it.">Manage</button></div><dl class="meta-list"><dt>Workspace</dt><dd>${esc(workspace)}</dd><dt>Topic</dt><dd>${esc(w.topic)}</dd><dt>Stage</dt><dd>${esc(stageLabel(w.stage))}</dd><dt>Queue</dt><dd>${esc(w.queue)}</dd><dt>Owner</dt><dd>${esc(w.owner || "Unassigned")}</dd></dl>${w.next_action ? `<p><strong>Next action</strong><br>${esc(w.next_action)}</p>` : ""}</section>`;
}
function editWorkflow() {
  const w = state.current.workflow;
  feature(
    "Manage review",
    `<form id="workflowForm"><label>Workspace<select name="workspace_id">${workspaceOptions(w.workspace_id)}</select></label><div class="form-row"><label>Topic<select name="topic">${["Results", "Corporate action", "Acquisition", "Governance", "Other"].map((x) => `<option ${x === w.topic ? "selected" : ""}>${x}</option>`).join("")}</select></label><label>Workflow stage<select name="stage">${["open", "in_review", "follow_up", "closed", "archived"].map((x) => `<option value="${x}" ${x === w.stage ? "selected" : ""}>${stageLabel(x)}</option>`).join("")}</select></label></div><label>Queue<select name="queue">${choiceOptions(["Analyst review", "Second review", "Issuer follow-up"], w.queue)}</select></label><label>Owner / team<select name="owner">${reviewerOptions(w.owner)}</select></label><label>Next action<textarea name="next_action" maxlength="2000" rows="3">${esc(w.next_action)}</textarea></label><p class="muted">This updates the internal review queue. Reviewer and team choices are sample labels, not user accounts; no email is sent. Archive hides a case from active reviews and can be reversed using the Archived filter.</p><p class="form-error" id="featureError" role="alert"></p><button class="primary" type="submit">Save routing and workflow</button></form>`,
  );
}
function manageWorkspaces() {
  state.view = "manage";
  state.managerWorkspace = state.managerWorkspace || "";
  $("#heading").textContent = "Manage workspaces";
  $("#headerActions").innerHTML =
    '<button class="primary new-case">+ New review</button>';
  $("#workspace").innerHTML =
    `<p class="muted">Organise reviews, move them between workspaces, or delete entries. All workspaces share the same access key.</p><div class="manager-layout"><section class="panel"><h2>Workspaces</h2><label>Find a workspace<input id="workspaceSearch" type="search" placeholder="Search by name"></label><div id="workspaceCards"></div><form id="workspaceCreate"><label>New workspace<input name="name" required minlength="2" maxlength="80" placeholder="e.g. Banks — results"></label><button class="primary" type="submit">Create workspace</button></form></section><section class="panel"><div id="managerTitle"></div><label>Find a review<input id="reviewSearch" type="search" placeholder="Search title, company, owner or queue"></label><p class="muted" id="managerCount"></p><div class="table-scroll"><table class="review-table"><thead><tr><th>Review / company</th><th>Stage / queue</th><th>Workspace</th><th>Actions</th></tr></thead><tbody id="managerReviews"></tbody></table></div></section></div><p class="form-error" id="featureError" role="alert"></p>`;
  renderWorkspaceCards();
  renderManagerReviews();
}
function renderWorkspaceCards() {
  const query = $("#workspaceSearch").value.toLowerCase();
  const options = [
    { id: "", name: "All workspaces" },
    ...state.workspaces,
  ].filter((w) => w.name.toLowerCase().includes(query));
  $("#workspaceCards").innerHTML =
    options
      .map(
        (w) =>
          `<button class="workspace-card ${state.managerWorkspace === w.id ? "selected" : ""}" data-manage-workspace="${esc(w.id)}"><strong>${esc(w.name)}</strong><span>${state.cases.filter((c) => !w.id || c.workflow.workspace_id === w.id).length} reviews</span></button>`,
      )
      .join("") || '<p class="muted">No matching workspaces.</p>';
}
function renderManagerReviews() {
  const wid = state.managerWorkspace;
  const w = state.workspaces.find((w) => w.id === wid);
  $("#managerTitle").innerHTML =
    `<div class="panel-top"><h2>${esc(w?.name || "All reviews")}</h2>${w ? `<div class="button-row"><button class="secondary" data-rename-workspace="${esc(wid)}">Rename</button>${!["general", "examples"].includes(wid) ? `<button class="secondary danger" data-delete-workspace="${esc(wid)}">Delete workspace</button>` : ""}</div>` : ""}</div>`;
  const query = $("#reviewSearch").value.toLowerCase();
  const cases = state.cases.filter(
    (c) =>
      (!wid || c.workflow.workspace_id === wid) &&
      `${c.title} ${c.issuer} ${c.workflow.owner} ${c.workflow.queue}`
        .toLowerCase()
        .includes(query),
  );
  $("#managerCount").textContent =
    `${cases.length} reviews · includes closed and archived reviews`;
  $("#managerReviews").innerHTML =
    cases
      .map(
        (c) =>
          `<tr><td><button class="text-button review-title" data-case="${esc(c.id)}">${esc(c.title)}</button><small>${esc(c.issuer)} · ${esc(c.article_date)}</small></td><td>${esc(stageLabel(c.workflow.stage))}<small>${esc(c.workflow.queue)} · ${esc(c.workflow.owner || "Unassigned")}</small></td><td><select aria-label="Workspace for ${esc(c.title)}" data-move-case="${esc(c.id)}">${workspaceOptions(c.workflow.workspace_id)}</select></td><td><button class="secondary danger" data-delete-case="${esc(c.id)}">Delete</button></td></tr>`,
      )
      .join("") ||
    '<tr><td colspan="4" class="muted">No reviews here. Create a review or choose another workspace.</td></tr>';
}
function confirmDeletion(kind, id) {
  let title, description;
  if (kind === "case") {
    title = state.cases.find((c) => c.id === id)?.title || state.current?.title;
    description =
      "Permanently deletes this review, its attached files, analyses and assessments. This cannot be undone. Other reviews are unaffected.";
  } else if (kind === "workspace") {
    title = state.workspaces.find((w) => w.id === id)?.name;
    description =
      "Deletes this workspace. Its reviews will move to General with their files and analysis history intact.";
  } else {
    title = state.current.documents.find((d) => d.id === id)?.title;
    description =
      "Removes this document from the next analysis. If an earlier analysis used it, its original file and citations remain available in that analysis history.";
  }
  feature(
    "Confirm deletion",
    `<h3>${esc(title)}</h3><p>${description}</p><form id="deleteEntry"><input type="hidden" name="kind" value="${kind}"><input type="hidden" name="id" value="${esc(id)}"><p class="form-error" id="deleteError" role="alert"></p><div class="button-row"><button type="button" class="secondary" data-close="featureDialog">Cancel</button><button type="submit" class="primary destructive">${kind === "document" ? "Remove attachment" : "Delete " + kind.replace("case", "review")}</button></div></form>`,
  );
}
async function showExamples() {
  try {
    const examples = await json("/api/examples");
    feature(
      "Real sources · test claims",
      `<p>The PDFs below are real, bundled issuer publications. The article claims are labelled test inputs, including deliberately false or unsubstantiated statements. Expected outcomes are teaching notes; every analysis uses the model.</p><div class="example-grid">${examples.map((x) => `<section class="panel"><span class="eyebrow">${esc(x.expected)}</span><h3>${esc(x.title)}</h3><p>${esc(x.article)}</p><p class="muted">${esc(x.explanation)}</p><p class="muted">${esc(x.document.title)} · ${esc(x.document.date)}</p><div class="button-row"><button class="primary" data-example="${esc(x.id)}">Create this review</button><button class="secondary" data-example-file="${esc(x.source)}">Download PDF</button><a href="${esc(x.document.url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a></div></section>`).join("")}</div><p class="muted">Created reviews go into Source examples. Attachments are included in the deployment; an external download is not needed to start.</p>`,
    );
  } catch (e) {
    message(e.message);
  }
}
function showHelp() {
  feature(
    "Help · how a review works",
    `<div class="help-content">
    <p><strong>1. Enter a claim.</strong> New review accepts a factual sentence or short news excerpt in Claims to check. A full article is not required. You can import text from a claim file or official link, then edit the excerpt. The claim-origin link records where the statement came from; it is not automatically evidence.</p>
    <p><strong>2. Supply independent evidence.</strong> Add evidence document accepts a file OR an official link. File format is detected automatically. A fetched link supplies the document content, so uploading the same document again is unnecessary. If a link is a cover page with attachments, select the actual PDF. Confirm the entity and reporting period match the claim.</p>
    <p><strong>3. Analyze.</strong> The model selects up to four factual claims. The app searches only your current evidence documents and retrieves up to three relevant passages for each claim. The model compares the claim with these passages. The app checks cited IDs and exact quote text against stored sources; this does not prove the interpretation is correct.</p>
    <p><strong>4. Inspect and assess.</strong> Supported means evidence agrees; contradicted means it explicitly conflicts; insufficient means these sources do not settle the claim. Open the cited PDF page, then assess each claim separately: agree with its AI finding, disagree, or request more evidence. Add a reviewer and reason for that claim. Agreeing with a contradicted finding means the evidence conflicts with the claim. Assessments stay attached to that claim in the selected analysis.</p>
    <p><strong>Examples using real documents and test claims</strong></p>
    <ul><li>“DBS net profit was SGD 11.0 billion in 2025” against its FY2025 results: expected support.</li><li>“DBS total income was SGD 28.9 billion in 2025” against the same release reporting SGD 22.9 billion: expected contradiction.</li><li>“SGX acquired Example Analytics for S$500 million” against SGX's FY2025 results: expected insufficient evidence. This acquisition claim is invented; the document's silence does not establish it is false.</li></ul>
    <p>Use Real-source examples to load these inputs and the bundled PDFs. Every analysis runs the selected model. Expected outcomes are teaching examples, not guaranteed outputs or an accuracy benchmark.</p>
    <h3>Editing, removing and retrying</h3><p>Use Edit / replace beside a document to correct its title/date or supply a replacement file or link. Remove excludes it from the next comparison. Previous analyses keep the evidence they used. Retry or Run new analysis uses the current set. Failed uploads leave existing evidence unchanged. Sources cannot change while an analysis is running.</p>
    <h3>Why keep analysis history?</h3><p>It separates previous findings from new evidence and keeps assessments attached to the result the reviewer actually saw. For example, an initial attempt may lack evidence; adding a relevant filing and running again may resolve the claim. History is optional to browse, not an extra work step.</p>
    <h3>Which dates and reviewer names?</h3><p>Claim date / as-of date anchors the statement being checked. Published on is the evidence publication date; it may be unknown. </p>
    <h3>Input limits and model connection</h3><p>Claim input: 20–12,000 characters, up to four selected claims. Evidence: up to eight documents and 250,000 extracted characters per review; each file is at most 4 MB and 100,000 extracted characters, and PDFs at most 40 pages. Supported formats: PDF, DOCX, TXT and MD. Scans need OCR first. Local Settings switches Ollama or Gemini. Vercel uses Gemini and cannot reach laptop Ollama. Exa and automatic web search are not included.</p>
    <h3>Workspaces and handoff</h3><p>Manage workspaces opens a searchable main view for moving, renaming or deleting entries. Workspaces share one access key. Manage review sets the queue, owner and next action. Copy Review brief for an external handoff; the app does not send it. Archive preserves a review; Delete review permanently removes its history and files after confirmation.</p>
    <p class="muted">Findings compare selected claims with the documents you supply. Inspect the source evidence and record your assessment for each claim.</p>
    </div>`,
  );
}
async function showBrief() {
  try {
    const selected = state.runId
      ? `?run_id=${encodeURIComponent(state.runId)}`
      : "";
    state.briefText = await (
      await api(`/api/cases/${state.current.id}/brief${selected}`)
    ).text();
    const lines = state.briefText.split("\n");
    const body = lines
      .slice(4)
      .map((line) =>
        /^\d\. /.test(line)
          ? `<h3>${esc(line)}</h3>`
          : /^Claim \d/.test(line)
            ? `<h4>${esc(line)}</h4>`
            : line
              ? `<p>${esc(line)}</p>`
              : "",
      )
      .join("");
    feature(
      "Review brief",
      `<div class="brief-toolbar"><button class="primary" id="copyBrief" title="Copy the structured review brief" aria-label="Copy review brief"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg> Copy</button><button class="secondary" id="downloadBrief">Save text file</button><span id="copyStatus" role="status"></span></div><article class="brief-content"><h2>${esc(lines[1])}</h2>${body}</article>`,
    );
  } catch (e) {
    message(e.message);
  }
}
async function download(path, filename) {
  const response = await api(path);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
async function importArticle(file) {
  const status = $("#articleImportStatus");
  status.textContent = "Reading file…";
  try {
    if (file.size > 4 * 1024 * 1024)
      throw new Error("Maximum file size is 4 MB.");
    const form = new FormData();
    form.append("file", file);
    const data = await json("/api/imports/file", {
      method: "POST",
      body: form,
    });
    $("#caseForm").elements.article.value = data.text;
    status.textContent = data.truncated
      ? "Imported the first 12,000 characters. Select the relevant excerpt before saving."
      : "Text imported. Check the company, content and publication date before saving.";
  } catch (e) {
    status.textContent = e.message;
  }
}
function bindDrop(zoneId, input, onFile) {
  const zone = $(zoneId);
  for (const name of ["dragenter", "dragover"])
    zone.addEventListener(name, (e) => {
      e.preventDefault();
      zone.classList.add("drag-over");
    });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length !== 1) {
      message("Add one file at a time so its title and date can be checked.");
      return;
    }
    const transfer = new DataTransfer();
    transfer.items.add(e.dataTransfer.files[0]);
    input.files = transfer.files;
    onFile(input.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files[0]) onFile(input.files[0]);
  });
}
document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "workspaceFilter",
    "companyFilter",
    "topicFilter",
    "stageFilter",
  ])
    $("#" + id).addEventListener("change", renderCases);
  $("#caseSearch").addEventListener("input", renderCases);
  bindDrop("#articleDrop", $("#articleFile"), importArticle);
  bindDrop("#pdfInput", $("#docForm").elements.file, (file) => {
    $("#clearEvidenceFile").hidden = false;
    $("#linkTools").hidden = true;
    const field = $("#docForm").elements.title;
    if (!field.value) field.value = file.name.replace(/\.[^.]+$/, "");
    $("#docError").textContent =
      file.size > 4 * 1024 * 1024
        ? "Maximum file size is 4 MB."
        : `Selected: ${file.name}`;
  });
});
document.addEventListener("change", (e) => {
  if (e.target.id === "sourcePage")
    loadPage(e.target.dataset.source, Number(e.target.value));
});
document.addEventListener("submit", async (e) => {
  const f = e.target;
  const formId = f.getAttribute("id");
  if (
    ![
      "workflowForm",
      "workspaceCreate",
      "workspaceRename",
      "deleteEntry",
    ].includes(formId)
  )
    return;
  e.preventDefault();
  busy(f, true);
  try {
    const body = Object.fromEntries(new FormData(f));
    if (formId === "deleteEntry") {
      const paths = {
        case: "cases",
        workspace: "workspaces",
        document: "documents",
      };
      await json(`/api/${paths[body.kind]}/${body.id}`, { method: "DELETE" });
      $("#featureDialog").close();
      if (body.kind === "document") await openCase(state.current.id);
      else {
        if (body.kind === "case" && state.current?.id === body.id)
          state.current = null;
        if (body.kind === "workspace") state.managerWorkspace = "general";
        await refreshWorkspaces();
        await refreshCases();
        manageWorkspaces();
      }
      message(
        body.kind === "workspace"
          ? "Workspace deleted. Its reviews are in General."
          : body.kind === "document"
            ? "Evidence removed from the current set. Run again to update findings."
            : "Entry deleted.",
      );
    } else if (formId === "workflowForm") {
      await json(`/api/cases/${state.current.id}/workflow`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      $("#featureDialog").close();
      await openCase(state.current.id);
      message("Review queue updated. No notification was sent.");
    } else {
      const path =
        formId === "workspaceCreate"
          ? "/api/workspaces"
          : `/api/workspaces/${body.id}`;
      await json(path, {
        method: formId === "workspaceCreate" ? "POST" : "PATCH",
        body: JSON.stringify({ name: body.name }),
      });
      $("#featureDialog").close();
      await refreshWorkspaces();
      manageWorkspaces();
    }
  } catch (e) {
    (formId === "deleteEntry"
      ? $("#deleteError")
      : f.querySelector("#featureError") || $("#featureError")
    ).textContent = e.message;
  } finally {
    busy(f, false);
  }
});
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.id === "toggleNavigation") {
      const expanded = $(".sidebar").classList.toggle("expanded");
      b.setAttribute("aria-expanded", String(expanded));
      b.textContent = expanded
        ? "Hide reviews and filters"
        : "Show reviews and filters";
    }
    if (b.id === "deleteCurrent") confirmDeletion("case", state.current.id);
    if (b.dataset.deleteCase) confirmDeletion("case", b.dataset.deleteCase);
    if (b.dataset.deleteWorkspace)
      confirmDeletion("workspace", b.dataset.deleteWorkspace);
    if (b.dataset.removeDocument)
      confirmDeletion("document", b.dataset.removeDocument);
    if (b.hasAttribute("data-manage-workspace")) {
      state.managerWorkspace = b.dataset.manageWorkspace;
      renderWorkspaceCards();
      renderManagerReviews();
    }
    if (b.dataset.renameWorkspace) {
      const w = state.workspaces.find(
        (w) => w.id === b.dataset.renameWorkspace,
      );
      feature(
        "Rename workspace",
        `<form id="workspaceRename"><input type="hidden" name="id" value="${esc(w.id)}"><label>Workspace name<input name="name" value="${esc(w.name)}" required minlength="2" maxlength="80"></label><p class="form-error" id="featureError" role="alert"></p><button class="primary" type="submit">Save name</button></form>`,
      );
    }
    if (b.id === "helpButton") showHelp();
    if (b.id === "flowExamples") await showExamples();
    if (b.id === "manageWorkspaces") manageWorkspaces();
    if (b.id === "editWorkflow") editWorkflow();
    if (b.dataset.example) {
      b.disabled = true;
      const c = await json(`/api/examples/${b.dataset.example}`, {
        method: "POST",
      });
      $("#featureDialog").close();
      state.runId = null;
      $("#workspaceFilter").value = "examples";
      $("#companyFilter").value = "";
      $("#topicFilter").value = "";
      $("#stageFilter").value = "active";
      $("#caseSearch").value = "";
      await openCase(c.id);
      message(
        "Real PDF attached. The article is a labelled test input. Select Analyze evidence to run the model.",
      );
    }
    if (b.dataset.exampleFile)
      await download(
        `/api/examples/${b.dataset.exampleFile}/file`,
        `${b.dataset.exampleFile}-results.pdf`,
      );
    if (b.id === "copyBrief") {
      await navigator.clipboard.writeText(state.briefText);
      $("#copyStatus").textContent = "Copied to clipboard";
    }
    if (b.id === "downloadBrief") {
      const blob = new Blob([state.briefText], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "review-brief.txt";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    }
    if (b.id === "fetchArticle") {
      b.disabled = true;
      $("#articleImportStatus").textContent = "Fetching official source…";
      const data = await json("/api/imports/url", {
        method: "POST",
        body: JSON.stringify({ url: $("#caseForm").elements.source_url.value }),
      });
      $("#caseForm").elements.article.value = data.text;
      if (!$("#caseForm").elements.title.value)
        $("#caseForm").elements.title.value = data.title;
      $("#caseForm").elements.source_url.value = data.source_url;
      $("#articleImportStatus").textContent =
        (data.truncated ? "First 12,000 characters imported. " : "") +
        "Review the text and publication date before saving.";
    }
    if (b.id === "inspectLink") {
      b.disabled = true;
      const data = await json("/api/imports/url", {
        method: "POST",
        body: JSON.stringify({ url: $("#docForm").elements.source_url.value }),
      });
      $("#linkAttachments").innerHTML =
        data.attachments
          .map(
            (x) =>
              `<button type="button" class="attachment-link" data-import-url="${esc(x.url)}">${esc(x.title)}</button>`,
          )
          .join("") ||
        "<p>No linked PDFs were found. Use a direct document link or upload the file.</p>";
    }
    if (b.dataset.importUrl) {
      $("#docForm").elements.source_url.value = b.dataset.importUrl;
      $("#linkAttachments").textContent =
        "Document link selected. Check the title and date, then save.";
    }
  } catch (err) {
    if (b.id === "copyBrief")
      $("#copyStatus").textContent =
        "Clipboard unavailable. Use Save text file or select the brief text.";
    else if (b.id === "fetchArticle")
      $("#articleImportStatus").textContent = err.message;
    else if (b.id === "inspectLink")
      $("#linkAttachments").textContent = err.message;
    else message(err.message);
  } finally {
    b.disabled = false;
  }
});

document.addEventListener("input", (e) => {
  if (e.target === $("#docForm").elements.source_url) {
    $("#linkTools").hidden =
      !e.target.value.trim() || !!$("#docForm").elements.file.files.length;
    $("#linkAttachments").textContent = "";
  }
  if (e.target.id === "workspaceSearch") renderWorkspaceCards();
  if (e.target.id === "reviewSearch") renderManagerReviews();
});
document.addEventListener("change", async (e) => {
  if (!e.target.dataset.moveCase) return;
  const c = state.cases.find((c) => c.id === e.target.dataset.moveCase);
  const { workspace_id, topic, owner, queue, stage, next_action } = c.workflow;
  e.target.disabled = true;
  try {
    await json(`/api/cases/${c.id}/workflow`, {
      method: "PATCH",
      body: JSON.stringify({
        workspace_id: e.target.value,
        topic,
        owner,
        queue,
        stage,
        next_action,
      }),
    });
    await refreshCases();
    renderWorkspaceCards();
    renderManagerReviews();
    message("Review moved.");
  } catch (err) {
    e.target.value = workspace_id;
    message(err.message);
  } finally {
    e.target.disabled = false;
  }
});

function showModelContext(claimId) {
  const run = state.current.runs.find((r) => r.id === state.runId);
  const finding = run?.result?.findings.find((f) => f.claim_id === claimId);
  if (!finding) return;
  feature(
    "Model context",
    `<p class="muted">Candidate excerpts retrieved for this claim. Their presence does not establish support or contradiction.</p><h3>${esc(finding.text)}</h3>${finding.passages.map((p) => `<section class="citation"><strong>${esc(p.title)} · p. ${p.page}</strong><p>${esc(p.text)}</p><button class="text-button" data-document="${esc(p.document_id)}" data-page="${p.page}">Open source page</button></section>`).join("") || "<p>No relevant excerpts were retrieved.</p>"}`,
  );
}
