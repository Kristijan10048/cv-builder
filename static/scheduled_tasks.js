/* Durable schedule management with visibility-scoped polling and retry-safe run-now keys. */
(function (root) {
  "use strict";
  const endpoint = "/api/task-schedules";
  const labels = { queued: "Queued", running: "Running", succeeded: "Succeeded", partial: "Partial success", failed: "Failed", cancelled: "Cancelled", missed: "Missed", interrupted: "Interrupted", skipped_overlap: "Skipped overlap" };
  function localInput(value) {
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19).replace(/:00$/, "");
  }
  function buildDefinition(values, original = null, now = Date.now()) {
    const name = values.name.trim();
    const results = Number(values.results);
    const seconds = Number(values.seconds);
    const date = new Date(values.start);
    if (!name || name.length > 120) throw new Error("Enter a name of 1–120 characters.");
    if (!values.preference || !values.sites.length) throw new Error("Choose a saved search and at least one board.");
    if (!Number.isInteger(results) || results < 1 || results > 1000) throw new Error("Choose 1–1,000 results per board.");
    if (!Number.isFinite(date.getTime())) throw new Error("Choose a valid first execution time.");
    const trigger = values.kind === "once" ? { kind: "once", run_at: date.toISOString() } : { kind: "interval", seconds, starts_at: date.toISOString() };
    if (trigger.kind === "interval" && (!Number.isInteger(seconds) || seconds < 300 || seconds > 31536000)) throw new Error("The interval must be 300–31,536,000 whole seconds.");
    // Preserve fractional UTC anchors when their displayed local input was not changed.
    const anchor = original && (original.trigger.starts_at || original.trigger.run_at);
    const unchanged = original && trigger.kind === original.trigger.kind && values.start === localInput(anchor) && (trigger.kind === "once" || seconds === original.trigger.seconds);
    if (!unchanged && date.getTime() <= now) throw new Error("Choose a first execution time in the future.");
    return { name, task_type: "fetch_jobs", payload_version: 1, payload: { preference_id: Number(values.preference), sites: [...values.sites], results_wanted: results }, trigger: unchanged ? { ...original.trigger } : trigger };
  }
  class RunRequests {
    constructor(makeKey) { this.makeKey = makeKey; this.pending = new Map(); this.busy = new Set(); }
    async send(schedule, request) {
      if (this.busy.has(schedule.id)) return null;
      if (!this.pending.has(schedule.id)) this.pending.set(schedule.id, { revision: schedule.revision, idempotency_key: this.makeKey() });
      this.busy.add(schedule.id);
      try {
        const result = await request(this.pending.get(schedule.id));
        this.pending.delete(schedule.id);
        return result;
      } catch (error) {
        if (error.status && error.status < 500) this.pending.delete(schedule.id);
        throw error;
      } finally { this.busy.delete(schedule.id); }
    }
  }
  class ScheduledTasksPage {
    constructor(document, ui) {
      Object.assign(this, { document, ui, generation: 0, refreshNumber: 0, historyNumber: 0, active: false, controller: null, timer: null, page: 1, historyPage: 1, historyId: null, editing: null, mutationBusy: false });
      this.schedules = new Map();
      this.receipt = null;
      this.runRequests = new RunRequests(() => root.crypto.randomUUID());
      this.bind();
    }
    element(id) { return this.document.getElementById(id); }
    message(text, error = false) {
      this.element("scheduleMessage").textContent = text;
      this.element("scheduleMessage").dataset.error = String(error);
    }
    report(error) {
      if (error.name === "AbortError" || !this.active) return;
      this.message(error.code === "revision_conflict" ? `${error.message} Reload the schedule before editing again.` : error.message, true);
    }
    request(url, options = {}) { return this.ui.request(url, { ...options, signal: this.controller?.signal }); }
    bind() {
      this.element("scheduleNew").addEventListener("click", () => this.openForm());
      this.element("scheduleCancel").addEventListener("click", () => this.closeForm());
      this.element("scheduleKind").addEventListener("change", () => this.updateTrigger());
      this.element("scheduleForm").addEventListener("submit", event => { event.preventDefault(); this.save(); });
      this.element("scheduleList").addEventListener("click", event => {
        const button = event.target.closest("button[data-action]");
        if (button) this.action(button);
      });
      for (const [id, change] of [["schedulePrevious", -1], ["scheduleNext", 1]]) this.element(id).addEventListener("click", () => { this.page += change; this.refresh().catch(error => this.report(error)); });
      for (const [id, change] of [["historyPrevious", -1], ["historyNext", 1]]) this.element(id).addEventListener("click", () => { this.historyPage += change; this.loadHistory().catch(error => this.report(error)); });
      this.element("scheduleHistoryClose").addEventListener("click", () => { this.historyId = null; this.historyNumber++; this.element("scheduleHistory").classList.add("hidden"); });
      this.document.addEventListener("visibilitychange", () => {
        if (!this.active) return;
        if (this.document.hidden) this.stopPolling(); else this.startPolling();
      });
    }
    enter() { this.active = true; this.startPolling(); }
    leave() { this.active = false; this.stopPolling(); }
    stopPolling() { this.generation++; clearTimeout(this.timer); this.controller?.abort(); this.controller = null; }
    startPolling() {
      this.stopPolling();
      if (!this.active || this.document.hidden) return;
      this.controller = new AbortController();
      const generation = this.generation;
      const poll = async () => {
        try { await this.refresh(); if (this.historyId !== null) await this.loadHistory(); }
        catch (error) { if (generation === this.generation) this.report(error); }
        if (this.active && !this.document.hidden && generation === this.generation) this.timer = setTimeout(poll, 5000);
      };
      poll();
    }
    async refresh() {
      const generation = this.generation;
      const sequence = ++this.refreshNumber;
      const [schedules, worker, preferences] = await Promise.all([this.request(`${endpoint}?page=${this.page}`), this.request("/api/scheduler/status"), this.request("/api/job-search-preferences")]);
      if (!this.active || generation !== this.generation || sequence !== this.refreshNumber) return;
      this.schedules = new Map(schedules.items.map(item => [item.id, item]));
      this.preferences = preferences;
      this.element("scheduleNoPreferences").classList.toggle("hidden", preferences.length > 0);
      this.element("scheduleNew").disabled = !preferences.length;
      const status = this.element("schedulerStatus");
      status.dataset.state = worker.state;
      status.textContent = worker.state === "fresh" ? `Worker online · ${worker.running_count} running · ${worker.queued_count} queued` : `Worker ${worker.state === "stale" ? "not responding" : "offline"} · Schedules are saved, but requests may expire until the worker starts.`;
      if (this.receipt) {
        const latest = this.schedules.get(this.receipt.scheduleId)?.latest_run;
        if (latest?.id === this.receipt.id) this.message(`${labels[latest.state]} · ${latest.state === "queued" && worker.state !== "fresh" ? "Worker is offline; this request may expire." : "Run request status updated."}`);
      }
      this.renderSchedules(schedules);
    }
    renderSchedules(page) {
      const escape = this.ui.escapeHtml;
      const focused = this.document.activeElement;
      const focusedId = focused?.dataset?.id;
      const focusedAction = focused?.dataset?.action;
      this.element("scheduleList").innerHTML = page.items.length ? page.items.map(schedule => {
        const repeat = schedule.trigger.kind === "once" ? "Once" : `Every ${schedule.trigger.seconds % 3600 === 0 ? `${schedule.trigger.seconds / 3600} hours` : `${schedule.trigger.seconds} seconds`}`;
        const actions = [["edit", "Edit"], [schedule.enabled ? "pause" : "resume", schedule.enabled ? "Pause" : "Resume"], ["run", "Run now"], ["history", "History"], ["delete", "Delete"]];
        return `<article class="panel scheduler-card"><h3>${escape(schedule.name)}</h3><p class="scheduler-meta">${escape(repeat)} · ${schedule.enabled ? "Enabled" : "Paused"} · ${escape(schedule.payload.sites.join(", "))}</p><p>Next run: ${schedule.next_run_at ? escape(this.ui.formatDate(schedule.next_run_at)) : "None"}</p><p>Last result: ${escape(labels[schedule.latest_run?.state] || "No runs yet")}${schedule.active_run_id ? " · Execution active" : ""}</p><div class="scheduler-actions">${actions.map(([action, label]) => `<button class="secondary" type="button" data-action="${action}" data-id="${schedule.id}" ${this.mutationBusy || (action === "run" && (schedule.active_run_id || this.runRequests.busy.has(schedule.id))) ? "disabled" : ""}>${label}</button>`).join("")}</div></article>`;
      }).join("") : '<div class="panel scheduler-card">No schedules yet. Create one to fetch jobs automatically.</div>';
      this.element("schedulePage").textContent = `Page ${page.page} of ${Math.max(1, page.total_pages)} · ${page.total} schedules`;
      this.element("schedulePrevious").disabled = page.page <= 1;
      this.element("scheduleNext").disabled = page.page >= page.total_pages;
      if (focusedId && focusedAction) this.element("scheduleList").querySelector(`[data-id="${Number(focusedId)}"][data-action="${focusedAction}"]`)?.focus();
    }
    updateTrigger() {
      const interval = this.element("scheduleKind").value === "interval";
      this.element("scheduleIntervalLabel").classList.toggle("hidden", !interval);
      this.element("scheduleSeconds").disabled = !interval;
    }
    openForm(schedule = null) {
      this.editing = schedule ? structuredClone(schedule) : null;
      this.element("schedulePreference").innerHTML = (this.preferences || []).map(preference => `<option value="${preference.id}">${this.ui.escapeHtml(preference.job_title)} · ${this.ui.escapeHtml(preference.country || "Any country")}</option>`).join("");
      this.element("scheduleForm").reset();
      this.element("scheduleFormHeading").textContent = schedule ? "Edit schedule" : "New schedule";
      this.element("scheduleName").value = schedule?.name || "";
      this.element("scheduleResults").value = schedule?.payload.results_wanted || 50;
      this.element("scheduleKind").value = schedule?.trigger.kind || "interval";
      this.element("scheduleSeconds").value = schedule?.trigger.seconds || 86400;
      this.element("scheduleStart").value = localInput(schedule ? (schedule.trigger.starts_at || schedule.trigger.run_at) : Date.now() + 600000);
      this.element("scheduleTimezone").textContent = `(${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
      if (schedule) this.element("schedulePreference").value = schedule.payload.preference_id;
      this.document.querySelectorAll('[name="scheduleBoard"]').forEach(checkbox => { checkbox.checked = (schedule?.payload.sites || ["linkedin"]).includes(checkbox.value); });
      this.updateTrigger();
      this.element("scheduleForm").classList.remove("hidden");
      this.element("scheduleName").focus();
    }
    closeForm() { this.editing = null; this.element("scheduleForm").classList.add("hidden"); this.element("scheduleNew").focus(); }
    async save() {
      if (this.mutationBusy) return;
      this.receipt = null;
      const generation = this.generation;
      try {
        const definition = buildDefinition({ name: this.element("scheduleName").value, preference: this.element("schedulePreference").value, sites: [...this.document.querySelectorAll('[name="scheduleBoard"]:checked')].map(input => input.value), results: this.element("scheduleResults").value, kind: this.element("scheduleKind").value, seconds: this.element("scheduleSeconds").value, start: this.element("scheduleStart").value }, this.editing);
        if (this.editing) definition.revision = this.editing.revision;
        this.mutationBusy = true;
        this.element("scheduleSave").disabled = true;
        await this.request(this.editing ? `${endpoint}/${this.editing.id}` : endpoint, { method: this.editing ? "PUT" : "POST", body: JSON.stringify(definition) });
        if (generation !== this.generation) return;
        this.closeForm();
        this.message("Schedule saved.");
      } catch (error) { if (generation === this.generation) this.report(error); }
      finally {
        this.mutationBusy = false;
        this.element("scheduleSave").disabled = false;
        if (generation === this.generation) { try { await this.refresh(); } catch (error) { this.report(error); } }
      }
    }
    async action(button) {
      const schedule = this.schedules.get(Number(button.dataset.id));
      const action = button.dataset.action;
      if (!schedule || this.mutationBusy) return;
      if (action === "edit") return this.openForm(schedule);
      if (action === "history") {
        this.historyId = schedule.id;
        this.historyPage = 1;
        this.element("scheduleHistoryHeading").textContent = `History · ${schedule.name}`;
        this.element("scheduleHistory").classList.remove("hidden");
        try { await this.loadHistory(); } catch (error) { this.report(error); }
        return;
      }
      if (action === "delete" && !root.confirm(`Delete “${schedule.name}”? Running work may finish. History is retained.`)) return;
      this.receipt = null;
      const generation = this.generation;
      this.mutationBusy = true;
      button.disabled = true;
      try {
        if (action === "run") {
          const receipt = await this.runRequests.send(schedule, body => this.request(`${endpoint}/${schedule.id}/run-now`, { method: "POST", body: JSON.stringify(body) }));
          if (receipt && generation === this.generation) {
            this.receipt = { id: receipt.run.id, scheduleId: schedule.id };
            this.message(`${labels[receipt.run.state]} · ${receipt.warning || "Run request accepted."}`);
          }
        } else if (action === "delete") {
          await this.request(`${endpoint}/${schedule.id}?revision=${schedule.revision}`, { method: "DELETE" });
          if (generation === this.generation) this.message("Schedule deleted. Execution history is retained.");
        } else {
          await this.request(`${endpoint}/${schedule.id}/${action}`, { method: "POST", body: JSON.stringify({ revision: schedule.revision }) });
          if (generation === this.generation) this.message(action === "pause" ? "Schedule paused. Running work may finish." : "Schedule resumed.");
        }
      } catch (error) { if (generation === this.generation) this.report(error); }
      finally {
        this.mutationBusy = false;
        if (generation === this.generation) { try { await this.refresh(); } catch (error) { this.report(error); } }
      }
    }
    async loadHistory() {
      const generation = this.generation;
      const sequence = ++this.historyNumber;
      const identifier = this.historyId;
      const history = await this.request(`${endpoint}/${identifier}/runs?page=${this.historyPage}`);
      if (!this.active || generation !== this.generation || sequence !== this.historyNumber || identifier !== this.historyId) return;
      const escape = this.ui.escapeHtml;
      this.element("scheduleHistoryList").innerHTML = history.items.length ? history.items.map(run => {
        const warnings = run.result?.warnings || [];
        const boards = Object.entries(run.result?.boards || {}).map(([site, result]) => `${site}: ${result.status} (${result.count})`);
        return `<article class="scheduler-run"><strong>${escape(labels[run.state] || run.state)}</strong> · ${escape(run.source)} · ${escape(this.ui.formatDate(run.queued_at))}<p>${run.result ? `${run.result.fetched} jobs saved` : "No completed result"}${run.skipped_count ? ` · ${run.skipped_count} occurrences skipped` : ""}</p>${boards.length ? `<p>${escape(boards.join(" · "))}</p>` : ""}${run.error ? `<p>${escape(run.error.message)}</p>` : ""}${warnings.length ? `<ul>${warnings.map(warning => `<li>${escape(warning)}</li>`).join("")}</ul>` : ""}</article>`;
      }).join("") : "<p>No executions yet.</p>";
      this.element("historyPage").textContent = `Page ${history.page} of ${Math.max(1, history.total_pages)} · ${history.total} runs`;
      this.element("historyPrevious").disabled = history.page <= 1;
      this.element("historyNext").disabled = history.page >= history.total_pages;
    }
  }
  if (typeof module !== "undefined") module.exports = { buildDefinition, localInput, RunRequests, ScheduledTasksPage };
  if (root.document?.getElementById("scheduledTasksView")) {
    const page = new ScheduledTasksPage(root.document, root.CvUi);
    root.CvUi.registerView("scheduledTasks", { enter: () => page.enter(), leave: () => page.leave() });
  }
})(typeof window !== "undefined" ? window : globalThis);
