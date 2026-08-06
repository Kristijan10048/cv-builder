const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
let rawHtml = "";
let importedData = "";
let toastTimer;

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = "Something went wrong.";
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
};

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.className = "toast", 3200);
}

const titles = {
  dashboard: "Overview", editor: "Application builder", applications: "Applications",
  templates: "Base documents", settings: "Settings"
};

async function showView(name) {
  $$(".view").forEach(view => view.classList.remove("active"));
  $(`#${name}View`).classList.add("active");
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === name));
  $("#pageTitle").textContent = titles[name];
  closeMenu();
  if (name === "dashboard") await loadOverview();
  if (name === "applications") await loadApplications();
  if (name === "templates") await loadTemplates();
  if (name === "settings") await loadSettings();
}

function rowMarkup(item) {
  const initial = (item.company || "?").trim().slice(0, 1);
  const date = new Date(`${item.updated_at.replace(" ", "T")}Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  return `<article class="application-row" data-id="${item.id}" tabindex="0">
    <span class="company-avatar">${escapeHtml(initial)}</span>
    <div><strong>${escapeHtml(item.job_title)}</strong><small>${escapeHtml(item.company)}</small></div>
    <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
    <small class="row-date">${date}</small><span>›</span>
  </article>`;
}

const emptyMarkup = `<div class="empty-state"><strong>No applications yet</strong>Add a role to start building your pipeline.</div>`;

async function loadOverview() {
  const data = await api("/api/overview");
  $("#metricTotal").textContent = data.total;
  $("#metricDraft").textContent = data.by_status.Draft || 0;
  $("#metricActive").textContent = ["Ready","Applied","Interview","Offer"].reduce((sum, key) => sum + (data.by_status[key] || 0), 0);
  $("#recentList").innerHTML = data.recent.length ? data.recent.map(rowMarkup).join("") : emptyMarkup;
}

async function loadApplications() {
  const params = new URLSearchParams({ search: $("#searchInput").value, status: $("#statusFilter").value });
  const rows = await api(`/api/applications?${params}`);
  $("#applicationList").innerHTML = rows.length ? rows.map(rowMarkup).join("") : emptyMarkup;
}

function resetApplication() {
  $("#applicationForm").reset();
  $("#applicationId").value = "";
  $("#status").value = "Draft";
  $("#editorHeading").textContent = "Create a focused application";
  $("#deleteButton").classList.add("hidden");
  rawHtml = ""; importedData = "";
}

async function openApplication(id) {
  const item = await api(`/api/applications/${id}`);
  $("#applicationId").value = item.id;
  $("#company").value = item.company;
  $("#jobTitle").value = item.job_title;
  $("#sourceUrl").value = item.source_url;
  $("#jobDescription").value = item.job_description;
  $("#adjustedCv").value = item.adjusted_cv;
  $("#adjustedCoverLetter").value = item.adjusted_cover_letter;
  $("#status").value = item.status;
  $("#notes").value = item.notes;
  rawHtml = item.raw_html; importedData = item.imported_data;
  $("#editorHeading").textContent = `${item.job_title} · ${item.company}`;
  $("#deleteButton").classList.remove("hidden");
  await showView("editor");
}

function applicationPayload() {
  return {
    company: $("#company").value.trim(), job_title: $("#jobTitle").value.trim(),
    source_url: $("#sourceUrl").value.trim(), job_description: $("#jobDescription").value,
    adjusted_cv: $("#adjustedCv").value, adjusted_cover_letter: $("#adjustedCoverLetter").value,
    status: $("#status").value, notes: $("#notes").value, raw_html: rawHtml,
    imported_data: importedData,
  };
}

$("#applicationForm").addEventListener("submit", async event => {
  event.preventDefault();
  const id = $("#applicationId").value;
  try {
    const saved = await api(id ? `/api/applications/${id}` : "/api/applications", {
      method: id ? "PUT" : "POST", body: JSON.stringify(applicationPayload())
    });
    $("#applicationId").value = saved.id;
    $("#deleteButton").classList.remove("hidden");
    $("#editorHeading").textContent = `${saved.job_title} · ${saved.company}`;
    toast("Application saved");
  } catch (error) { toast(error.message, true); }
});

$("#deleteButton").addEventListener("click", async () => {
  const id = $("#applicationId").value;
  if (!id || !confirm("Delete this application? This cannot be undone.")) return;
  try { await api(`/api/applications/${id}`, { method: "DELETE" }); toast("Application deleted"); await showView("applications"); }
  catch (error) { toast(error.message, true); }
});

$("#importButton").addEventListener("click", async () => {
  const url = $("#sourceUrl").value.trim();
  if (!url) return toast("Add a public job page URL first.", true);
  $("#importButton").disabled = true; $("#importButton").textContent = "Importing…";
  try {
    const result = await api("/api/import", { method: "POST", body: JSON.stringify({ url }) });
    if (!$("#jobTitle").value) $("#jobTitle").value = result.job_title;
    if (!$("#company").value) $("#company").value = result.company;
    $("#jobDescription").value = result.job_description || $("#jobDescription").value;
    rawHtml = result.raw_html; importedData = result.imported_data;
    toast("Job page imported");
  } catch (error) { toast(error.message, true); }
  finally { $("#importButton").disabled = false; $("#importButton").textContent = "Import"; }
});

$$("[data-generate]").forEach(button => button.addEventListener("click", async () => {
  const id = $("#applicationId").value;
  if (!id) return toast("Save the application before drafting with LM Studio.", true);
  const document = button.dataset.generate;
  const target = document === "cv" ? $("#adjustedCv") : $("#adjustedCoverLetter");
  const instructions = document === "cv" ? $("#cvInstructions").value : $("#coverInstructions").value;
  const original = button.textContent; button.disabled = true; button.textContent = "Drafting…";
  try {
    const result = await api("/api/generate", { method: "POST", body: JSON.stringify({ application_id: Number(id), document, instructions }) });
    target.value = result.content; toast(`Draft created with ${result.model}`);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = original; }
}));

async function loadTemplates() {
  const data = await api("/api/templates");
  renderCurrentFile("#currentCvFile", data.cv.filename, "No CV uploaded");
  renderCurrentFile("#currentCoverLetterFile", data.cover_letter.filename, "No cover letter uploaded");
}
$("#templateForm").addEventListener("submit", async event => {
  event.preventDefault();
  const cv = $("#templateCvFile").files[0];
  const coverLetter = $("#templateCoverLetterFile").files[0];
  if (!cv && !coverLetter) return toast("Select at least one .tex file.", true);
  const formData = new FormData();
  if (cv) formData.append("cv", cv);
  if (coverLetter) formData.append("cover_letter", coverLetter);
  const submit = event.submitter;
  if (submit) { submit.disabled = true; submit.textContent = "Uploading…"; }
  try {
    const response = await fetch("/api/templates/upload", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Upload failed.");
    renderCurrentFile("#currentCvFile", result.cv.filename, "No CV uploaded");
    renderCurrentFile("#currentCoverLetterFile", result.cover_letter.filename, "No cover letter uploaded");
    $("#templateForm").reset();
    $$(".file-drop").forEach(drop => drop.classList.remove("has-file"));
    toast("LaTeX files uploaded");
  } catch (error) { toast(error.message, true); }
  finally { if (submit) { submit.disabled = false; submit.textContent = "Upload selected files"; } }
});

function renderCurrentFile(selector, filename, fallback) {
  const element = $(selector);
  element.innerHTML = `<span>TEX</span><small>${escapeHtml(filename || fallback)}</small>`;
}

$$(".file-drop input").forEach(input => input.addEventListener("change", () => {
  const drop = input.closest(".file-drop");
  drop.classList.toggle("has-file", Boolean(input.files.length));
  const strong = drop.querySelector("strong");
  strong.textContent = input.files[0]?.name || "Choose a .tex file";
}));

const profileFields = {
  first_name: "#profileFirstName", last_name: "#profileLastName",
  email: "#profileEmail", phone: "#profilePhone",
  address_line1: "#profileAddressLine1", address_line2: "#profileAddressLine2",
  postal_code: "#profilePostalCode", city: "#profileCity",
  state_region: "#profileStateRegion", country: "#profileCountry",
  linkedin_url: "#profileLinkedinUrl", website_url: "#profileWebsiteUrl",
  current_company: "#profileCurrentCompany", current_job_title: "#profileCurrentJobTitle",
  work_authorization: "#profileWorkAuthorization", notice_period: "#profileNoticePeriod",
  salary_expectation: "#profileSalaryExpectation",
};

async function loadSettings() {
  const [settings, profile] = await Promise.all([
    api("/api/settings"), api("/api/personal-details")
  ]);
  $("#lmStudioUrl").value = settings.lm_studio_url;
  $("#lmStudioModel").value = settings.lm_studio_model;
  Object.entries(profileFields).forEach(([key, selector]) => {
    $(selector).value = profile[key] || "";
  });
}
$("#personalDetailsForm").addEventListener("submit", async event => {
  event.preventDefault();
  const payload = Object.fromEntries(
    Object.entries(profileFields).map(([key, selector]) => [key, $(selector).value.trim()])
  );
  try {
    await api("/api/personal-details", { method: "PUT", body: JSON.stringify(payload) });
    toast("Personal details saved");
  } catch (error) { toast(error.message, true); }
});
$("#settingsForm").addEventListener("submit", async event => {
  event.preventDefault();
  try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ lm_studio_url: $("#lmStudioUrl").value, lm_studio_model: $("#lmStudioModel").value }) }); toast("Settings saved"); }
  catch (error) { toast(error.message, true); }
});
$("#testConnection").addEventListener("click", async () => {
  const state = $("#connectionState"); state.className = ""; state.textContent = "Testing…";
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ lm_studio_url: $("#lmStudioUrl").value, lm_studio_model: $("#lmStudioModel").value }) });
    const data = await api("/api/lm-studio/models");
    state.className = "success"; state.textContent = `Connected · ${data.data?.length || 0} model(s) available`;
  } catch (error) { state.className = "error"; state.textContent = error.message; }
});

$$("[data-document]").forEach(button => button.addEventListener("click", () => {
  $$("[data-document]").forEach(item => item.classList.remove("active"));
  $$(".document-pane").forEach(item => item.classList.remove("active"));
  button.classList.add("active");
  $(`#${button.dataset.document === "cv" ? "cv" : "coverLetter"}Pane`).classList.add("active");
}));

document.addEventListener("click", event => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) { event.preventDefault(); showView(viewButton.dataset.view); }
  if (event.target.closest("[data-action='new']")) { resetApplication(); showView("editor"); }
  const row = event.target.closest(".application-row");
  if (row) openApplication(row.dataset.id);
});
document.addEventListener("keydown", event => {
  const row = event.target.closest(".application-row");
  if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openApplication(row.dataset.id); }
});
let searchTimer;
$("#searchInput").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadApplications, 250); });
$("#statusFilter").addEventListener("change", loadApplications);

function openMenu(){ $("#sidebar").classList.add("open"); $("#mobileOverlay").classList.add("visible"); }
function closeMenu(){ $("#sidebar").classList.remove("open"); $("#mobileOverlay").classList.remove("visible"); }
$("#menuButton").addEventListener("click", openMenu);
$("#mobileOverlay").addEventListener("click", closeMenu);
function escapeHtml(value = "") { const div = document.createElement("div"); div.textContent = value; return div.innerHTML; }

loadOverview().catch(error => toast(error.message, true));
