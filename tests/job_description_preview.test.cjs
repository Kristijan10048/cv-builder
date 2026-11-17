"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { JobDescriptionPreview } = require("../static/job_description_preview.js");

/** Minimal DOM fixture for real controller events, focus, and layout restoration. */
function fixture() {
  const window = {
    scrollX: 0, scrollY: 240, mobile: false, scrollCalls: [],
    matchMedia() { return { matches: this.mobile }; },
    scrollTo(position) { this.scrollCalls.push(position); },
  };
  const document = { defaultView: window, activeElement: null };
  function element() {
    const classes = new Set();
    const attributes = {};
    return {
      ownerDocument: document, listeners: {}, hidden: false, textContent: "", scrollTop: 0, scrollLeft: 0,
      classList: {
        add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
        toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
      },
      addEventListener(name, handler) { this.listeners[name] = handler; },
      setAttribute(name, value) { attributes[name] = value; },
      getAttribute(name) { return attributes[name]; },
      focus(options) { document.activeElement = this; this.focusOptions = options; },
      set innerHTML(value) { throw new Error("Posting text must never be inserted as HTML"); },
    };
  }
  const view = element();
  const elements = Object.fromEntries([
    "#availableJobsWorkspace", "#availableJobsList", ".application-table-wrap", "#jobDescriptionPreview",
    "#jobDescriptionTitle", "#jobDescriptionContent", "#jobDescriptionClose", "#availableJobsSearch",
  ].map(selector => [selector, element()]));
  view.querySelector = selector => elements[selector];
  const [workspace, list, table, panel, title, content, close, search] = Object.values(elements);
  panel.hidden = true;
  panel.contains = target => [panel, title, content, close].includes(target);
  list.buttons = [];
  list.querySelectorAll = () => list.buttons;
  list.contains = button => list.buttons.includes(button);
  function replaceRows(items) {
    list.buttons = items.map(item => {
      const button = element();
      const row = element();
      button.dataset = { jobId: String(item.id) };
      button.closest = selector => selector === "tr" ? row : button;
      button.click = () => list.listeners.click({ target: button });
      return button;
    });
  }
  const columns = {
    widths: [180, 320, 110], captures: 0,
    capture() { this.captures++; return [...this.widths]; },
    restore(widths) { this.widths = [...widths]; },
  };
  const preview = new JobDescriptionPreview(view, columns);
  const jobs = [{ id: 1, job_title: "C# Developer", description: "First line\n\n<script>unsafe()</script>" },
    { id: 2, job_title: "Simulation Developer", description: "  " }];
  const refresh = (items = jobs) => { replaceRows(items); preview.setItems(items); };
  refresh();
  return { preview, view, workspace, list, table, panel, title, content, close, search, columns, document, window, jobs, refresh };
}

test("click opens literal full text; switching jobs keeps the original layout snapshot", () => {
  const f = fixture();
  f.table.scrollLeft = 45;
  f.list.buttons[0].click();
  assert.equal(f.panel.hidden, false);
  assert.equal(f.workspace.classList.contains("preview-open"), true);
  assert.equal(f.content.textContent, f.jobs[0].description);
  assert.equal(f.title.textContent, "C# Developer");
  assert.equal(f.document.activeElement, f.title);
  assert.equal(f.list.buttons[0].getAttribute("aria-expanded"), "true");
  f.columns.widths = [110, 110, 110];
  f.table.scrollLeft = 100;
  f.content.scrollTop = 90;
  f.list.buttons[1].click();
  assert.equal(f.content.textContent, "No description available");
  assert.equal(f.content.scrollTop, 0);
  assert.equal(f.columns.captures, 1);
  assert.equal(f.list.buttons[0].getAttribute("aria-expanded"), "false");
  f.close.listeners.click();
  assert.equal(f.panel.hidden, true);
  assert.equal(f.workspace.classList.contains("preview-open"), false);
  assert.deepEqual(f.columns.widths, [180, 320, 110]);
  assert.equal(f.table.scrollLeft, 45);
  assert.equal(f.document.activeElement, f.list.buttons[1]);
  assert.equal(f.window.scrollCalls[0].top, 240);
});

test("Escape closes the preview but respects already handled keyboard events", () => {
  const f = fixture();
  f.preview.open(1);
  f.view.listeners.keydown({ key: "Escape", defaultPrevented: true });
  assert.equal(f.panel.hidden, false);
  let prevented = false;
  f.view.listeners.keydown({ key: "Escape", preventDefault() { prevented = true; }, stopPropagation() {} });
  assert.equal(prevented, true);
  assert.equal(f.panel.hidden, true);
  assert.equal(f.document.activeElement, f.list.buttons[0]);
});

test("refresh retains selection and reading position, then updates changed text", () => {
  const f = fixture();
  f.preview.open(1);
  f.content.scrollTop = 120;
  f.refresh();
  assert.equal(f.content.scrollTop, 120);
  assert.equal(f.list.buttons[0].getAttribute("aria-expanded"), "true");
  f.refresh([{ ...f.jobs[0], description: "Updated posting" }]);
  assert.equal(f.content.textContent, "Updated posting");
  f.close.listeners.click();
  assert.equal(f.document.activeElement, f.list.buttons[0], "focus goes to the replacement row");
});

test("filter/page removal closes; focus stays on filters or returns from hidden preview", () => {
  const f = fixture();
  f.preview.open(1);
  f.search.focus();
  f.refresh([f.jobs[1]]);
  assert.equal(f.panel.hidden, true);
  assert.equal(f.document.activeElement, f.search);
  f.preview.open(2);
  f.refresh([]);
  assert.equal(f.panel.hidden, true);
  assert.equal(f.document.activeElement, f.search);
});

test("leaving the view clears the preview without stealing navigation focus or scrolling", () => {
  const f = fixture();
  f.preview.open(1);
  const navigation = {};
  f.document.activeElement = navigation;
  f.preview.close({ restoreFocus: false, restoreScroll: false });
  f.refresh();
  assert.equal(f.panel.hidden, true);
  assert.equal(f.preview.selectedId, null);
  assert.equal(f.document.activeElement, navigation);
  assert.equal(f.window.scrollCalls.length, 0);
});

test("mobile opening permits focus to scroll to the stacked preview; missing IDs are ignored", () => {
  const f = fixture();
  f.window.mobile = true;
  f.preview.open(99);
  assert.equal(f.panel.hidden, true);
  assert.equal(f.columns.captures, 0);
  f.preview.open(1);
  assert.equal(f.title.focusOptions.preventScroll, false);
});
