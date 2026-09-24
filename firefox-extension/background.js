const API_BASE = "http://127.0.0.1:8000";
const AUTO_SCRIPT_ID = "applykit-auto-fill";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `ApplyKit returned HTTP ${response.status}.`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

async function removeAutoScript() {
  const scripts = await browser.scripting.getRegisteredContentScripts({
    ids: [AUTO_SCRIPT_ID],
  });
  if (scripts.length) {
    await browser.scripting.unregisterContentScripts({ ids: [AUTO_SCRIPT_ID] });
  }
}

async function configureAutoFill() {
  const { autoFillEnabled = false } = await browser.storage.local.get(
    "autoFillEnabled"
  );
  const hasPermission = await browser.permissions.contains({
    origins: ["<all_urls>"],
  });

  await removeAutoScript();
  if (!autoFillEnabled || !hasPermission) {
    if (autoFillEnabled && !hasPermission) {
      await browser.storage.local.set({ autoFillEnabled: false });
    }
    return false;
  }

  await browser.scripting.registerContentScripts([
    {
      id: AUTO_SCRIPT_ID,
      matches: ["http://*/*", "https://*/*"],
      js: ["content.js"],
      runAt: "document_idle",
      allFrames: true,
      persistAcrossSessions: true,
    },
  ]);
  return true;
}

async function fillTab(tabId) {
  await browser.scripting.executeScript({
    target: { tabId },
    files: ["/content.js"],
  });
  return browser.tabs.sendMessage(tabId, { type: "applykit:fill" });
}

browser.runtime.onMessage.addListener((message) => {
  if (message?.type === "applykit:get-profile") {
    return api("/api/personal-details");
  }
  if (message?.type === "applykit:ping") {
    return api("/api/personal-details").then(() => ({ ok: true }));
  }
  if (message?.type === "applykit:configure-auto-fill") {
    return configureAutoFill().then((enabled) => ({ enabled }));
  }
  if (message?.type === "applykit:save-application") {
    const application = message.application || {};
    return api("/api/applications", {
      method: "POST",
      body: JSON.stringify({
        company: application.company || "Unknown company",
        job_title: application.job_title || "Job application",
        source_url: application.source_url || "",
        status: "Applied",
      }),
    });
  }
  return undefined;
});

browser.commands.onCommand.addListener(async (command) => {
  if (command !== "fill-current-page") return;
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    try {
      await fillTab(tab.id);
    } catch (_) {}
  }
});

browser.runtime.onInstalled.addListener(() => {
  configureAutoFill().catch(() => {});
});
browser.runtime.onStartup.addListener(() => {
  configureAutoFill().catch(() => {});
});
