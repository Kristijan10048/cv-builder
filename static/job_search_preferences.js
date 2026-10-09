let savedSearchPreferences = [];
let searchPreferencesLoaded = false;
let searchPreferenceBusy = false;
const searchPreferenceLocations = new SearchPreferenceLocationFields()

function updateSearchPreferenceCount() {
  const count = savedSearchPreferences.length;
  if (searchPreferencesLoaded) $("#searchPreferenceCount").textContent = `${count} of 10 searches saved${count === 10 ? ". Edit or delete a search to add another." : ""}`;
  $("#addSearchPreference").disabled = !searchPreferencesLoaded || count >= 10 || searchPreferenceBusy;
}

function renderSearchPreferences() {
  updateSearchPreferenceCount();
  $("#searchPreferenceList").innerHTML = savedSearchPreferences.length
    ? savedSearchPreferences.map(item => {
      const location = [item.city, item.country].filter(Boolean).join(", ") || "Any location";
      const age = item.posted_within_days ? `Last ${item.posted_within_days} day${item.posted_within_days === 1 ? "" : "s"}` : "Any time";
      return `<article class="panel preference-card">
        <div class="preference-card-heading"><h3>${escapeHtml(item.job_title)}</h3>
          <div class="preference-card-actions">
            <button class="secondary" type="button" data-preference-edit="${item.id}" aria-label="Edit ${escapeHtml(item.job_title)}">Edit</button>
            <button class="text-button" type="button" data-preference-delete="${item.id}" aria-label="Delete ${escapeHtml(item.job_title)}">Delete</button>
          </div>
        </div>
        <dl class="preference-details">
          <div><dt>Location</dt><dd>${escapeHtml(location)}</dd></div>
          <div><dt>City radius</dt><dd>${item.city ? `${item.radius_km} km` : "Any distance"}</dd></div>
          <div><dt>Dates posted</dt><dd>${escapeHtml(age)}</dd></div>
          <div><dt>Description keywords</dt><dd>${escapeHtml(item.keywords.join(", ") || "Any description")}</dd></div>
        </dl>
      </article>`;
    }).join("")
    : `<div class="panel empty-state"><strong>No saved searches yet</strong>Add a search for a role such as Software Developer or Second Level Support.</div>`;
}

async function loadJobSearchPreferences() {
  if (searchPreferenceBusy) return;
  setSearchPreferenceBusy(true);
  $("#searchPreferenceLoadError").classList.add("hidden");
  $("#searchPreferenceCount").textContent = "Loading saved searches...";
  $("#addSearchPreference").disabled = true;
  try {
    savedSearchPreferences = await api("/api/job-search-preferences");
    searchPreferencesLoaded = true;
    renderSearchPreferences();
  } catch (error) {
    searchPreferencesLoaded = false;
    $("#searchPreferenceCount").textContent = "Saved searches could not be loaded.";
    $("#searchPreferenceList").innerHTML = "";
    $("#searchPreferenceLoadErrorMessage").textContent = error.message;
    $("#searchPreferenceLoadError").classList.remove("hidden");
  } finally {
    setSearchPreferenceBusy(false);
  }
}

function openSearchPreferenceEditor(item = null) {
  if (searchPreferenceBusy || !searchPreferencesLoaded) return;
  if (!item && savedSearchPreferences.length >= 10) return;
  $("#searchPreferenceForm").reset();
  $("#searchPreferenceId").value = item?.id || "";
  $("#searchPreferenceTitle").value = item?.job_title || "";
  searchPreferenceLocations.load(item?.country || '', item?.city || '')
  $("#searchPreferenceRadius").value = item?.radius_km || 0;
  $("#searchPreferenceKeywords").value = item?.keywords.join(", ") || "";
  const age = item?.posted_within_days ? String(item.posted_within_days) : "";
  const ageSelect = $("#searchPreferenceAge");
  // Preserve valid custom posting ages saved through the API.
  ageSelect.querySelectorAll("[data-custom-age]").forEach(option => option.remove());
  if (age && ![...ageSelect.options].some(option => option.value === age)) {
    const option = new Option(`Last ${age} days`, age);
    option.dataset.customAge = "true";
    ageSelect.add(option);
  }
  ageSelect.value = age;
  $("#searchPreferenceFormHeading").textContent = item ? "Edit job search" : "New job search";
  $("#searchPreferenceFormError").classList.add("hidden");
  $("#searchPreferenceForm").classList.remove("hidden");
  $("#searchPreferenceTitle").focus();
}

