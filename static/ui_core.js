/* Shared transport, presentation and view lifecycle. */
(function (root) {
  "use strict";
  const views = new Map();
  let currentView = null;
  function formatError(value) {
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(formatError).filter(Boolean).join("; ");
    if (value && typeof value === "object") return formatError(value.error || value.detail || value.message || value.msg || value.warnings);
    return "Something went wrong.";
  }
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    if (!response.ok) {
      let body = null;
      try { body = await response.json(); } catch (_) { /* Safe fallback for proxy HTML. */ }
      const error = new Error(formatError(body));
      error.status = response.status;
      error.code = body?.error?.code;
      error.detail = body?.error;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  function formatDate(value, options = { dateStyle: "medium", timeStyle: "short" }) {
    if (!value) return "Not recorded";
    const normalized = String(value).replace(" ", "T");
    const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, options);
  }
  function escapeHtml(value = "") {
    return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }
  function registerView(name, lifecycle) { views.set(name, lifecycle); }
  async function enterView(name) {
    if (currentView === name) return;
    views.get(currentView)?.leave?.();
    currentView = name;
    await views.get(name)?.enter?.();
  }
  root.CvUi = { request, formatError, formatDate, escapeHtml, registerView, enterView };
  if (typeof module !== "undefined") module.exports = root.CvUi;
})(typeof window !== "undefined" ? window : globalThis);
