let jobsPage = 1;
let jobsRequest = 0;
let fetchingJobs = false;
let jobsSearchTimer;
const boardNames = { linkedin: "LinkedIn", indeed: "Indeed", glassdoor: "Glassdoor", zip_recruiter: "ZipRecruiter", bayt: "Bayt", bdjobs: "BDJobs", naukri: "Naukri" };

// Keep widths on columns, so replacing result rows never resets a user's sizing.
function enableJobColumnResizing() {
  const table = $(".available-jobs-table");
  const headers = Array.from(table.querySelectorAll("thead th"));
  const columns = document.createElement("colgroup");
  const columnElements = headers.map(() => document.createElement("col"));
  columns.append(...columnElements);
  table.querySelector("thead").before(columns);
  const minWidth = 110;
  const container = table.closest(".application-table-wrap");
  let widths;
  let preferredWidths;
  let drag;

  function visibleColumnIndices() {
    const previewOpen = table.closest(".available-jobs-workspace").classList.contains("preview-open");
    return headers.flatMap((header, index) =>
      previewOpen && header.classList.contains("job-secondary-column") ? [] : [index]);
  }
  function applyWidths() {
    const visibleIndices = visibleColumnIndices();
    // Keep the colgroup aligned with visible cells; hidden columns must take no space.
    columns.replaceChildren(...visibleIndices.map(index => columnElements[index]));
    widths.forEach((width, index) => { columnElements[index].style.width = `${width}px`; });
    table.style.width = `${Math.max(container.clientWidth, visibleIndices.length * minWidth)}px`;
    table.classList.add("columns-resized");
  }
  function initializeWidths() {
    if (!widths) {
      widths = headers.map(header => Math.max(minWidth, header.getBoundingClientRect().width));
    }
    fitAvailableSpace();
  }
  function fitAvailableSpace() {
    if (!container.clientWidth || window.matchMedia("(max-width: 700px)").matches) return;
    if (!widths) widths = headers.map(header => Math.max(minWidth, header.getBoundingClientRect().width));
    const visibleIndices = visibleColumnIndices();
    const total = Math.max(container.clientWidth, visibleIndices.length * minWidth);
    const spare = total - visibleIndices.length * minWidth;
    // Retain proportions even when the split makes every column hit its minimum.
    if (!preferredWidths) preferredWidths = [...widths];
    const weights = visibleIndices.map(index => Math.max(0, preferredWidths[index] - minWidth));
    const sum = weights.reduce((a, b) => a + b, 0);
    visibleIndices.forEach((index, position) => {
      widths[index] = minWidth + spare * (sum ? weights[position] / sum : 1 / visibleIndices.length);
    });
    applyWidths();
  }
  function resizeColumn(index, requestedWidth, original = widths) {
    const visibleIndices = visibleColumnIndices();
    const otherIndices = visibleIndices.filter(columnIndex => columnIndex !== index);
    const total = visibleIndices.reduce((sum, columnIndex) => sum + original[columnIndex], 0);
    const selected = Math.min(total - minWidth * otherIndices.length, Math.max(minWidth, requestedWidth));
    const remainingSpare = total - selected - minWidth * otherIndices.length;
    const otherSpare = otherIndices.reduce((sum, columnIndex) => sum + Math.max(0, original[columnIndex] - minWidth), 0);
    widths = [...original];
    widths[index] = selected;
    otherIndices.forEach(columnIndex => {
      widths[columnIndex] = minWidth + remainingSpare * (otherSpare ? Math.max(0, original[columnIndex] - minWidth) / otherSpare : 1 / otherIndices.length);
    });
    preferredWidths = [...widths];
    applyWidths();
  }
  function finishDrag() {
    if (!drag) return;
    const { handle, pointerId } = drag;
    drag = null;
    document.body.classList.remove("resizing-job-column");
    if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
  }

  headers.forEach((header, index) => {
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = "column-resize-handle";
    const label = `Resize ${header.textContent.trim()} column`;
    handle.setAttribute("aria-label", label);
    handle.title = `${label}. Drag or use Left and Right arrow keys.`;
    header.append(handle);
    handle.addEventListener("pointerdown", event => {
      if (event.button !== 0 || window.matchMedia("(max-width: 700px)").matches) return;
      event.preventDefault();
      initializeWidths();
      handle.focus();
      drag = { handle, pointerId: event.pointerId, startX: event.clientX, original: [...widths] };
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add("resizing-job-column");
    });
    handle.addEventListener("pointermove", event => {
      if (!drag || drag.handle !== handle || drag.pointerId !== event.pointerId) return;
      resizeColumn(index, drag.original[index] + event.clientX - drag.startX, drag.original);
    });
    handle.addEventListener("pointerup", finishDrag);
    handle.addEventListener("pointercancel", finishDrag);
    handle.addEventListener("lostpointercapture", finishDrag);
    handle.addEventListener("keydown", event => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      initializeWidths();
      resizeColumn(index, widths[index] + (event.key === "ArrowRight" ? 10 : -10));
    });
  });
  window.addEventListener("blur", finishDrag);
  window.addEventListener("resize", finishDrag);
  let lastContainerWidth;
  new ResizeObserver(() => {
    if (container.clientWidth === lastContainerWidth) return;
    lastContainerWidth = container.clientWidth;
    finishDrag();
    fitAvailableSpace();
  }).observe(container);
  return {
    capture() {
      finishDrag();
      initializeWidths();
      return { widths: widths && [...widths], preferredWidths: preferredWidths && [...preferredWidths] };
    },
    restore(snapshot) {
      finishDrag();
      widths = snapshot.widths && [...snapshot.widths];
      preferredWidths = snapshot.preferredWidths && [...snapshot.preferredWidths];
      fitAvailableSpace();
    },
  };
}
const jobColumnSizing = enableJobColumnResizing();
const jobDescriptionPreview = new window.JobDescriptionPreview($("#availableJobsView"), jobColumnSizing);
window.CvUi.registerView("availableJobs", {
  leave: () => jobDescriptionPreview.close({ restoreFocus: false, restoreScroll: false }),
});

