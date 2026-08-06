(() => {
  if (globalThis.__applyKitAutofillLoaded) return;
  globalThis.__applyKitAutofillLoaded = true;

  const blockedInputTypes = new Set([
    "button", "checkbox", "color", "file", "hidden", "image", "password",
    "radio", "range", "reset", "search", "submit",
  ]);

  function normalized(value = "") {
    return value
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, " ")
      .replace(/[_\-.:[\]()/#]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function descriptor(element) {
    const labels = element.labels
      ? [...element.labels].map((label) => label.textContent || "")
      : [];
    const parentLabel = element.closest("label")?.textContent || "";
    return normalized([
      element.autocomplete,
      element.name,
      element.id,
      element.placeholder,
      element.getAttribute("aria-label"),
      element.getAttribute("data-testid"),
      ...labels,
      parentLabel,
    ].filter(Boolean).join(" "));
  }

  function profileKeyFor(element) {
    const text = descriptor(element);
    const autocomplete = normalized(element.autocomplete);

    const autocompleteKeys = [
      ["given name", "first_name"],
      ["family name", "last_name"],
      ["address line2", "address_line2"],
      ["address line1", "address_line1"],
      ["street address", "address_line1"],
      ["postal code", "postal_code"],
      ["address level2", "city"],
      ["address level1", "state_region"],
      ["country name", "country"],
      ["organization title", "current_job_title"],
      ["organization", "current_company"],
      ["email", "email"],
      ["tel", "phone"],
      ["name", "full_name"],
      ["url", "website_url"],
    ];
    for (const [token, key] of autocompleteKeys) {
      if (autocomplete.split(" ").join(" ").includes(token)) return key;
    }

    const patterns = [
      [/\b(linkedin|linked in)\b/, "linkedin_url"],
      [/\b(first name|given name|forename|vorname)\b/, "first_name"],
      [/\b(last name|family name|surname|nachname|familienname)\b/, "last_name"],
      [/\b(full name|your name|applicant name|vollstandiger name|name des bewerbers)\b/, "full_name"],
      [/\b(e mail|email|mail address|emailadresse)\b/, "email"],
      [/\b(phone|telephone|mobile|cell|telefon|handy|mobilnummer)\b/, "phone"],
      [/\b(address line 2|address 2|suite|apartment|unit|adresszusatz)\b/, "address_line2"],
      [/\b(street address|address line 1|address 1|street|strasse|anschrift|adresse)\b/, "address_line1"],
      [/\b(postal|zip|postcode|post code|plz|postleitzahl)\b/, "postal_code"],
      [/\b(city|town|locality|stadt|wohnort|ort)\b/, "city"],
      [/\b(state|province|region|county|bundesland)\b/, "state_region"],
      [/\b(country|nation|land)\b/, "country"],
      [/\b(website|portfolio|personal site|homepage|webseite)\b/, "website_url"],
      [/\b(current company|current employer|employer|arbeitgeber|unternehmen)\b/, "current_company"],
      [/\b(current job title|current title|current role|profession|berufsbezeichnung|aktuelle position)\b/, "current_job_title"],
      [/\b(work authorization|authorised to work|authorized to work|work permit|visa status|arbeitserlaubnis)\b/, "work_authorization"],
      [/\b(notice period|availability|available from|kundigungsfrist|verfugbarkeit|eintrittstermin)\b/, "notice_period"],
      [/\b(salary expectation|expected salary|desired salary|compensation expectation|gehaltsvorstellung|wunschgehalt)\b/, "salary_expectation"],
    ];
    return patterns.find(([pattern]) => pattern.test(text))?.[1] || "";
  }

  function isFillable(element) {
    if (!(element instanceof HTMLInputElement ||
          element instanceof HTMLTextAreaElement ||
          element instanceof HTMLSelectElement)) return false;
    if (element.disabled || element.readOnly) return false;
    if (element instanceof HTMLInputElement && blockedInputTypes.has(element.type)) return false;
    if (String(element.value || "").trim()) return false;
    return element.getClientRects().length > 0;
  }

  function setValue(element, value) {
    if (!value) return false;

    if (element instanceof HTMLSelectElement) {
      const wanted = normalized(value);
      const option = [...element.options].find((item) =>
        normalized(item.value) === wanted || normalized(item.textContent) === wanted
      );
      if (!option) return false;
      element.value = option.value;
    } else {
      const prototype = element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (setter) setter.call(element, value);
      else element.value = value;
    }

    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dataset.applykitFilled = "true";
    return true;
  }

  async function fillPage() {
    const profile = await browser.runtime.sendMessage({
      type: "applykit:get-profile",
    });
    profile.full_name = [profile.first_name, profile.last_name]
      .filter(Boolean)
      .join(" ");

    let count = 0;
    const fields = document.querySelectorAll("input, textarea, select");
    for (const field of fields) {
      if (!isFillable(field)) continue;
      const key = profileKeyFor(field);
      if (key && setValue(field, profile[key])) count += 1;
    }
    return { count };
  }

  browser.runtime.onMessage.addListener((message) => {
    if (message?.type === "applykit:fill") return fillPage();
    return undefined;
  });

  browser.storage.local.get("autoFillEnabled").then(({ autoFillEnabled }) => {
    if (autoFillEnabled) fillPage().catch(() => {});
  });
})();

