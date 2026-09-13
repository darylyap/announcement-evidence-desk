const claimDrafts = new Map();
const decisionLabel = (v) =>
  ({
    accept: "Agrees with AI finding",
    reject: "Disagrees with AI finding",
    needs_evidence: "Needs more evidence",
  })[v] || v;
function claimAssessmentHTML(f, run) {
  const history = run.decisions.filter((d) => d.claim_id === f.claim_id);
  const current = history.at(-1);
  const draft = claimDrafts.get(`${run.id}:${f.claim_id}`) || current || {};
  const options = [
    ["", "Choose an assessment"],
    ["accept", "Agree with AI finding"],
    ["reject", "Disagree with AI finding"],
    ["needs_evidence", "Need more evidence"],
  ];
  return `<section class="claim-assessment"><div class="panel-top"><h4>Your assessment of this claim</h4>${helpTip("Assess this claim only. Agree means accepting the AI's supported, contradicted or insufficient finding; it does not necessarily mean the claim is true. Give your reason. Each claim and each analysis keep separate assessments.", "Claim assessment help")}</div><form class="claim-review-form" data-run-id="${esc(run.id)}" data-claim-id="${esc(f.claim_id)}"><div class="form-row"><label>Assessment<select name="verdict" required>${options.map(([value, label]) => `<option value="${value}" ${draft.verdict === value ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Reviewer<select name="reviewer" required>${reviewerOptions(draft.reviewer || "", false)}</select></label></div><label>Reason / follow-up<textarea name="note" required minlength="5" maxlength="2000" rows="2" placeholder="What did you verify for this claim?">${esc(draft.note || "")}</textarea></label><p class="form-error" role="alert"></p><button type="submit" class="primary">${current ? "Save revised assessment" : "Save claim assessment"}</button></form>${current ? `<div class="decision"><strong>${esc(decisionLabel(current.verdict))}</strong><p>${esc(current.note)}</p><small>${esc(current.reviewer)} · Saved ${date(current.created_at)}</small></div>` : '<p class="muted">Pending assessment</p>'}${
    history.length > 1
      ? `<details><summary>Earlier assessments of this claim (${history.length - 1})</summary>${history
          .slice(0, -1)
          .reverse()
          .map(
            (d) =>
              `<p><strong>${esc(decisionLabel(d.verdict))}</strong> · ${esc(d.reviewer)} · ${date(d.created_at)}<br>${esc(d.note)}</p>`,
          )
          .join("")}</details>`
      : ""
  }</section>`;
}
function assessmentSummaryHTML(run) {
  const a = run.assessment;
  const earlier = run.decisions.filter((d) => !d.claim_id);
  return `<section class="panel"><h3>Claim assessments</h3><p><strong>${a.assessed} of ${a.total} claims assessed</strong></p><p class="muted">${a.pending} pending · ${a.needs_evidence} need more evidence</p>${
    earlier.length
      ? `<details><summary>Earlier overall assessments</summary><p class="muted">These records do not specify individual claims.</p>${earlier
          .slice()
          .reverse()
          .map(
            (d) =>
              `<p><strong>${esc(human(d.verdict))}</strong><br>${esc(d.note)}<br><small>${esc(d.reviewer)} · ${date(d.created_at)}</small></p>`,
          )
          .join("")}</details>`
      : ""
  }</section>`;
}
function rememberClaimDraft(e) {
  const form = e.target.closest(".claim-review-form");
  if (form)
    claimDrafts.set(
      `${form.dataset.runId}:${form.dataset.claimId}`,
      Object.fromEntries(new FormData(form)),
    );
}
document.addEventListener("input", rememberClaimDraft);
document.addEventListener("change", rememberClaimDraft);
document.addEventListener("submit", async (e) => {
  const form = e.target;
  if (!form.matches(".claim-review-form")) return;
  e.preventDefault();
  const { runId, claimId } = form.dataset;
  const cid = state.current.id;
  const body = { ...Object.fromEntries(new FormData(form)), claim_id: claimId };
  const key = `${runId}:${claimId}`;
  const savedDraft = JSON.stringify(claimDrafts.get(key));
  busy(form, true);
  form.querySelector(".form-error").textContent = "";
  try {
    await json(`/api/runs/${runId}/decisions`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (JSON.stringify(claimDrafts.get(key)) === savedDraft)
      claimDrafts.delete(key);
    if (
      state.current?.id === cid &&
      state.runId === runId &&
      state.view === "review"
    )
      await openCase(cid);
    else await refreshCases();
    message("Claim assessment saved.");
  } catch (err) {
    form.querySelector(".form-error").textContent = err.message;
  } finally {
    busy(form, false);
  }
});
