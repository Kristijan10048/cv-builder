"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

test("preview sizes only five visible columns and restores all eight original widths", () => {
  let previewOpen = false;
  let resizeObserved;
  function element() {
    return {
      children: [], style: {}, listeners: {},
      classList: { add() {}, remove() {}, contains() { return false; } },
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      setAttribute() {}, addEventListener(name, handler) { this.listeners[name] = handler; },
    };
  }
  const container = { clientWidth: 1200 };
  const workspace = { classList: { contains() { return previewOpen; } } };
  const headers = [180, 230, 150, 120, 120, 160, 130, 110].map((width, index) => ({
    ...element(), textContent: String(index),
    classList: { contains() { return [3, 4, 5].includes(index); } },
    getBoundingClientRect() { return { width }; },
  }));
  let columnGroup;
  const table = {
    ...element(), querySelectorAll() { return headers; },
    querySelector() { return { before(element) { columnGroup = element; } }; },
    closest(selector) { return selector === ".application-table-wrap" ? container : workspace; },
  };
  const context = vm.createContext({
    $: () => table,
    document: { createElement: element, body: element() },
    window: { matchMedia: () => ({ matches: false }), addEventListener() {} },
    ResizeObserver: class { constructor(callback) { resizeObserved = callback; } observe() {} },
  });
  const source = readFileSync(require.resolve("../static/available_jobs.js"), "utf8");
  vm.runInContext(source.split("const jobColumnSizing =")[0], context);
  const sizing = vm.runInContext("enableJobColumnResizing()", context);
  resizeObserved();
  headers[1].children[0].listeners.keydown({ key: "ArrowRight", preventDefault() {} });
  const snapshot = sizing.capture();
  const originalColumns = [...columnGroup.children];
  const originalWidths = originalColumns.map(column => column.style.width);

  previewOpen = true;
  container.clientWidth = 700;
  resizeObserved();
  assert.deepEqual(columnGroup.children, [0, 1, 2, 6, 7].map(index => originalColumns[index]));
  assert.equal(table.style.width, "700px");
  assert.ok(Math.abs(columnGroup.children.reduce((sum, column) => sum + parseFloat(column.style.width), 0) - 700) < 0.01);
  const titleBeforeResize = parseFloat(originalColumns[1].style.width);
  headers[1].children[0].listeners.keydown({ key: "ArrowRight", preventDefault() {} });
  assert.ok(parseFloat(originalColumns[1].style.width) > titleBeforeResize);
  assert.equal(originalColumns[3].style.width, originalWidths[3], "hidden columns are not resized");

  previewOpen = false;
  container.clientWidth = 1200;
  sizing.restore(snapshot);
  assert.equal(columnGroup.children.length, 8);
  assert.deepEqual(columnGroup.children.map(column => column.style.width), originalWidths);
});
