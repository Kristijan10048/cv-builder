"use strict";

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");
const backgroundSource = readFileSync(join(__dirname, "../firefox-extension/background.js"), "utf8");

for (const enabled of [false, true]) {
  test(`autofill upgrade removes legacy registration when enabled=${enabled}`, async () => {
    const registrations = new Map([["applykit-auto-fill", { id: "applykit-auto-fill" }]]);
    const listener = { addListener() {} };
    const context = {
      browser: {
        storage: { local: { get: async () => ({ autoFillEnabled: enabled }) } },
        permissions: { contains: async () => true },
        scripting: {
          getRegisteredContentScripts: async ({ ids }) =>
            Array.from(registrations.values()).filter(script => ids.includes(script.id)),
          unregisterContentScripts: async ({ ids }) => {
            for (const identifier of ids) registrations.delete(identifier);
          },
          registerContentScripts: async scripts => {
            for (const script of scripts) registrations.set(script.id, script);
          },
        },
        runtime: { onMessage: listener, onInstalled: listener, onStartup: listener },
        commands: { onCommand: listener },
      },
    };
    runInNewContext(backgroundSource, context);
    assert.equal(await context.configureAutoFill(), enabled);
    assert.equal(registrations.has("applykit-auto-fill"), false);
    assert.equal(registrations.has("cv_builder-auto-fill"), enabled);
    assert.equal(registrations.size, enabled ? 1 : 0);
    if (enabled) {
      assert.equal(registrations.get("cv_builder-auto-fill").js.join(), "content.js");
    }
  });
}