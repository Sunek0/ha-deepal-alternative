// Panel shell: app bar, persistent vitals, segmented tabs, action dispatch
// and error feedback. The views live in 60_status.js, 61_climate.js,
// 62_charging.js and 63_driving.js and hang off the prototype.

class DeepalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "status";
    this._deviceId = null;
    this._error = "";
    this._vehicles = [];
    this._animHost = null;
    this._animVideos = {};
    this._animStates = {};
    this._animSupported = null;
    this._animProbeStarted = false;
    installPointerFreeze(this);
    this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
  }

  disconnectedCallback() {
    this._removePointerFreeze();
  }

  set hass(hass) {
    this._hass = hass;
    this._syncVehicles();
    // Rebuilding the whole panel on every global state change would replace
    // the buttons under the pointer and swallow clicks.
    if (
      this.shadowRoot.innerHTML &&
      this._renderKey() === this._renderKeyCache
    ) {
      return;
    }
    if (this._pointerDown) {
      // A finger or the mouse button is down: never swap the DOM under it.
      this._renderPending = true;
      return;
    }
    this._render();
  }

  set narrow(narrow) {
    this._narrow = Boolean(narrow);
    this.toggleAttribute("narrow", this._narrow);
    if (this._hass) this._render();
  }

  /** Whether the combined flash-and-horn control is offered (panel only). */
  get _showsFlashAndHonk() {
    return true;
  }

  _syncVehicles() {
    this._vehicles = discoverVehicles(this._hass || {});
    if (!this._vehicles.some((vehicle) => vehicle.deviceId === this._deviceId)) {
      this._deviceId = this._vehicles.length
        ? this._vehicles[0].deviceId
        : null;
    }
    // A model change can drop the selected tab (the Driving tab only exists
    // on the profiles that define it): fall back to the status tab.
    const vehicle = this._vehicle;
    if (
      vehicle &&
      !this._profileTabs(vehicle).some(([key]) => key === this._tab)
    ) {
      this._tab = "status";
    }
  }

  get _vehicle() {
    return (
      this._vehicles.find((vehicle) => vehicle.deviceId === this._deviceId) ||
      null
    );
  }

  get _language() {
    return panelLanguage(this._hass || {});
  }

  _t(key, values) {
    return translate(this._language, key, values);
  }

  async _callService(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      this._error = "";
    } catch (error) {
      const message = error && (error.message || error.error || String(error));
      this._error = message || this._t("command_failed");
    }
    this._render();
  }

  _onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    const action = target.dataset.action;
    if (action === "tab") {
      this._tab = target.dataset.tab;
      this._render();
      return;
    }
    const vehicle = this._vehicle;
    if (!vehicle) return;
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    switch (action) {
      case "refresh": {
        const id = entity("button", "refresh");
        if (id) this._callService("button", "press", { entity_id: id });
        return;
      }
      case "press": {
        const id = entity("button", target.dataset.key);
        if (id) this._callService("button", "press", { entity_id: id });
        return;
      }
      case "lock-toggle": {
        const id = entity("lock", "doors");
        if (!id) return;
        const locked = stateFor(hass, id)?.state === "locked";
        this._callService("lock", locked ? "unlock" : "lock", {
          entity_id: id,
        });
        return;
      }
      case "cover-toggle": {
        const id = entity("cover", target.dataset.key);
        if (!id) return;
        const open = stateFor(hass, id)?.state === "open";
        this._callService("cover", open ? "close_cover" : "open_cover", {
          entity_id: id,
        });
        return;
      }
      case "climate-mode": {
        const id = entity("climate", "cabin");
        if (id) {
          this._callService("climate", "set_hvac_mode", {
            entity_id: id,
            hvac_mode: target.dataset.mode,
          });
        }
        return;
      }
      case "temp-step": {
        const id = entity("climate", "cabin");
        if (!id) return;
        const state = stateFor(hass, id);
        const current = Number(
          state?.attributes?.temperature ??
            state?.attributes?.current_temperature ??
            22,
        );
        const min = Number(state?.attributes?.min_temp ?? 16);
        const max = Number(state?.attributes?.max_temp ?? 32);
        const delta = Number(target.dataset.delta || 0);
        const value = Math.min(
          max,
          Math.max(min, Math.round((current + delta) * 2) / 2),
        );
        this._callService("climate", "set_temperature", {
          entity_id: id,
          temperature: value,
        });
        return;
      }
      case "number-step": {
        const id = entity("number", target.dataset.key);
        if (!id) return;
        const state = stateFor(hass, id);
        if (!state) return;
        const min = Number(state.attributes.min ?? 0);
        const max = Number(state.attributes.max ?? 3);
        const step = Number(state.attributes.step ?? 1) || 1;
        const delta = Number(target.dataset.delta || 0) * step;
        const value = Math.min(
          max,
          Math.max(min, Number(state.state) + delta),
        );
        this._callService("number", "set_value", { entity_id: id, value });
        return;
      }
      case "toggle-switch": {
        const id = entity("switch", target.dataset.key);
        if (!id) return;
        this._callService("switch", isOn(hass, id) ? "turn_off" : "turn_on", {
          entity_id: id,
        });
        return;
      }
    }
  }

  _onChange(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    if (target.dataset.action === "select-vehicle") {
      this._deviceId = target.value;
      this._render();
      return;
    }
    if (target.dataset.action === "time-set") {
      const vehicle = this._vehicle;
      if (!vehicle) return;
      const id = entityFor(vehicle, "time", target.dataset.key);
      if (id && target.value) {
        this._callService("time", "set_value", {
          entity_id: id,
          time: target.value,
        });
      }
    }
  }

  /** Cheap signature of everything the panel currently shows. */
  _renderKey() {
    const hass = this._hass || {};
    const vehicle = this._vehicle;
    const parts = [
      this._tab,
      this._deviceId || "",
      this._error,
      this._narrow ? "1" : "0",
      panelLanguage(hass),
      this._vehicles
        .map((candidate) => `${candidate.deviceId}:${candidate.name}`)
        .join("|"),
    ];
    if (vehicle && hass.states) {
      for (const [domain, keys] of Object.entries(PANEL_KEYS)) {
        const ids = vehicle.entities[domain];
        if (!ids) continue;
        for (const key of Object.values(keys)) {
          const entityId = ids[key];
          if (!entityId) continue;
          const state = hass.states[entityId];
          parts.push(
            state
              ? `${entityId}=${state.state};${JSON.stringify(state.attributes)}`
              : `${entityId}=missing`,
          );
        }
      }
    }
    return parts.join("\n");
  }

  _render() {
    if (!this._hass) return;
    try {
      this.shadowRoot.innerHTML = this._renderHtml();
      this._syncAnimations();
    } catch (error) {
      // A render error must never leave the panel stuck on the old view.
      console.error("Deepal panel render failed", error);
      this.shadowRoot.innerHTML = `
        <style>${PANEL_CSS}</style>
        <div class="panel">
          <div class="alert">${escapeHtml(
            String((error && error.message) || error),
          )}</div>
        </div>`;
    }
    this._renderKeyCache = this._renderKey();
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    const vehicles = this._vehicles;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    const name = vehicle ? vehicle.name : this._t("title");
    const model = vehicle && vehicle.model ? vehicle.model : "";
    const selector =
      vehicles.length > 1
        ? `
      <div class="vehicle-select">
        <ha-icon icon="mdi:car-multiple"></ha-icon>
        <select data-action="select-vehicle" aria-label="${escapeHtml(this._t("vehicle"))}">
          ${vehicles
            .map(
              (candidate) =>
                `<option value="${escapeHtml(candidate.deviceId)}" ${
                  candidate.deviceId === this._deviceId ? "selected" : ""
                }>${escapeHtml(candidate.name)}</option>`,
            )
            .join("")}
        </select>
      </div>`
        : "";
    return `
      <style>${PANEL_CSS}</style>
      <div class="panel">
        <header class="app-bar">
          <h1 class="app-title">
            <ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon>
            <span>${escapeHtml(name)}</span>
            ${model ? `<span class="model">${escapeHtml(model)}</span>` : ""}
          </h1>
          <div class="spacer"></div>
          ${selector}
          ${
            refresh
              ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" aria-label="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="${PANEL_ICONS.refresh}"></ha-icon></button>`
              : ""
          }
        </header>
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key))}
               <nav class="segmented" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }

  _renderView(vehicle) {
    if (this._tab === "driving") return this._renderDriving(vehicle);
    if (this._tab === "climate") return this._renderClimate(vehicle);
    if (this._tab === "charging") return this._renderCharging(vehicle);
    return this._renderStatus(vehicle);
  }

  /** Tabs of the vehicle's model profile, or the default list. */
  _profileTabs(vehicle) {
    const layout = layoutFor(vehicle);
    return (layout && layout.tabs) || PANEL_TABS;
  }

  _tabsHtml() {
    return this._profileTabs(this._vehicle).map(
      ([key, icon]) => `
      <button class="segment" role="tab" aria-selected="${this._tab === key}" data-action="tab" data-tab="${key}">
        <ha-icon icon="${icon}"></ha-icon>
        <span>${escapeHtml(this._t(`tab_${key}`))}</span>
      </button>`,
    ).join("");
  }
}
