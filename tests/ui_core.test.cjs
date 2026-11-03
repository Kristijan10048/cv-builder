"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ui = require("../static/ui_core.js");

test("structured and array errors produce readable messages", () => {
  assert.equal(ui.formatError({ error: { message: "Refresh", code: "revision_conflict" } }), "Refresh");
  assert.equal(ui.formatError({ detail: [{ msg: "Too short" }, { msg: "Required" }] }), "Too short; Required");
  assert.equal(ui.formatError({ detail: { message: "Board failure", warnings: ["Offline"] } }), "Board failure");
  assert.equal(ui.formatError(null), "Something went wrong.");
});
test("legacy SQLite and offset-bearing ISO values represent the same instant", () => {
  assert.equal(ui.formatDate("2030-01-01 10:00:00"), ui.formatDate("2030-01-01T10:00:00Z"));
  assert.equal(ui.formatDate("2030-01-01T11:00:00+01:00"), ui.formatDate("2030-01-01T10:00:00Z"));
  assert.equal(ui.formatDate("bad date"), "bad date");
  assert.equal(ui.escapeHtml('<img src="x" onerror=\'alert(1)\'>&'), "&lt;img src=&quot;x&quot; onerror=&#39;alert(1)&#39;&gt;&amp;");
});
test("transport handles 204, safe non-JSON failure, structured metadata and abort", async () => {
  const previous = global.fetch;
  try {
    global.fetch = async () => ({ ok: true, status: 204 });
    assert.equal(await ui.request("/test"), null);
    global.fetch = async () => ({ ok: false, status: 503, json: async () => { throw new Error("private html"); } });
    await assert.rejects(ui.request("/test"), { message: "Something went wrong.", status: 503 });
    global.fetch = async () => ({ ok: false, status: 409, json: async () => ({ error: { code: "revision_conflict", message: "Refresh" } }) });
    await assert.rejects(ui.request("/test"), { code: "revision_conflict", status: 409 });
    const controller = new AbortController();
    controller.abort();
    global.fetch = async (url, options) => { options.signal.throwIfAborted(); };
    await assert.rejects(ui.request("/test", { signal: controller.signal }), { name: "AbortError" });
  } finally { global.fetch = previous; }
});
test("view transitions leave before enter and do not duplicate entry", async () => {
  const calls = [];
  ui.registerView("one", { enter: () => calls.push("enter one"), leave: () => calls.push("leave one") });
  ui.registerView("two", { enter: () => calls.push("enter two"), leave: () => calls.push("leave two") });
  await ui.enterView("one");
  await ui.enterView("one");
  await ui.enterView("two");
  await ui.enterView("legacy");
  assert.deepEqual(calls, ["enter one", "leave one", "enter two", "leave two"]);
});