function updateFetchButton() {
  $("#fetchJobsButton").disabled = fetchingJobs || !$("#jobSearchPreference").value || !$("input[name='jobBoard']:checked");
}

/** Refresh saved profile options without resetting a valid selection or fetch settings. */
function refreshJobSearchProfiles(preferences) {
  const select = $("#jobSearchPreference");
  const selected = select.value;
  select.innerHTML = '<option value="">All fetched jobs</option>' + preferences.map(item =>
    `<option value="${item.id}">${escapeHtml([item.job_title, item.city, item.country].filter(Boolean).join(" · "))}</option>`
  ).join("");
  select.value = preferences.some(item => String(item.id) === selected) ? selected : "";
  const selectionChanged = select.value !== selected;
  if (selectionChanged) jobsPage = 1;
  updateFetchButton();
  return selectionChanged;
}

async function loadAvailableJobs() {
  try {
    const preferences = await api("/api/job-search-preferences");
    refreshJobSearchProfiles(preferences);
    await loadJobsPage();
  } catch (error) { toast(error.message, true); }
}

function availableJobMarkup(item) {
  const languageRequirements = (item.language_requirements || []).join(', ')
  const languageMarkup = languageRequirements ? escapeHtml(languageRequirements) : '<span class="table-empty-value">Not specified</span>'
  const source = safeExternalUrl(item.job_url);
  const link = source ? `<a href="${escapeHtml(source.href)}" target="_blank" rel="noopener noreferrer">View job &#8599;</a>` : '<span class="table-empty-value">Unavailable</span>';
  return `<tr class="application-table-row available-job-row">
    <td data-label="Company"><strong>${escapeHtml(item.company || "Not listed")}</strong></td>
    <td data-label="Title"><button type="button" class="job-title-button" data-job-id="${escapeHtml(item.id)}" aria-controls="jobDescriptionPreview" aria-expanded="false">${escapeHtml(item.job_title)}</button></td>
    <td data-label="Location">${escapeHtml(item.location || (item.is_remote ? "Remote" : "Not listed"))}</td>
    <td data-label="Language" class="job-secondary-column">${languageMarkup}</td>
    <td data-label="Source" class="job-secondary-column">${escapeHtml(boardNames[item.site] || item.site)}</td>
    <td data-label="Date Fetched" class="job-secondary-column"><time>${escapeHtml(formatUtcDateTime(item.fetched_at))}</time></td>
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
      '<tr><td colspan="8"><div class="empty-state"><strong>No matching jobs</strong>Fetch jobs for a saved search or adjust your filters.</div></td></tr>'
    $("#availableJobsNote").textContent = data.total ? `${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total} fetched jobs` : "No matching fetched jobs.";
    jobDescriptionPreview.setItems(data.items);
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
