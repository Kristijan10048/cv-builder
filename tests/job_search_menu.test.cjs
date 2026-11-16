"use strict";
const assert = require("node:assert/strict");
const { test } = require("node:test");
const { JobSearchMenu } = require("../static/job_search_menu.js");

/** Small DOM fixture exercising the controller through its registered UI events. */
function createMenuFixture() {
  const document = { activeElement: null };
  const elements = new Map();
  function createElement(id, attributes = {}) {
    const listeners = {};
    const element = {
      id, hidden: false, tabIndex: -1, textContent: "", ownerDocument: document,
      setAttribute(name, value) { attributes[name] = value; },
      getAttribute(name) { return attributes[name] ?? null; },
      addEventListener(name, callback) { listeners[name] = callback; },
      focus() { document.activeElement = element; },
      click() { element.focus(); listeners.click(); },
      press(key) {
        let prevented = false;
        listeners.keydown({ key, preventDefault() { prevented = true; } });
        return prevented;
      },
    };
    elements.set(id, element);
    return element;
  }
  const toggle = createElement("jobSearchMenuToggle");
  const tabList = createElement("jobSearchTabs");
  const panels = createElement("jobSearchPanels");
  const tabs = ["Fetch", "Preferences", "Tips"].map((name, index) => {
    const panelId = name === "Preferences" ? "jobSearchPreferencesView" : `jobSearch${name}Panel`;
    createElement(panelId);
    return createElement(`jobSearch${name}Tab`, {
      "aria-controls": panelId,
      "aria-selected": String(index === 0),
    });
  });
  tabList.querySelectorAll = () => tabs;
  const element = {
    ownerDocument: document,
    querySelector(selector) { return elements.get(selector.slice(1)); },
    contains(target) { return [...elements.values()].includes(target); },
  };
  let loads = 0;
  const menu = new JobSearchMenu(element, () => { loads += 1; });
  return { menu, document, elements, toggle, tabList, panels, tabs, loads: () => loads };
}

test("collapse restores the selected preference panel without replacing its draft", () => {
  const fixture = createMenuFixture();
  const preferencePanel = fixture.elements.get("jobSearchPreferencesView");
  preferencePanel.draft = { title: "Unsaved role", country: "Germany" };
  fixture.tabs[1].click();
  fixture.toggle.click();
  assert.equal(fixture.tabList.hidden, true);
  assert.equal(fixture.panels.hidden, true);
  assert.equal(fixture.toggle.getAttribute("aria-expanded"), "false");
  assert.equal(fixture.document.activeElement, fixture.toggle);
  fixture.toggle.click();
  assert.equal(fixture.panels.hidden, false);
  assert.equal(fixture.tabs[1].getAttribute("aria-selected"), "true");
  assert.equal(fixture.elements.get("jobSearchPreferencesView"), preferencePanel);
  assert.deepEqual(preferencePanel.draft, { title: "Unsaved role", country: "Germany" });
  assert.equal(fixture.loads(), 1, "show/hide must not reload the editor");
});

test("arrow keys wrap tabs, Home/End work, and normal Tab is not trapped", () => {
  const { tabs, document } = createMenuFixture();
  assert.equal(tabs[0].press("ArrowLeft"), true);
  assert.equal(document.activeElement, tabs[2]);
  assert.equal(tabs[2].getAttribute("aria-selected"), "true");
  tabs[2].press("ArrowRight");
  assert.equal(document.activeElement, tabs[0]);
  tabs[0].press("End");
  assert.equal(document.activeElement, tabs[2]);
  tabs[2].press("Home");
  assert.equal(document.activeElement, tabs[0]);
  assert.deepEqual(tabs.map(tab => tab.tabIndex), [0, -1, -1]);
  assert.equal(tabs[0].press("Tab"), false);
});

test("sidebar-style entry expands a collapsed menu and activates preferences", () => {
  const { menu, panels, tabs, loads } = createMenuFixture();
  menu.setExpanded(false);
  menu.setExpanded(true);
  menu.selectTab("jobSearchPreferencesTab");
  assert.equal(panels.hidden, false);
  assert.equal(tabs[1].getAttribute("aria-selected"), "true");
  assert.equal(loads(), 1);
  menu.selectTab("missing-tab");
  assert.equal(tabs[1].getAttribute("aria-selected"), "true");
});
