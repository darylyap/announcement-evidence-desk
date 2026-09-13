const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

function harness(formId, fields, fail = false) {
  const handlers = {},
    requests = [],
    notices = [];
  let prevented = false,
    closed = false;
  const error = { textContent: "" };
  const context = vm.createContext({
    document: {
      addEventListener: (event, fn) => (handlers[event] ??= []).push(fn),
    },
    state: { current: { id: "review-1" } },
    FormData: class {
      constructor() {
        return Object.entries(fields);
      }
    },
    busy() {},
    message: (text) => notices.push(text),
    json: async (url, options) => {
      requests.push({ url, ...options });
      if (fail) throw Error("Deletion failed; record retained.");
    },
    $: (selector) =>
      selector === "#featureDialog"
        ? {
            close() {
              closed = true;
            },
          }
        : error,
    refreshCases: async () => {},
    openCase: async () => {},
  });
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../web/features.js"), "utf8"),
    context,
  );
  context.refreshWorkspaces = async () => {};
  context.manageWorkspaces = () => {};
  const event = {
    // A named "id" input can shadow form.id in the browser.
    target: {
      id: { value: fields.id },
      getAttribute: () => formId,
      querySelector: () => error,
    },
    preventDefault() {
      prevented = true;
    },
  };
  return {
    context,
    requests,
    error,
    notices,
    run: async () => {
      for (const fn of handlers.submit) await fn(event);
      return { prevented, closed };
    },
  };
}

test("rename submits the workspace ID without navigating the page", async () => {
  const h = harness("workspaceRename", {
    id: "workspace-1",
    name: "Bank coverage",
  });
  assert.deepEqual(await h.run(), { prevented: true, closed: true });
  assert.equal(h.requests[0].url, "/api/workspaces/workspace-1");
  assert.equal(h.requests[0].method, "PATCH");
  assert.deepEqual(JSON.parse(h.requests[0].body), { name: "Bank coverage" });
});
for (const [kind, resource] of [
  ["case", "cases"],
  ["workspace", "workspaces"],
  ["document", "documents"],
]) {
  test(`confirmed ${kind} deletion reaches the correct endpoint`, async () => {
    const h = harness("deleteEntry", { id: "entry-1", kind });
    assert.deepEqual(await h.run(), { prevented: true, closed: true });
    assert.equal(h.requests[0].url, `/api/${resource}/entry-1`);
    assert.equal(h.requests[0].method, "DELETE");
  });
}
test("failed deletion leaves the dialog open and reports the error", async () => {
  const h = harness("deleteEntry", { id: "review-1", kind: "case" }, true);
  assert.deepEqual(await h.run(), { prevented: true, closed: false });
  assert.equal(h.context.state.current.id, "review-1");
  assert.match(h.error.textContent, /record retained/);
  assert.equal(h.notices.length, 0);
});

function claimHarness(fail = false) {
  const handlers = {},
    requests = [],
    errors = { textContent: "" };
  let refreshed = 0;
  const context = vm.createContext({
    document: {
      addEventListener: (type, fn) => (handlers[type] ??= []).push(fn),
    },
    state: { current: { id: "case-1" }, runId: "run-1", view: "review" },
    FormData: class {
      constructor(form) {
        return Object.entries(form.fields);
      }
    },
    busy() {},
    message() {},
    json: async (url, options) => {
      requests.push({ url, body: JSON.parse(options.body) });
      if (fail) throw Error("Save failed. Try again.");
    },
    openCase: async () => {
      refreshed++;
    },
    refreshCases: async () => {},
  });
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../web/assessments.js"), "utf8"),
    context,
  );
  const form = (id, note) => ({
    dataset: { runId: "run-1", claimId: id },
    fields: { verdict: "accept", reviewer: "Analyst A", note },
    matches: () => true,
    querySelector: () => errors,
  });
  const draft = (f) => handlers.input[0]({ target: { closest: () => f } });
  return {
    context,
    requests,
    errors,
    form,
    draft,
    saved: () => refreshed,
    submit: (f) => handlers.submit[0]({ target: f, preventDefault() {} }),
    drafts: () =>
      JSON.parse(vm.runInContext("JSON.stringify([...claimDrafts])", context)),
  };
}

test("saving one claim preserves an unfinished assessment of another", async () => {
  const h = claimHarness();
  const first = h.form("claim-1", "Revenue confirmed.");
  const second = h.form("claim-2", "Checking the approval date.");
  h.draft(first);
  h.draft(second);
  await h.submit(first);
  assert.equal(h.requests[0].body.claim_id, "claim-1");
  assert.equal(h.requests[0].url, "/api/runs/run-1/decisions");
  assert.deepEqual(h.drafts(), [["run-1:claim-2", second.fields]]);
  assert.equal(h.saved(), 1);
});

test("failed claim save keeps the draft and reports the error in that form", async () => {
  const h = claimHarness(true);
  const f = h.form("claim-1", "Source figure confirmed.");
  h.draft(f);
  await h.submit(f);
  assert.deepEqual(h.drafts(), [["run-1:claim-1", f.fields]]);
  assert.match(h.errors.textContent, /Save failed/);
  assert.equal(h.saved(), 0);
});
