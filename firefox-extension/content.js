(() => {
  const blockedInputTypes = new Set([
    "button", "checkbox", "color", "file", "hidden", "image", "password",
    "radio", "range", "reset", "search", "submit",
  ]);

  function normalized(value = "") {
    return value
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, " ")
      .replace(/ß/g, "ss")
      .replace(/[_\-.:[\]()/#]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function descriptor(element) {
    const labels = element.labels
      ? [...element.labels].map((label) => label.textContent || "")
      : [];
    const parentLabel = element.closest("label")?.textContent || "";
    const labelledBy = (element.getAttribute("aria-labelledby") || "")
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent || "");
    const groupLabel = element.closest("fieldset, [role='group']")
      ?.querySelector("legend")?.textContent || "";
    return normalized([
      element.autocomplete,
      element.name,
      element.id,
      element.placeholder,
      element.getAttribute("aria-label"),
      element.getAttribute("data-testid"),
      ...labels,
      ...labelledBy,
      parentLabel,
      groupLabel,
    ].filter(Boolean).join(" "));
  }

  function profileKeyFor(element) {
    const text = descriptor(element);
    const autocomplete = normalized(element.autocomplete);

    const autocompleteKeys = [
      ["bday day", "birth_day"],
      ["bday month", "birth_month"],
      ["bday year", "birth_year"],
      ["bday", "date_of_birth"],
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
      [/\b(staatsangehorigkeit|nationality|citizenship)\b/, "nationality"],
      [/\b(birth|geburt)\w*\b.*\b(day|tag)\b|\b(day|tag)\b.*\b(birth|geburt)\w*\b/, "birth_day"],
      [/\b(birth|geburt)\w*\b.*\b(month|monat)\b|\b(month|monat)\b.*\b(birth|geburt)\w*\b/, "birth_month"],
      [/\b(birth|geburt)\w*\b.*\b(year|jahr)\b|\b(year|jahr)\b.*\b(birth|geburt)\w*\b/, "birth_year"],
      [/\b(date of birth|birth date|dob|geburtsdatum)\b/, "date_of_birth"],
      [/\b(deutsch\w*|german)\b.*\b(sprache|language|niveau|level|kenntnisse)\b|\b(sprache|language|niveau|level|kenntnisse)\b.*\b(deutsch\w*|german)\b/, "german_language_level"],
      [/\b(englisch\w*|english)\b.*\b(sprache|language|niveau|level|kenntnisse)\b|\b(sprache|language|niveau|level|kenntnisse)\b.*\b(englisch\w*|english)\b/, "english_language_level"],
      [/\b(50.*standort|standort.*50|on site|onsite|office presence|prasenz)\b/, "onsite_availability"],
      [/\b(reisebereitschaft|reisebereit|travel willingness|willing to travel|business travel)\b/, "travel_willingness"],
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
    if (element instanceof HTMLSelectElement) {
      const selectedText = element.options[element.selectedIndex]?.textContent || "";
      const current = normalized(`${element.value || ""} ${selectedText}`);
      const isPlaceholder = !element.value || /\b(bitte.*auswahl|bitte.*wahlen|please.*select|choose|select one)\b/.test(current);
      if (!isPlaceholder) return false;
    } else if (String(element.value || "").trim()) return false;
    return element.getClientRects().length > 0;
  }

  const monthAliases = {
    "01": ["1", "01", "january", "januar"],
    "02": ["2", "02", "february", "februar"],
    "03": ["3", "03", "march", "marz", "maerz"],
    "04": ["4", "04", "april"],
    "05": ["5", "05", "may", "mai"],
    "06": ["6", "06", "june", "juni"],
    "07": ["7", "07", "july", "juli"],
    "08": ["8", "08", "august"],
    "09": ["9", "09", "september"],
    "10": ["10", "october", "oktober"],
    "11": ["11", "november"],
    "12": ["12", "december", "dezember"],
  };

  function selectCandidates(value, key) {
    const wanted = normalized(value);
    const candidates = new Set([wanted]);
    if (["yes", "ja", "true"].includes(wanted)) ["yes", "ja", "true", "1"].forEach((item) => candidates.add(item));
    if (["no", "nein", "false"].includes(wanted)) ["no", "nein", "false", "0"].forEach((item) => candidates.add(item));
    if (key === "birth_day") candidates.add(String(Number(value)));
    if (key === "birth_month") (monthAliases[value] || []).forEach((item) => candidates.add(normalized(item)));
    if (["native", "native speaker", "muttersprache"].includes(wanted)) {
      ["native", "native speaker", "mother tongue", "muttersprache"].forEach((item) => candidates.add(item));
    }
    return candidates;
  }

  function setValue(element, value, key) {
    if (!value) return false;

    if (element instanceof HTMLSelectElement) {
      const candidates = selectCandidates(value, key);
      const option = [...element.options].find((item) =>
        candidates.has(normalized(item.value)) || candidates.has(normalized(item.textContent))
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
    const birthDate = /^(\d{4})-(\d{2})-(\d{2})$/.exec(profile.date_of_birth || "");
    if (birthDate) {
      profile.birth_year = birthDate[1];
      profile.birth_month = birthDate[2];
      profile.birth_day = birthDate[3];
    }

    let count = 0;
    const fields = document.querySelectorAll("input, textarea, select");
    for (const field of fields) {
      if (!isFillable(field)) continue;
      const key = profileKeyFor(field);
      if (key && setValue(field, profile[key], key)) count += 1;
    }
    return { count };
  }

  if (globalThis.__applyKitAutofillListener) {
    try {
      browser.runtime.onMessage.removeListener(globalThis.__applyKitAutofillListener);
    } catch (_) {}
  }
  globalThis.__applyKitAutofillListener = (message) => {
    if (message?.type === "applykit:fill") return fillPage();
    return undefined;
  };
  browser.runtime.onMessage.addListener(globalThis.__applyKitAutofillListener);

  browser.storage.local.get("autoFillEnabled").then(({ autoFillEnabled }) => {
    if (autoFillEnabled) fillPage().catch(() => {});
  });
})();
