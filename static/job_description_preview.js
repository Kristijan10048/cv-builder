(function (root) {
  "use strict";

  /** Manage the inline description without replacing the jobs table or its controls. */
  class JobDescriptionPreview {
    constructor(view, columns) {
      this.view = view;
      this.columns = columns;
      this.window = view.ownerDocument.defaultView;
      this.workspace = view.querySelector("#availableJobsWorkspace");
      this.list = view.querySelector("#availableJobsList");
      this.tableContainer = view.querySelector(".application-table-wrap");
      this.panel = view.querySelector("#jobDescriptionPreview");
      this.title = view.querySelector("#jobDescriptionTitle");
      this.content = view.querySelector("#jobDescriptionContent");
      this.items = new Map();
      this.selectedId = null;
      this.savedLayout = null;

      this.list.addEventListener("click", event => {
        const button = event.target.closest(".job-title-button");
        if (button && this.list.contains(button)) this.open(button.dataset.jobId);
      });
      view.querySelector("#jobDescriptionClose").addEventListener("click", () => this.close());
      view.addEventListener("keydown", event => {
        if (event.key === "Escape" && !event.defaultPrevented && this.selectedId !== null) {
          event.preventDefault();
          event.stopPropagation();
          this.close();
        }
      });
    }

    /** Reconcile selection only after the current list request has succeeded. */
    setItems(items) {
      this.items = new Map(items.map(item => [String(item.id), item]));
      if (this.selectedId !== null) {
        if (this.items.has(this.selectedId)) this.render();
        else this.close({ restoreFocus: this.panel.contains(this.view.ownerDocument.activeElement) });
      }
    }

    /** Open or switch descriptions, saving the original layout once per preview session. */
    open(jobId) {
      const selectedId = String(jobId);
      if (!this.items.has(selectedId)) return;
      if (this.selectedId === null) {
        this.savedLayout = {
          columns: this.columns.capture(),
          scrollX: this.window.scrollX,
          scrollY: this.window.scrollY,
          tableScrollLeft: this.tableContainer.scrollLeft,
        };
      }
      const selectionChanged = this.selectedId !== selectedId;
      this.selectedId = selectedId;
      this.panel.hidden = false;
      this.workspace.classList.add("preview-open");
      this.render();
      if (selectionChanged) this.content.scrollTop = 0;
      this.title.focus({ preventScroll: !this.window.matchMedia("(max-width: 700px)").matches });
    }

    /** Insert untrusted posting text literally and mark the selected title. */
    render() {
      const item = this.items.get(this.selectedId);
      this.title.textContent = item.job_title;
      const description = item.description || "";
      const text = description.trim() ? description : "No description available";
      // Avoid resetting the reader's position when a refresh returns unchanged text.
      if (this.content.textContent !== text) this.content.textContent = text;
      this.updateSelection();
    }

    /** Keep selection styling and expanded state in sync after row replacement. */
    updateSelection() {
      this.list.querySelectorAll(".job-title-button").forEach(button => {
        const selected = button.dataset.jobId === this.selectedId;
        button.setAttribute("aria-expanded", String(selected));
        button.closest("tr").classList.toggle("preview-selected", selected);
      });
    }

    /** Restore the original list layout; navigation can opt out of focus and page scrolling. */
    close({ restoreFocus = true, restoreScroll = true } = {}) {
      if (this.selectedId === null) return;
      const selectedId = this.selectedId;
      const savedLayout = this.savedLayout;
      this.selectedId = null;
      this.savedLayout = null;
      this.panel.hidden = true;
      this.workspace.classList.remove("preview-open");
      this.columns.restore(savedLayout.columns);
      this.updateSelection();
      this.title.textContent = "";
      this.content.textContent = "";
      this.tableContainer.scrollLeft = savedLayout.tableScrollLeft;
      if (restoreFocus) {
        const selectedButton = Array.from(this.list.querySelectorAll(".job-title-button"))
          .find(button => button.dataset.jobId === selectedId);
        (selectedButton || this.view.querySelector("#availableJobsSearch")).focus({ preventScroll: true });
      }
      if (restoreScroll) this.window.scrollTo({ left: savedLayout.scrollX, top: savedLayout.scrollY, behavior: "instant" });
    }
  }

  root.JobDescriptionPreview = JobDescriptionPreview;
  if (typeof module !== "undefined") module.exports = { JobDescriptionPreview };
})(typeof window !== "undefined" ? window : globalThis);
