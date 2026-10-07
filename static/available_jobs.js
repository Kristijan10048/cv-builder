let jobsPage = 1;
let jobsRequest = 0;
let fetchingJobs = false;
let jobsSearchTimer;
const boardNames = { linkedin: "LinkedIn", indeed: "Indeed", glassdoor: "Glassdoor", zip_recruiter: "ZipRecruiter", bayt: "Bayt", bdjobs: "BDJobs", naukri: "Naukri" };

function updateFetchButton() {
  $("#fetchJobsButton").disabled = fetchingJobs || !$("#jobSearchPreference").value || !$("input[name='jobBoard']:checked");
}

async function loadAvailableJobs() {
  try {
    const preferences = await api("/api/job-search-preferences");
    const select = $("#jobSearchPreference");
    const selected = select.value;
    select.innerHTML = '<option value="">All fetched jobs</option>' + preferences.map(item =>
      `<option value="${item.id}">${escapeHtml([item.job_title, item.city, item.country].filter(Boolean).join(" · "))}</option>`
    ).join("");
    select.value = preferences.some(item => String(item.id) === selected) ? selected : "";
    if (select.value !== selected) jobsPage = 1;
    updateFetchButton();
    await loadJobsPage();
  } catch (error) { toast(error.message, true); }
}

function availableJobMarkup(item) {
  const source = safeExternalUrl(item.job_url);
  const link = source ? `<a href="${escapeHtml(source.href)}" target="_blank" rel="noopener noreferrer">View job &#8599;</a>` : '<span class="table-empty-value">Unavailable</span>';
  return `<tr class="application-table-row available-job-row">
    <td data-label="Company"><strong>${escapeHtml(item.company || "Not listed")}</strong></td>
    <td data-label="Title">${escapeHtml(item.job_title)}</td>
    <td data-label="Location">${escapeHtml(item.location || (item.is_remote ? "Remote" : "Not listed"))}</td>
    <td data-label="Source">${escapeHtml(boardNames[item.site] || item.site)}</td>
    <td data-label="Date Fetched"><time>${escapeHtml(formatUtcDateTime(item.fetched_at))}</time></td>
    <td data-label="Job link">${link}</td>
    <td data-label="Applied"><span class="status-badge ${item.applied ? "status-Applied" : "status-Draft"}">${item.applied ? "Yes" : "No"}</span></td>
  </tr>`;
}

async function loadJobsPage(page = jobsPage) {
  const request = ++jobsRequest;
  $("#jobsPrevious").disabled = true;
  $("#jobsNext").disabled = true;
  $("#availableJobsList").setAttribute("aria-busy", "true");
  const params = new URLSearchParams({ page, page_size: $("#availableJobsPageSize").value, search: $("#availableJobsSearch").value });
  if ($("#jobSearchPreference").value) params.set("preference_id", $("#jobSearchPreference").value);
  if ($("#availableJobsSite").value) params.set("site", $("#availableJobsSite").value);
  try {
    const data = await api(`/api/available-jobs?${params}`);
    if (request !== jobsRequest) return;
    jobsPage = data.page;
    $("#availableJobsList").innerHTML = data.items.length ? data.items.map(availableJobMarkup).join("") :
      '<tr><td colspan="7"><div class="empty-state"><strong>No matching jobs</strong>Fetch jobs for a saved search or adjust your filters.</div></td></tr>';
    $("#availableJobsNote").textContent = data.total ? `${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total} fetched jobs` : "No matching fetched jobs.";
    $("#jobsPageLabel").textContent = `Page ${data.page} of ${data.total_pages}`;
    $("#jobsPrevious").disabled = !data.has_previous;
    $("#jobsNext").disabled = !data.has_next;
  } catch (error) {
    if (request === jobsRequest) {
      $("#availableJobsNote").textContent = "Could not load jobs. Adjust a filter or reopen Available Jobs to retry.";
      toast(error.message, true);
    }
  } finally {
    if (request === jobsRequest) $("#availableJobsList").setAttribute("aria-busy", "false");
  }
}

$("#jobSearchForm").addEventListener("submit", async event => {
  event.preventDefault();
  if (fetchingJobs) return;
  const preferenceId = Number($("#jobSearchPreference").value);
  const sites = $$("input[name='jobBoard']:checked").map(input => input.value);
  if (!preferenceId || !sites.length) return toast("Choose a saved search and at least one job board.", true);
  fetchingJobs = true;
  updateFetchButton();
  $("#fetchJobsButton").textContent = "Fetching jobs…";
  $("#jobSearchStatus").textContent = "Searching job boards. This can take a few minutes.";
  $("#jobSearchWarnings").classList.add("hidden");
  try {
    const response = await fetch("/api/job-search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preference_id: preferenceId, sites, results_wanted: Number($("#jobSearchLimit").value) }) });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : [detail?.message || "Could not fetch jobs.", ...(detail?.warnings || [])].join(" "));
    }
    $("#jobSearchStatus").textContent = `${data.fetched} jobs fetched. Previously fetched jobs remain available.`;
    $("#jobSearchWarnings").textContent = data.warnings.join(" ");
    $("#jobSearchWarnings").classList.toggle("hidden", !data.warnings.length);
    await loadJobsPage(1);
  } catch (error) {
    $("#jobSearchStatus").textContent = "Could not complete the search. Previously fetched jobs remain available.";
    $("#jobSearchWarnings").textContent = error.message;
    $("#jobSearchWarnings").classList.remove("hidden");
  } finally {
    fetchingJobs = false;
    $("#fetchJobsButton").textContent = "Fetch jobs";
    updateFetchButton();
  }
});

$("#jobSearchPreference").addEventListener("change", () => { updateFetchButton(); loadJobsPage(1); });
$$("input[name='jobBoard']").forEach(input => input.addEventListener("change", updateFetchButton));
$("#availableJobsSite").addEventListener("change", () => loadJobsPage(1));
$("#availableJobsPageSize").addEventListener("change", () => loadJobsPage(1));
$("#availableJobsSearch").addEventListener("input", () => { clearTimeout(jobsSearchTimer); jobsSearchTimer = setTimeout(() => loadJobsPage(1), 250); });
$("#jobsPrevious").addEventListener("click", () => loadJobsPage(jobsPage - 1));
$("#jobsNext").addEventListener("click", () => loadJobsPage(jobsPage + 1));
