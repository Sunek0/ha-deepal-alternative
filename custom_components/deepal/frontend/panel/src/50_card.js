// Shared card base: vehicle discovery, service dispatch, state guards and
// render-key handling. The single dashboard card (70_card.js) provides the
// hero, the configurable sections and the settings panel.

class DeepalCardBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._deviceId = null;
    this._error = "";
    this._vehicles = [];
    this._settingsOpen = false;
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
    // Rebuilding the card on every global state change would replace the
    // buttons under the pointer and swallow clicks.
    if (
      this.shadowRoot.innerHTML &&
      this._renderKey() === this._renderKeyCache
    ) {
      return;
    }
    if (this._pointerDown) {
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

  /** The card offers the combined flash-and-horn action. */
  get _showsFlashAndHonk() {
    return true;
  }

  _syncVehicles() {
    this._vehicles = discoverVehicles(this._hass || {});
    const configured = this._config && this._config.device_id;
    if (
      configured &&
      this._vehicles.some((vehicle) => vehicle.deviceId === configured)
    ) {
      this._deviceId = configured;
      return;
    }
    if (!this._vehicles.some((vehicle) => vehicle.deviceId === this._deviceId)) {
      this._deviceId = this._vehicles.length
        ? this._vehicles[0].deviceId
        : null;
    }
  }

  get _vehicle() {
    return (
      this._vehicles.find((vehicle) => vehicle.deviceId === this._deviceId) ||
      null
    );
  }

  get _language() {
    const configured = this._config && this._config.language;
    if (configured && configured !== "auto") {
      return panelLanguage({ locale: { language: configured } });
    }
    return panelLanguage(this._hass || {});
  }

  _t(key, values) {
    return translate(this._language, key, values);
  }

  async _callService(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      this._error = "";
      this._render();
      return true;
    } catch (error) {
      const message = error && (error.message || error.error || String(error));
      this._error = message || this._t("command_failed");
      this._render();
      return false;
    }
  }

  _handleCustomClick() {
    return false;
  }

  _onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    if (this._handleCustomClick(target)) return;
    this._executeAction(target.dataset.action, target.dataset);
  }

  _executeAction(action, data = {}) {
    const target = { dataset: data };
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
    if (this._handleCustomChange && this._handleCustomChange(event)) return;
    const target = event.target.closest("[data-action]");
    if (!target) return;
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

  /** Cheap signature of everything the card currently shows. */
  _renderKey() {
    const hass = this._hass || {};
    const vehicle = this._vehicle;
    const parts = [
      this._deviceId || "",
      this._error,
      this._narrow ? "1" : "0",
      this._settingsOpen ? "settings" : "",
      panelLanguage(hass),
      this._language,
      JSON.stringify(this._config || {}),
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
      for (const entry of [
        ...(this._config.info_custom || []),
        ...(this._config.diag_custom || []),
      ]) {
        const state = hass.states[entry.entity];
        parts.push(
          state
            ? `${entry.entity}=${state.state};${JSON.stringify(state.attributes)}`
            : `${entry.entity}=missing`,
        );
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
      // A render error must never leave the card stuck on the old view.
      console.error("Deepal card render failed", error);
      this.shadowRoot.innerHTML = `
        <style>${PANEL_CSS}</style>
        <div class="card-root">
          <div class="alert">${escapeHtml(
            String((error && error.message) || error),
          )}</div>
        </div>`;
    }
    this._renderKeyCache = this._renderKey();
  }

  _renderHtml() {
    return `<style>${PANEL_CSS}</style><div class="card-root"><div class="empty">${escapeHtml(this._t("no_vehicle"))}</div></div>`;
  }
}
