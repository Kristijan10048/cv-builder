(() => {
  "use strict";

  const C_STORAGE_KEY = "cv_builder.theme";
  const C_LEGACY_STORAGE_KEY = "applykit.theme";
  const C_DARK = "dark";
  const C_LIGHT = "light";
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  let preferredTheme = null;

  /** Read only supported preferences; storage may be disabled by the browser. */
  function readPreference() {
    try {
      let storedTheme = window.localStorage.getItem(C_STORAGE_KEY);
      if (storedTheme === null) {
        storedTheme = window.localStorage.getItem(C_LEGACY_STORAGE_KEY);
        if ([C_DARK, C_LIGHT].includes(storedTheme)) {
          // Preserve the old choice even if storage cannot be updated.
          try {
            window.localStorage.setItem(C_STORAGE_KEY, storedTheme);
            window.localStorage.removeItem(C_LEGACY_STORAGE_KEY);
          } catch { /* Reading preferences can work while writes are blocked. */ }
        }
      }
      return [C_DARK, C_LIGHT].includes(storedTheme) ? storedTheme : null;
    } catch {
      return null;
    }
  }

  /** Apply the palette and keep the accessible Settings switch in sync. */
  function applyTheme() {
    const activeTheme = preferredTheme || (systemTheme.matches ? C_DARK : C_LIGHT);
    const isDark = activeTheme === C_DARK;
    document.documentElement.dataset.theme = activeTheme;
    const toggleButton = document.getElementById("themeToggle");
    const themeStatus = document.getElementById("themeStatus");
    if (toggleButton) toggleButton.setAttribute("aria-checked", String(isDark));
    if (themeStatus) themeStatus.textContent = isDark ? "Dark mode on" : "Light mode on";
  }

  /** Change appearance immediately, even when persistence is unavailable. */
  function toggleTheme() {
    preferredTheme = document.documentElement.dataset.theme === C_DARK ? C_LIGHT : C_DARK;
    try {
      window.localStorage.setItem(C_STORAGE_KEY, preferredTheme);
    } catch {
      // Retain the user's choice for this page when storage is unavailable.
    }
    applyTheme();
  }

  preferredTheme = readPreference();
  // Run before the stylesheet loads to avoid a flash of the wrong theme.
  applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);
    applyTheme();
  });
  systemTheme.addEventListener("change", () => {
    if (!preferredTheme) applyTheme();
  });
  window.addEventListener("storage", event => {
    if (event.key === C_STORAGE_KEY || event.key === null) {
      preferredTheme = readPreference();
      applyTheme();
    }
  });
})();