function closeSearchPreferenceEditor() {
  searchPreferenceLocations.close()
  $("#searchPreferenceForm").classList.add("hidden");
  $("#searchPreferenceForm").reset();
  $("#searchPreferenceId").value = "";
  $("#addSearchPreference").focus();
}

function setSearchPreferenceBusy(busy) {
  searchPreferenceBusy = busy;
  $("#searchPreferenceFields").disabled = busy;
  searchPreferenceLocations.updateDisabled()
  $$("[data-preference-edit], [data-preference-delete]").forEach(button => button.disabled = busy || !searchPreferencesLoaded);
  updateSearchPreferenceCount();
}

$("#addSearchPreference").addEventListener("click", () => openSearchPreferenceEditor());
$("#cancelSearchPreference").addEventListener("click", closeSearchPreferenceEditor);
$("#retrySearchPreferences").addEventListener("click", loadJobSearchPreferences);
$("#searchPreferenceForm").addEventListener("submit", async event => {
  event.preventDefault();
  if (searchPreferenceBusy || searchPreferenceLocations.loading) return
  const id = $("#searchPreferenceId").value;
  const payload = {
    job_title: $("#searchPreferenceTitle").value.trim(),
    country: $("#searchPreferenceCountry").value.trim(),
    city: searchPreferenceLocations.cityValue(),
    radius_km: Number($("#searchPreferenceRadius").value),
    keywords: $("#searchPreferenceKeywords").value.split(",").map(value => value.trim()).filter(Boolean),
    posted_within_days: $("#searchPreferenceAge").value ? Number($("#searchPreferenceAge").value) : null,
  };
  const errorBox = $("#searchPreferenceFormError");
  errorBox.classList.add("hidden");
  if (payload.radius_km > 0 && !payload.city) {
    errorBox.textContent = 'Choose a city when using a search radius.'
    errorBox.classList.remove("hidden");
    $("#searchPreferenceCity").focus();
    return;
  }
  setSearchPreferenceBusy(true);
  try {
    const saved = await api(`/api/job-search-preferences${id ? `/${id}` : ""}`, {
      method: id ? "PUT" : "POST", body: JSON.stringify(payload),
    });
    savedSearchPreferences = id
      ? savedSearchPreferences.map(item => item.id === saved.id ? saved : item)
      : [...savedSearchPreferences, saved];
    renderSearchPreferences();
    searchPreferenceLocations.close()
    $("#searchPreferenceForm").classList.add("hidden");
    $("#searchPreferenceForm").reset();
    $("#searchPreferenceId").value = "";
    toast("Job search saved");
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  } finally {
    setSearchPreferenceBusy(false);
    if ($("#searchPreferenceForm").classList.contains("hidden")) {
      const editButton = $("#searchPreferenceList [data-preference-edit]");
      if (!$("#addSearchPreference").disabled) $("#addSearchPreference").focus();
      else editButton?.focus();
    }
  }
});

$("#searchPreferenceList").addEventListener("click", async event => {
  if (searchPreferenceBusy) return;
  const edit = event.target.closest("[data-preference-edit]");
  if (edit) {
    openSearchPreferenceEditor(savedSearchPreferences.find(item => item.id === Number(edit.dataset.preferenceEdit)));
    return;
  }
  const remove = event.target.closest("[data-preference-delete]");
  if (!remove) return;
  const id = Number(remove.dataset.preferenceDelete);
  const item = savedSearchPreferences.find(item => item.id === id);
  if (!confirm(`Delete the saved search for "${item.job_title}"?`)) return;
  setSearchPreferenceBusy(true);
  try {
    await api(`/api/job-search-preferences/${id}`, { method: "DELETE" });
    savedSearchPreferences = savedSearchPreferences.filter(item => item.id !== id);
    if (Number($("#searchPreferenceId").value) === id) closeSearchPreferenceEditor();
    renderSearchPreferences();
    toast("Job search deleted");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setSearchPreferenceBusy(false);
  }
});
