// Dashboard cards. The complete card (`deepal-card`) is the sidebar panel
// inside a card: same vitals, views, actions and update guards. The compact
// card (`deepal-compact-card`) is a glance composition of the same parts:
// title, vitals, the layered picture with its state chips, quick actions and
// a charging strip while the cable is connected.

class DeepalCard extends DeepalPanel {
  constructor() {
    super();
    this._config = {};
  }

  static getStubConfig(hass) {
    const vehicles = discoverVehicles(hass || {});
    return vehicles.length ? { device_id: vehicles[0].deviceId } : {};
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "device_id",
          required: true,
          selector: { device: { filter: [{ integration: "deepal" }] } },
        },
      ],
      computeLabel: () => translate(PANEL_BASE_LANGUAGE, "vehicle"),
    };
  }

  setConfig(config) {
    this._config = config || {};
    if (this._config.device_id) {
      this._deviceId = this._config.device_id;
    }
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 4 };
  }

  get _showsFlashAndHonk() {
    return false;
  }

  get _chipsShowLock() {
    return true;
  }

  _titleHtml() {
    const vehicle = this._vehicle;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    const name = vehicle ? vehicle.name : this._t("title");
    const model = vehicle && vehicle.model ? vehicle.model : "";
    return `
      <div class="card-title">
        <ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon>
        <span>${escapeHtml(name)}</span>
        ${model ? `<span class="model">${escapeHtml(model)}</span>` : ""}
        <div class="spacer"></div>
        ${
          refresh
            ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" aria-label="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="${PANEL_ICONS.refresh}"></ha-icon></button>`
            : ""
        }
      </div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        ${this._titleHtml()}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key), { lock: false })}
               <nav class="segmented" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}

class DeepalCompactCard extends DeepalCard {
  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 3 };
  }

  _actionsHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
    const tile = (icon, label, value, action, key, cls = "") => `
      <button class="tile ${cls}" data-action="${action}" ${key ? `data-key="${key}"` : ""}>
        <ha-icon icon="${icon}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(label)}</span>
          ${value ? `<span class="tile-value">${escapeHtml(value)}</span>` : ""}
        </span>
      </button>`;

    const tiles = [];
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null) {
      tiles.push(
        tile(
          locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock,
          locked ? t("unlock_doors") : t("lock_doors"),
          locked ? t("locked") : t("unlocked"),
          "lock-toggle",
          null,
          locked ? "" : "warn",
        ),
      );
    }
    const windowsId = entityFor(vehicle, "cover", "windows");
    if (windowsId) {
      const open = stateFor(hass, windowsId)?.state === "open";
      tiles.push(
        tile(
          PANEL_ICONS.window,
          open ? t("close_windows") : t("open_windows"),
          open ? t("open") : t("closed"),
          "cover-toggle",
          "windows",
        ),
      );
    }
    if (entityFor(vehicle, "button", "flash_lights")) {
      tiles.push(
        tile(PANEL_ICONS.flash, t("flash_lights"), null, "press", "flash_lights"),
      );
    }
    if (entityFor(vehicle, "button", "honk_horn")) {
      tiles.push(
        tile(PANEL_ICONS.horn, t("honk_horn"), null, "press", "honk_horn"),
      );
    }
    return tiles.length ? `<div class="tiles">${tiles.join("")}</div>` : "";
  }

  _chargingStripHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    if (!plugged) return "";
    const metric = (label, value) => `
      <div class="metric">
        <span class="label">${escapeHtml(label)}</span>
        <span class="value">${escapeHtml(value ?? "—")}</span>
      </div>`;
    const current =
      formatState(hass, entityFor(vehicle, "sensor", "ac_charge_current")) ||
      formatState(hass, entityFor(vehicle, "sensor", "dc_charge_current")) ||
      formatState(hass, entityFor(vehicle, "sensor", "charge_current"));
    const remaining =
      formatState(hass, entityFor(vehicle, "sensor", "remaining_time_formatted")) ||
      formatState(hass, entityFor(vehicle, "sensor", "remaining_time"));
    return `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.charging}"></ha-icon>
          <span class="section-title">${escapeHtml(t("charging"))}</span>
        </div>
        <div class="metrics">
          ${metric(t("charge_status"), chargeStatusText(hass, vehicle, t))}
          ${current ? metric(t("charge_current"), current) : ""}
          ${remaining ? metric(t("remaining_time"), remaining) : ""}
        </div>
      </div>`;
  }

  _climateHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
    const climateId = entityFor(vehicle, "climate", "cabin");
    if (!climateId) return "";
    const climateState = stateFor(hass, climateId);
    const climateOn = climateState ? climateState.state !== "off" : false;
    const target = climateState?.attributes?.temperature;
    return `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
          <span class="section-title">${escapeHtml(t("climate"))}</span>
        </div>
        <div class="segmented">
          <button class="segment" aria-pressed="${climateOn}" data-action="climate-mode" data-mode="heat_cool">
            <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
            <span>${escapeHtml(t("climate_on"))}</span>
          </button>
          <button class="segment" aria-pressed="${!climateOn}" data-action="climate-mode" data-mode="off">
            <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
            <span>${escapeHtml(t("climate_off"))}</span>
          </button>
        </div>
        <div class="center">
          <div class="stepper">
            <button data-action="temp-step" data-delta="-0.5" aria-label="-">&minus;</button>
            <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
            <button data-action="temp-step" data-delta="0.5" aria-label="+">+</button>
          </div>
        </div>
      </div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        ${this._titleHtml()}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key))}
               <div class="section">
                 ${vehiclePhotoHtml(this._hass, vehicle) || vehicleHeroHtml(vehicle) || vehicleStageHtml(this._hass, vehicle)}
                 <div class="chips">${vehicleChipsHtml(this._hass, vehicle, (key) => this._t(key), { openingsOnly: true })}</div>
               </div>
               ${this._climateHtml(vehicle)}
               ${this._actionsHtml(vehicle)}
               ${this._chargingStripHtml(vehicle)}`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}
