"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const { buildDefinition, localInput, RunRequests, ScheduledTasksPage } = require("../static/scheduled_tasks.js");
const ui = require("../static/ui_core.js");
const fixture = JSON.parse(readFileSync(require("node:path").join(__dirname, "../docs/roadmap_scheduler/contract_examples.json"), "utf8"));
const values = { name: " Example ", preference: "1", sites: ["linkedin"], results: "50", seconds: "86400", kind: "interval", start: "2035-01-01T09:00:00" };

test("form converts local time to UTC and preserves an untouched original anchor", () => {
  const definition = buildDefinition(values, null, 0);
  assert.equal(definition.name, "Example");
  assert.equal(definition.trigger.starts_at, new Date(values.start).toISOString());
  const original = { ...definition, trigger: { ...definition.trigger, starts_at: "2030-01-01T09:00:00.123Z" } };
  const replacement = buildDefinition({ ...values, start: localInput(original.trigger.starts_at) }, original);
  assert.deepEqual(replacement.trigger, original.trigger);
  assert.doesNotMatch(localInput("2030-01-01T09:00:00Z"), /:00:00$/);
});
for (const invalid of [{ name: " " }, { sites: [] }, { seconds: "299" }, { seconds: "600.5" }, { results: "1001" }, { results: "1.5" }, { start: "bad" }, { start: "2000-01-01T00:00" }]) {
  test(`form rejects ${JSON.stringify(invalid)}`, () => assert.throws(() => buildDefinition({ ...values, ...invalid })));
}
test("run-now retries retain both key and original revision and suppress double clicks", async () => {
  let count = 0;
  const requests = new RunRequests(() => `key-${++count}`);
  const sent = [];
  let release;
  const promise = requests.send({ id: 1, revision: 2 }, async body => { sent.push(body); await new Promise(resolve => { release = resolve; }); throw new Error("network"); });
  assert.equal(await requests.send({ id: 1, revision: 2 }, () => assert.fail()), null);
  release();
  await assert.rejects(promise);
  await requests.send({ id: 1, revision: 3 }, async body => { sent.push(body); return { run: { id: 1 } }; });
  assert.deepEqual(sent, [{ revision: 2, idempotency_key: "key-1" }, { revision: 2, idempotency_key: "key-1" }]);
  assert.equal(requests.pending.size, 0);
});

function fakePage(request) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, { textContent: "", innerHTML: "", dataset: {}, disabled: false, classList: { toggle() {}, add() {}, remove() {} }, addEventListener() {}, querySelector() { return null; } });
    return elements.get(id);
  }
  const document = { getElementById: element, addEventListener() {}, activeElement: null, hidden: false };
  const page = new ScheduledTasksPage(document, { ...ui, request });
  page.active = true;
  return { page, elements, element, document };
}
test("stale refresh responses cannot render after leave", async () => {
  const releases = [];
  const { page, element } = fakePage(() => new Promise(resolve => releases.push(resolve)));
  const refreshing = page.refresh();
  page.controller = new AbortController();
  const signal = page.controller.signal;
  page.leave();
  releases[0]({ items: [], total: 0, total_pages: 0, page: 1 });
  releases[1]({ state: "stopped" });
  releases[2]([]);
  await refreshing;
  assert.equal(signal.aborted, true);
  assert.equal(element("schedulerStatus").textContent, "");
});
test("offline health and empty state differ; history paging and warnings are escaped", async () => {
  const paths = [];
  const { page, element } = fakePage(async path => {
    paths.push(path);
    if (path.includes("/runs")) return { page: 2, total: 21, total_pages: 2, items: [{ state: "partial", source: "manual", queued_at: "2030-01-01T00:00:00Z", result: { fetched: 1, boards: {}, warnings: ["<script>bad</script>"] } }] };
    if (path.includes("status")) return { state: "stopped" };
    if (path.includes("preferences")) return [];
    return { items: [], total: 0, total_pages: 0, page: 1 };
  });
  await page.refresh();
  assert.match(element("schedulerStatus").textContent, /offline/);
  assert.match(element("scheduleList").innerHTML, /No schedules yet/);
  page.historyId = 1;
  page.historyPage = 2;
  await page.loadHistory();
  assert.ok(paths.includes("/api/task-schedules/1/runs?page=2"));
  assert.match(element("scheduleHistoryList").innerHTML, /&lt;script&gt;/);
  assert.equal(element("historyNext").disabled, true);
  assert.equal(element("historyPrevious").disabled, false);
  page.report({ code: "revision_conflict", message: "Changed" });
  assert.match(element("scheduleMessage").textContent, /Reload/);
});
test("frozen fixture schedules render without unsafe source text", () => {
  const definitions = [];
  function collect(value) {
    if (!value || typeof value !== "object") return;
    if (value.id && value.trigger && value.payload && typeof value.enabled === "boolean") definitions.push(value);
    Object.values(value).forEach(collect);
  }
  collect(fixture);
  assert.ok(definitions.length > 0);
  const { page, element } = fakePage();
  page.renderSchedules({ items: definitions.slice(0, 2), page: 1, total: 2, total_pages: 1 });
  assert.match(element("scheduleList").innerHTML, /Run now/);
});

test("accepted receipt advances from offline queued to completed on refresh", async () => {
  const { page, element } = fakePage(async path => {
    if (path.includes("status")) return { state: "fresh", queued_count: 0, running_count: 0 };
    if (path.includes("preferences")) return [];
    return { items: [{ id: 1, name: "Example", enabled: false, trigger: { kind: "once" }, payload: { sites: ["linkedin"] }, latest_run: { id: 5, state: "succeeded" } }], page: 1, total_pages: 1, total: 1 };
  });
  page.receipt = { id: 5, scheduleId: 1 };
  page.message("Queued · Worker is offline");
  await page.refresh();
  assert.match(element("scheduleMessage").textContent, /Succeeded/);
  assert.doesNotMatch(element("scheduleMessage").textContent, /offline/);
});
