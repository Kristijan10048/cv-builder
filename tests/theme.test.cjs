"use strict";

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");
const themeSource = readFileSync(join(__dirname, "../static/theme.js"), "utf8");

/** Emulate the browser APIs used before and after the Settings markup exists. */
function createBrowser({ preference = null, legacyPreference = null, darkSystem = false, storageBlocked = false, writesBlocked = false } = {}) {
  const documentEvents = {};
  const windowEvents = {};
  const toggleEvents = {};
  const attributes = {};
  const systemTheme = {
    matches: darkSystem,
    addEventListener: (eventName, callback) => { systemTheme.onChange = callback; },
  };
  const toggleButton = {
    setAttribute: (name, value) => { attributes[name] = value; },
    addEventListener: (eventName, callback) => { toggleEvents[eventName] = callback; },
  };
  const themeStatus = { textContent: "" };
  const storedValues = new Map(preference === null ? [] : [["cv_builder.theme", preference]]);
  if (legacyPreference !== null) storedValues.set("applykit.theme", legacyPreference);
  let markupReady = false;
  const document = {
    documentElement: { dataset: {} },
    getElementById: identifier => markupReady
      ? ({ themeToggle: toggleButton, themeStatus })[identifier] : null,
    addEventListener: (eventName, callback) => { documentEvents[eventName] = callback; },
  };
  const window = {
    matchMedia: () => systemTheme,
    localStorage: {
      getItem: key => {
        if (storageBlocked) throw new Error("Storage unavailable");
        return storedValues.get(key) ?? null;
      },
      removeItem: key => { storedValues.delete(key); },
      setItem: (key, value) => {
        if (storageBlocked || writesBlocked) throw new Error("Storage unavailable");
        storedValues.set(key, value);
      },
    },
    addEventListener: (eventName, callback) => { windowEvents[eventName] = callback; },
  };
  runInNewContext(themeSource, { document, window });
  return {
    document, attributes, storedValues, themeStatus,
    mount() { markupReady = true; documentEvents.DOMContentLoaded(); },
    toggle() { toggleEvents.click(); },
    systemChange(isDark) { systemTheme.matches = isDark; systemTheme.onChange(); },
    storageChange(key = "cv_builder.theme") { windowEvents.storage({ key }); },
  };
}

for (const darkSystem of [false, true]) {
  test(`system ${darkSystem ? "dark" : "light"} theme applies before markup loads`, () => {
    const browser = createBrowser({ darkSystem });
    assert.equal(browser.document.documentElement.dataset.theme, darkSystem ? "dark" : "light");
    browser.mount();
    assert.equal(browser.attributes["aria-checked"], String(darkSystem));
    assert.equal(browser.themeStatus.textContent, darkSystem ? "Dark mode on" : "Light mode on");
    assert.equal(browser.storedValues.size, 0);
    browser.systemChange(!darkSystem);
    assert.equal(browser.document.documentElement.dataset.theme, darkSystem ? "light" : "dark");
  });
}

for (const preference of ["light", "dark"]) {
  test(`saved ${preference} choice overrides system changes`, () => {
    const browser = createBrowser({ preference, darkSystem: preference === "light" });
    browser.mount();
    assert.equal(browser.document.documentElement.dataset.theme, preference);
    browser.systemChange(false);
    browser.systemChange(true);
    assert.equal(browser.document.documentElement.dataset.theme, preference);
  });
}

test("switch updates accessibility state, persists both choices and restores after reload", () => {
  const browser = createBrowser();
  browser.mount();
  browser.toggle();
  assert.equal(browser.document.documentElement.dataset.theme, "dark");
  assert.equal(browser.attributes["aria-checked"], "true");
  assert.equal(browser.themeStatus.textContent, "Dark mode on");
  assert.equal(browser.storedValues.get("cv_builder.theme"), "dark");
  const reloadedBrowser = createBrowser({ preference: browser.storedValues.get("cv_builder.theme") });
  reloadedBrowser.mount();
  assert.equal(reloadedBrowser.attributes["aria-checked"], "true");
  browser.toggle();
  assert.equal(browser.attributes["aria-checked"], "false");
  assert.equal(browser.themeStatus.textContent, "Light mode on");
  assert.equal(browser.storedValues.get("cv_builder.theme"), "light");
  browser.systemChange(true);
  assert.equal(browser.document.documentElement.dataset.theme, "light");
});

test("invalid preferences fall back to system without writing storage", () => {
  const browser = createBrowser({ preference: "invalid", darkSystem: true });
  browser.mount();
  assert.equal(browser.attributes["aria-checked"], "true");
  browser.systemChange(false);
  assert.equal(browser.attributes["aria-checked"], "false");
  assert.equal(browser.storedValues.get("cv_builder.theme"), "invalid");
});

test("blocked storage still permits switching and preserves the session choice", () => {
  const browser = createBrowser({ storageBlocked: true });
  browser.mount();
  browser.toggle();
  browser.systemChange(true);
  browser.systemChange(false);
  assert.equal(browser.document.documentElement.dataset.theme, "dark");
  assert.equal(browser.attributes["aria-checked"], "true");
  browser.toggle();
  assert.equal(browser.document.documentElement.dataset.theme, "light");
});

test("other tabs synchronize theme preferences and resume system theme after clearing storage", () => {
  const browser = createBrowser();
  browser.mount();
  browser.storedValues.set("cv_builder.theme", "dark");
  browser.storageChange("unrelated");
  assert.equal(browser.attributes["aria-checked"], "false");
  browser.storageChange();
  assert.equal(browser.attributes["aria-checked"], "true");
  browser.storedValues.delete("cv_builder.theme");
  browser.storageChange(null);
  assert.equal(browser.attributes["aria-checked"], "false");
  browser.systemChange(true);
  assert.equal(browser.attributes["aria-checked"], "true");
});

test("existing theme preference migrates without resetting the choice", () => {
  const browser = createBrowser({ legacyPreference: "dark" });
  assert.equal(browser.document.documentElement.dataset.theme, "dark");
  assert.equal(browser.storedValues.get("cv_builder.theme"), "dark");
  assert.equal(browser.storedValues.has("applykit.theme"), false);
  browser.storedValues.delete("cv_builder.theme");
  browser.storageChange(null);
  assert.equal(browser.document.documentElement.dataset.theme, "light");
});

test("canonical theme preference takes precedence over the old setting", () => {
  const browser = createBrowser({ preference: "light", legacyPreference: "dark" });
  assert.equal(browser.document.documentElement.dataset.theme, "light");
});

test("existing theme remains usable when storage writes are blocked", () => {
  const browser = createBrowser({ legacyPreference: "dark", writesBlocked: true });
  assert.equal(browser.document.documentElement.dataset.theme, "dark");
});