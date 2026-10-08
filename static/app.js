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
    try {
      const detail = (await response.json()).detail;
      message = Array.isArray(detail)
        ? detail.map(item => `${item.loc?.slice(1).join(" ") || "Search"}: ${item.msg}`).join("; ")
        : detail || message;
    } catch (_) {}
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
  templates: "Base documents", profile: "Profile", settings: "Settings",
  availableJobs: "Available Jobs", jobSearchPreferences: "Job Search Preferences"
};

async function showView(name) {
  $$(".view").forEach(view => view.classList.remove("active"));
  $(`#${name}View`).classList.add("active");
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === name));
  $("#pageTitle").textContent = titles[name];
  closeMenu();
  if (name === "dashboard") await loadOverview();
  if (name === "applications") await loadApplications();
  if (name === "availableJobs") await loadAvailableJobs();
  if (name === "jobSearchPreferences") await loadJobSearchPreferences();
  if (name === "templates") await loadTemplates();
  if (name === "profile") await loadProfile();
  if (name === "settings") await loadSettings();
}

function rowMarkup(item) {
  const initial = (item.company || "?").trim().slice(0, 1);
  const date = formatUtcDateTime(item.updated_at, { month: "short", day: "numeric", year: "numeric" });
  return `<article class="application-row" data-application-id="${item.id}" tabindex="0">
    <span class="company-avatar">${escapeHtml(initial)}</span>
    <div><strong>${escapeHtml(item.job_title)}</strong><small>${escapeHtml(item.company)}</small></div>
    <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
    <small class="row-date">${date}</small><span>›</span>
  </article>`;
}

function formatUtcDateTime(value, options = { dateStyle: "medium", timeStyle: "short" }) {
  if (!value) return "Not recorded";
  const date = new Date(`${value.replace(" ", "T")}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, options);
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url : null;
  } catch (_) {
    return null;
  }
}

function applicationTableMarkup(item) {
  const source = safeExternalUrl(item.source_url);
  const sourceMarkup = source
    ? `<a href="${escapeHtml(source.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.hostname.replace(/^www\./, ""))}</a>`
    : `<span class="table-empty-value">Not available</span>`;
  return `<tr class="application-table-row" data-application-id="${item.id}" tabindex="0">
    <td data-label="Company"><strong>${escapeHtml(item.company)}</strong></td>
    <td data-label="Role">${escapeHtml(item.job_title)}</td>
    <td data-label="Job page">${sourceMarkup}</td>
    <td data-label="Applied on"><time>${escapeHtml(formatUtcDateTime(item.created_at))}</time></td>
    <td data-label="Status"><span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td>
    <td class="table-open" aria-hidden="true">›</td>
  </tr>`;
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
  $("#applicationList").innerHTML = rows.length
    ? rows.map(applicationTableMarkup).join("")
    : `<tr><td colspan="6">${emptyMarkup}</td></tr>`;
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
  nationality: "#profileNationality", date_of_birth: "#profileDateOfBirth",
  linkedin_url: "#profileLinkedinUrl", website_url: "#profileWebsiteUrl",
  current_company: "#profileCurrentCompany", current_job_title: "#profileCurrentJobTitle",
  work_authorization: "#profileWorkAuthorization", notice_period: "#profileNoticePeriod",
  salary_expectation: "#profileSalaryExpectation",
  strongest_programming_language: "#profileStrongestProgrammingLanguage",
  german_language_level: "#profileGermanLanguageLevel",
  english_language_level: "#profileEnglishLanguageLevel",
  onsite_availability: "#profileOnsiteAvailability",
  travel_willingness: "#profileTravelWillingness",
};

const profileSections = [
  ["Contact", [
    ["Email", "email"], ["Phone", "phone"], ["LinkedIn Profile", "linkedin_url"],
    ["Website / portfolio", "website_url"],
  ]],
  ["Address", [
    ["Address line 1", "address_line1"], ["Address line 2", "address_line2"],
    ["Postal code", "postal_code"], ["City", "city"],
    ["State / region", "state_region"], ["Country", "country"],
    ["Nationality", "nationality"],
  ]],
  ["Work", [
    ["Current company", "current_company"], ["Current job title", "current_job_title"],
    ["Work authorization", "work_authorization"], ["Notice period", "notice_period"],
    ["Salary expectation", "salary_expectation"],
    ["Strongest programming language", "strongest_programming_language"],
    ["Date of birth", "date_of_birth"],
    ["German language level", "german_language_level"],
    ["English language level", "english_language_level"],
    ["50% on-site availability", "onsite_availability"],
    ["Willing to travel", "travel_willingness"],
  ]],
];

let savedProfile = {};

function hasSavedProfile(profile) {
  return Object.values(profile).some(value => String(value || "").trim());
}

function profileValueMarkup(label, key, value) {
  const safeValue = escapeHtml(value || "Not provided");
  const isLink = ["linkedin_url", "website_url"].includes(key) && value;
  const content = isLink
    ? `<a href="${escapeHtml(value)}" target="_blank" rel="noopener noreferrer">${safeValue}</a>`
    : safeValue;
  return `<div class="profile-detail${value ? "" : " is-empty"}"><dt>${escapeHtml(label)}</dt><dd>${content}</dd></div>`;
}

function renderProfile(profile) {
  savedProfile = profile;
  const hasProfile = hasSavedProfile(profile);
  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(" ");
  const role = [profile.current_job_title, profile.current_company].filter(Boolean).join(" at ");
  const initials = [profile.first_name, profile.last_name]
    .filter(Boolean).map(value => value.trim().charAt(0)).join("").slice(0, 2).toUpperCase();

  $("#profileDisplayName").textContent = fullName || "Your profile";
  $("#profileDisplayRole").textContent = role || profile.email || "Personal details saved locally";
  $("#profileAvatar").textContent = initials || "👤";
  $("#profileEmpty").classList.toggle("hidden", hasProfile);
  $("#profileDetails").classList.toggle("hidden", !hasProfile);
  $("#editProfileButton").textContent = hasProfile ? "Edit profile" : "Add details";
  $("#profileDetails").innerHTML = profileSections.map(([heading, fields]) => `
    <section class="profile-detail-group">
      <h4>${heading}</h4>
      <dl>${fields.map(([label, key]) => profileValueMarkup(label, key, profile[key])).join("")}</dl>
    </section>`).join("");
}

function fillProfileForm(profile) {
  Object.entries(profileFields).forEach(([key, selector]) => {
    $(selector).value = profile[key] || "";
  });
}

async function loadProfile() {
  const profile = await api("/api/personal-details");
  renderProfile(profile);
  fillProfileForm(profile);
  closeProfileEditor();
}

async function loadSettings() {
  const settings = await api("/api/settings");
  $("#lmStudioUrl").value = settings.lm_studio_url;
  $("#lmStudioModel").value = settings.lm_studio_model;
}

function openProfileEditor() {
  fillProfileForm(savedProfile);
  $("#profileSummary").classList.add("hidden");
  $("#personalDetailsForm").classList.remove("hidden");
  $("#editProfileButton").classList.add("hidden");
  $("#profileFirstName").focus();
}

function closeProfileEditor() {
  $("#personalDetailsForm").classList.add("hidden");
  $("#profileSummary").classList.remove("hidden");
  $("#editProfileButton").classList.remove("hidden");
}

$("#personalDetailsForm").addEventListener("submit", async event => {
  event.preventDefault();
  const payload = Object.fromEntries(
    Object.entries(profileFields).map(([key, selector]) => [key, $(selector).value.trim()])
  );
  try {
    const profile = await api("/api/personal-details", { method: "PUT", body: JSON.stringify(payload) });
    renderProfile(profile);
    closeProfileEditor();
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
  const actionButton = event.target.closest("[data-action]");
  if (actionButton?.dataset.action === "new") { resetApplication(); showView("editor"); }
  if (actionButton?.dataset.action === "edit-profile") openProfileEditor();
  if (actionButton?.dataset.action === "cancel-profile-edit") {
    fillProfileForm(savedProfile);
    closeProfileEditor();
  }
  const row = event.target.closest("[data-application-id]");
  if (row && !event.target.closest("a, button")) openApplication(row.dataset.applicationId);
});
document.addEventListener("keydown", event => {
  const row = event.target.closest("[data-application-id]");
  if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openApplication(row.dataset.applicationId); }
});
let searchTimer;
$("#searchInput").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadApplications, 250); });
$("#statusFilter").addEventListener("change", loadApplications);

