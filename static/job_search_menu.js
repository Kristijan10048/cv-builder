/* Compact job-search tabs keep their forms mounted so drafts survive navigation. */
(function (root) {
  "use strict";

  const C_PREFERENCES_TAB_ID = "jobSearchPreferencesTab";

  /** Control menu visibility and accessible tab navigation without replacing form content. */
  class JobSearchMenu {
    /** Bind the existing menu and a lazy preference loader. */
    constructor(element, loadPreferences) {
      this.element = element;
      this.loadPreferences = loadPreferences;
      this.toggle = element.querySelector("#jobSearchMenuToggle");
      this.tabList = element.querySelector("#jobSearchTabs");
      this.panels = element.querySelector("#jobSearchPanels");
      this.tabs = Array.from(this.tabList.querySelectorAll('[role="tab"]'));
      this.activeTab = this.tabs.find(tab => tab.getAttribute("aria-selected") === "true");
      this.expanded = true;
      this.toggle.addEventListener("click", () => this.setExpanded(!this.expanded));
      this.tabs.forEach(tab => {
        tab.addEventListener("click", () => this.selectTab(tab.id));
        tab.addEventListener("keydown", event => this.handleTabKey(event, tab));
      });
      this.render();
    }

    /** Collapse only the menu, preserving the active tab and all entered values. */
    setExpanded(expanded) {
      if (!expanded && this.element.contains(this.element.ownerDocument.activeElement)) {
        this.toggle.focus();
      }
      this.expanded = expanded;
      this.render();
    }

    /** Activate a panel and request saved searches only when its editor needs them. */
    selectTab(tabId) {
      const selectedTab = this.tabs.find(tab => tab.id === tabId);
      if (!selectedTab) return;
      this.activeTab = selectedTab;
      this.render();
      if (tabId === C_PREFERENCES_TAB_ID) this.loadPreferences();
    }

    /** Support arrow, Home and End keys with a single tab stop in the tab list. */
    handleTabKey(event, tab) {
      const index = this.tabs.indexOf(tab);
      let targetIndex;
      switch (event.key) {
        case "ArrowRight": targetIndex = (index + 1) % this.tabs.length; break;
        case "ArrowLeft": targetIndex = (index + this.tabs.length - 1) % this.tabs.length; break;
        case "Home": targetIndex = 0; break;
        case "End": targetIndex = this.tabs.length - 1; break;
        default: return;
      }
      event.preventDefault();
      this.tabs[targetIndex].focus();
      this.selectTab(this.tabs[targetIndex].id);
    }

    /** Update visibility and ARIA state while leaving forms and fetch requests intact. */
    render() {
      this.tabList.hidden = !this.expanded;
      this.panels.hidden = !this.expanded;
      this.toggle.setAttribute("aria-expanded", String(this.expanded));
      this.toggle.setAttribute("aria-label", this.expanded ? "Hide job search menu" : "Show job search menu");
      this.toggle.textContent = this.expanded ? "Hide ↑" : "Show menu ↓";
      this.tabs.forEach(tab => {
        const selected = tab === this.activeTab;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        this.element.querySelector(`#${tab.getAttribute("aria-controls")}`).hidden = !selected;
      });
    }
  }

  if (typeof module !== "undefined") module.exports = { JobSearchMenu };
  if (root.document) {
    root.jobSearchMenu = new JobSearchMenu(root.document.getElementById("jobSearchTools"), () => {
      if (!searchPreferencesLoaded) return loadJobSearchPreferences();
    });
  }
})(typeof window !== "undefined" ? window : globalThis);
