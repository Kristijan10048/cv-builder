const C_OTHER_CITY = '__cv_builder_other_city__'

class SearchPreferenceLocationFields {
  /** Manage country-dependent dropdowns while preserving saved location strings. */
  constructor() {
    this.countries = null
    this.countryRequest = null
    this.citiesByCountry = new Map()
    this.requestVersion = 0
    this.loading = false
    this.countrySelect = $('#searchPreferenceCountry')
    this.citySelect = $('#searchPreferenceCity')
    this.customCityInput = $('#searchPreferenceCustomCity')
    this.countrySelect.addEventListener('change', () => {
      // A city and its radius belong to the old country until explicitly chosen again.
      $('#searchPreferenceRadius').value = 0
      this.load(this.countrySelect.value, '')
    })
    this.citySelect.addEventListener('change', () => this.updateCustomCity(true))
    $('#retrySearchPreferenceLocations').addEventListener('click', () => {
      this.load(this.countrySelect.value, this.cityValue())
    })
  }

  /** Keep location controls and submission disabled during catalog requests. */
  updateDisabled() {
    this.countrySelect.disabled = this.loading
    this.citySelect.disabled = this.loading
    $('#saveSearchPreference').disabled = this.loading || searchPreferenceBusy
  }

  /** Resolve standard saved ISO codes and names without rewriting saved values. */
  countryCode(countryValue) {
    const normalizedValue = countryValue.toLowerCase()
    const aliases = { uk: 'GB', usa: 'US', 'united states of america': 'US', 'the netherlands': 'NL' }
    const country = (this.countries || []).find(candidate =>
      [candidate.name, candidate.code, candidate.iso3].some(value => value.toLowerCase() === normalizedValue)
    )
    return country?.code || aliases[normalizedValue] || ''
  }

  /** Populate native options safely, retaining locations outside the catalog. */
  renderChoices(selectElement, choices, selectedValue, emptyLabel) {
    const options = [new Option(emptyLabel, '')]
    choices.forEach(value => options.push(new Option(value, value)))
    if (selectedValue && !choices.includes(selectedValue)) {
      options.push(new Option(selectedValue, selectedValue))
    }
    selectElement.replaceChildren(...options)
    selectElement.value = selectedValue
  }

  /** Display city choices, an unrestricted choice, and a manual-entry fallback. */
  renderCities(cityNames, selectedCity) {
    this.renderChoices(this.citySelect, cityNames, selectedCity, 'Any city')
    this.citySelect.add(new Option('Other city…', C_OTHER_CITY))
    this.customCityInput.value = ''
    this.updateCustomCity(false)
  }

  /** Expose the manual city field only when the matching dropdown option is used. */
  updateCustomCity(focusInput) {
    const customCitySelected = this.citySelect.value === C_OTHER_CITY
    $('#searchPreferenceCustomCityField').classList.toggle('hidden', !customCitySelected)
    this.customCityInput.required = customCitySelected
    if (customCitySelected && focusInput) this.customCityInput.focus()
  }

  /** Return the city name expected by the existing saved-search API. */
  cityValue() {
    return this.citySelect.value === C_OTHER_CITY
      ? this.customCityInput.value.trim()
      : this.citySelect.value
  }

  /** Reuse one country request and permit a fresh request after a failure. */
  async loadCountries() {
    if (this.countries) return this.countries
    if (!this.countryRequest) {
      this.countryRequest = api('/api/job-search-locations/countries')
        .then(countries => {
          this.countries = countries
          return countries
        })
        .finally(() => { this.countryRequest = null })
    }
    return this.countryRequest
  }

  /** Load one editor's choices and ignore responses from a closed or replaced editor. */
  async load(countryValue, cityValue) {
    const requestVersion = ++this.requestVersion
    this.loading = true
    $('#searchPreferenceLocationError').classList.add('hidden')
    this.renderChoices(this.countrySelect, (this.countries || []).map(country => country.name), countryValue, 'Any country')
    this.renderCities([], cityValue)
    this.updateDisabled()
    try {
      const countries = await this.loadCountries()
      if (requestVersion !== this.requestVersion) return
      this.renderChoices(this.countrySelect, countries.map(country => country.name), countryValue, 'Any country')
      const countryCode = this.countryCode(countryValue)
      let cityNames = []
      if (countryCode) {
        if (!this.citiesByCountry.has(countryCode)) {
          const cities = await api(`/api/job-search-locations/countries/${encodeURIComponent(countryCode)}/cities`)
          this.citiesByCountry.set(countryCode, cities)
        }
        cityNames = this.citiesByCountry.get(countryCode)
      }
      // A request may finish after Cancel, or after opening a different saved search.
      if (requestVersion !== this.requestVersion) return
      this.renderCities(cityNames, cityValue)
    } catch (error) {
      if (requestVersion !== this.requestVersion) return
      $('#searchPreferenceLocationErrorMessage').textContent = `Locations could not be loaded. ${error.message}`
      $('#searchPreferenceLocationError').classList.remove('hidden')
    } finally {
      if (requestVersion === this.requestVersion) {
        this.loading = false
        this.updateDisabled()
      }
    }
  }

  /** Invalidate pending loads and reset manual-entry validation on editor close. */
  close() {
    this.requestVersion += 1
    this.loading = false
    this.customCityInput.required = false
    $('#searchPreferenceCustomCityField').classList.add('hidden')
    this.updateDisabled()
  }
}
