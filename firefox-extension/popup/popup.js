const connection = document.querySelector("#connection");
const fillButton = document.querySelector("#fillButton");
const autoFill = document.querySelector("#autoFill");
const result = document.querySelector("#result");

function showResult(message, error = false) {
  result.textContent = message;
  result.className = `result${error ? " error" : ""}`;
}

async function checkConnection() {
  try {
    await browser.runtime.sendMessage({ type: "applykit:ping" });
    connection.textContent = "ApplyKit is connected";
    connection.className = "state connected";
    fillButton.disabled = false;
  } catch (_) {
    connection.textContent = "Start ApplyKit at 127.0.0.1:8000";
    connection.className = "state error";
    fillButton.disabled = true;
  }
}

async function loadPreferences() {
  const stored = await browser.storage.local.get("autoFillEnabled");
  autoFill.checked = Boolean(stored.autoFillEnabled);
}

fillButton.addEventListener("click", async () => {
  fillButton.disabled = true;
  showResult("Filling…");
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("No active page was found.");
    await browser.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["/content.js"],
    });
    const response = await browser.tabs.sendMessage(tab.id, {
      type: "applykit:fill",
    });
    const count = response?.count || 0;
    showResult(count ? `Filled ${count} field${count === 1 ? "" : "s"}.` : "No matching empty fields found.");
  } catch (error) {
    showResult(error.message || "This page cannot be filled.", true);
  } finally {
    fillButton.disabled = false;
  }
});

autoFill.addEventListener("change", async () => {
  if (autoFill.checked) {
    const granted = await browser.permissions.request({ origins: ["<all_urls>"] });
    if (!granted) {
      autoFill.checked = false;
      showResult("Website access was not granted.", true);
      return;
    }
  }

  await browser.storage.local.set({ autoFillEnabled: autoFill.checked });
  const response = await browser.runtime.sendMessage({
    type: "applykit:configure-auto-fill",
  });
  autoFill.checked = Boolean(response.enabled);

  if (!autoFill.checked) {
    await browser.permissions.remove({ origins: ["<all_urls>"] });
    showResult("Automatic filling is off.");
  } else {
    showResult("Automatic filling is enabled.");
  }
});

Promise.all([checkConnection(), loadPreferences()]).catch((error) => {
  showResult(error.message, true);
});