const sidebarToggle = $("#sidebarToggle");
const mobileLayout = window.matchMedia("(max-width: 900px)");
let sidebarCollapsed = false;
try { sidebarCollapsed = localStorage.getItem("applykit.sidebarCollapsed") === "true"; }
catch { /* Navigation still works when browser storage is unavailable. */ }

function updateSidebar() {
  $(".app-shell").classList.toggle("sidebar-collapsed", sidebarCollapsed);
  const expanded = mobileLayout.matches || !sidebarCollapsed;
  const label = expanded ? "Collapse menu" : "Expand menu";
  sidebarToggle.setAttribute("aria-expanded", String(expanded));
  sidebarToggle.setAttribute("aria-label", label);
  sidebarToggle.title = label;
}
sidebarToggle.addEventListener("click", () => {
  sidebarCollapsed = !sidebarCollapsed;
  updateSidebar();
  try { localStorage.setItem("applykit.sidebarCollapsed", String(sidebarCollapsed)); }
  catch { /* Keep the current session's choice without persistent storage. */ }
});
mobileLayout.addEventListener("change", () => { closeMenu(); updateSidebar(); });
updateSidebar();

function openMenu(){ $("#sidebar").classList.add("open"); $("#mobileOverlay").classList.add("visible"); }
function closeMenu(){ $("#sidebar").classList.remove("open"); $("#mobileOverlay").classList.remove("visible"); }
$("#menuButton").addEventListener("click", openMenu);
$("#mobileOverlay").addEventListener("click", closeMenu);
function escapeHtml(value = "") { const div = document.createElement("div"); div.textContent = value; return div.innerHTML.replaceAll('"', "&quot;"); }

loadOverview().catch(error => toast(error.message, true));
