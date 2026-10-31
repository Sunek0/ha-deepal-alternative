// The single Deepal dashboard card: a configurable hero, configurable
// sections, an action layout, a visual editor and in-card settings. It uses
// the integration's registry-based discovery and model profiles; 61_climate.js,
// 62_charging.js and 63_driving.js provide the section content.

const CARD_SECTIONS = [
  "actions",
  "status",
  "climate",
  "charging",
  "driving",
  "energy",
  "info",
  "diagnostics",
  "tires",
];
const CARD_BUTTONS = [
  "lock",
  "windows",
  "trunk",
  "climate",
  "tires",
  "flash",
  "honk",
  "find",
];
const CARD_HERO_ITEMS = ["name", "model", "plate", "range", "lock", "cloud", "updated"];
const CARD_CONFIRM_ITEMS = ["unlock", "lock", "trunk", "windows", "climate", "flash", "honk", "find"];
const CARD_INFO_ITEMS = {
  odometer: ["sensor", "odometer", "odometer", "odometer"],
  battery: ["sensor", "battery", "battery", "battery"],
  range: ["sensor", "range", "range", "range"],
  outside_temperature: ["sensor", "outside_temperature", "outside_temperature", "temperature"],
  inside_temperature: ["sensor", "inside_temperature", "inside_temperature", "temperature"],
  cabin_humidity: ["sensor", "cabin_humidity", "cabin_humidity", "humidity"],
  fuel_level: ["sensor", "fuel_level", "fuel", "fuel"],
  fuel_range: ["sensor", "fuel_range", "fuel_range", "fuel"],
  charge_status: ["sensor", "charge_status", "charge_status", "charging"],
  vehicle_status: ["sensor", "vehicle_status", "vehicle_status", "car"],
  speed: ["sensor", "speed", "speed", "speed"],
  gear: ["sensor", "gear", "gear", "gear"],
  trip_mileage: ["sensor", "trip_mileage", "trip_mileage", "odometer"],
  mileage_yesterday: ["sensor", "mileage_yesterday", "mileage_yesterday", "odometer"],
};
const CARD_INFO_IDS = Object.keys(CARD_INFO_ITEMS);

const CARD_DEFAULTS = {
  hero_style: "auto",
  hero_show: ["name", "model", "plate", "range", "lock", "cloud", "updated"],
  order: ["actions", "status", "charging", "info", "climate", "tires", "driving", "energy", "diagnostics"],
  hidden: ["status", "climate", "tires", "driving", "energy"],
  buttons: CARD_BUTTONS.slice(),
  buttons_hidden: [],
  button_layout: "grid",
  button_primary: 4,
  button_size: "m",
  button_labels: "both",
  confirm: ["unlock", "trunk", "windows"],
  info: ["odometer", "battery", "outside_temperature", "inside_temperature", "cabin_humidity", "fuel_level", "charge_status"],
  info_custom: [],
  diag: null,
  diag_mode: "alerts",
  diag_custom: [],
  diag_ignore: [],
  show_settings: true,
  language: "auto",
  toasts: true,
  toast_position: "bottom",
  card_padding: "normal",
  image_scale: 1,
  image_aspect: null,
  tire_unit: "bar",
  tire_min: 2.0,
  tire_max: 3.5,
};
const CARD_SETTING_KEYS = Object.keys(CARD_DEFAULTS);

const cardUniq = (values) => [...new Set(values)];
const cardClone = (value) => JSON.parse(JSON.stringify(value));

function cardFixOrder(values, all) {
  const list = cardUniq((Array.isArray(values) ? values : []).filter((value) => all.includes(value)));
  return [...list, ...all.filter((value) => !list.includes(value))];
}

function mergeCardConfig(yaml, local) {
  const c = { ...cardClone(CARD_DEFAULTS), ...(yaml || {}), ...(local || {}) };
  if (c.hero_style === "carview") c.hero_style = "iso";
  c.hero_show = cardUniq((Array.isArray(c.hero_show) ? c.hero_show : []).filter((value) => CARD_HERO_ITEMS.includes(value)));
  c.order = cardFixOrder(c.order, CARD_SECTIONS);
  c.hidden = cardUniq((Array.isArray(c.hidden) ? c.hidden : []).filter((value) => CARD_SECTIONS.includes(value)));
  c.buttons = cardFixOrder(c.buttons, CARD_BUTTONS);
  c.buttons_hidden = cardUniq((Array.isArray(c.buttons_hidden) ? c.buttons_hidden : []).filter((value) => CARD_BUTTONS.includes(value)));
  c.confirm = cardUniq((Array.isArray(c.confirm) ? c.confirm : []).filter((value) => CARD_CONFIRM_ITEMS.includes(value)));
  c.info = cardUniq((Array.isArray(c.info) ? c.info : []).filter((value) => CARD_INFO_IDS.includes(value)));
  c.info_custom = Array.isArray(c.info_custom) ? c.info_custom.filter((item) => item && item.entity) : [];
  c.diag_custom = Array.isArray(c.diag_custom) ? c.diag_custom.filter((item) => item && item.entity) : [];
  c.diag_ignore = Array.isArray(c.diag_ignore) ? c.diag_ignore : [];
  c.button_primary = Math.max(1, Math.min(6, Number(c.button_primary) || 4));
  c.image_scale = Number(c.image_scale) > 0 ? Number(c.image_scale) : 1;
  c.tire_unit = ["bar", "kPa", "psi"].includes(c.tire_unit) ? c.tire_unit : "bar";
  return c;
}

function cardSettingsOnly(values) {
  const out = {};
  if (values && typeof values === "object" && !Array.isArray(values)) {
    for (const key of CARD_SETTING_KEYS) {
      if (Object.prototype.hasOwnProperty.call(values, key)) out[key] = values[key];
    }
  }
  return out;
}

const CARD_CONFIRM_TEXT = {
  unlock: ["confirm_unlock_title", "confirm_unlock_text"],
  lock: ["confirm_lock_title", "confirm_lock_text"],
  trunk: ["confirm_trunk_title", "confirm_trunk_text"],
  windows: ["confirm_windows_title", "confirm_windows_text"],
  climate: ["confirm_climate_title", "confirm_climate_text"],
  flash: ["confirm_flash_title", "confirm_flash_text"],
  honk: ["confirm_honk_title", "confirm_honk_text"],
  find: ["confirm_find_title", "confirm_find_text"],
};

class DeepalCard extends DeepalCardBase {
  constructor() {
    super();
    this._yaml = {};
    this._local = {};
    this._remoteLoaded = false;
    this._settingsTab = "hero";
    this._settingsScroll = 0;
    this._settingsDirty = false;
    this._uiRestored = false;
    this._modal = null;
    this._confirm = null;
    this._moreOpen = false;
    this._toast = null;
    this._saveTimer = null;
    this.shadowRoot.addEventListener("settings-change", (event) => this._patch(event.detail || {}));
    this.shadowRoot.addEventListener("settings-close", () => {
      this._settingsOpen = false;
      this._settingsScroll = 0;
      this._saveUiState();
      this._render();
      this._commitSettings();
    });
  }

  static getStubConfig(hass) {
    const vehicles = discoverVehicles(hass || {});
    return vehicles.length ? { device_id: vehicles[0].deviceId } : {};
  }

  static getConfigElement() {
    return document.createElement("deepal-card-editor");
  }

  setConfig(config) {
    if (!config) throw new Error("Deepal card: missing configuration");
    this._yaml = { ...config };
    this._config = mergeCardConfig(config, this._local);
    if (config.device_id) this._deviceId = config.device_id;
    if (!this._uiRestored) {
      this._uiRestored = true;
      this._restoreUiState();
    }
    if (this._hass) this._render();
  }

  set hass(hass) {
    if (this._settingsOpen && this._hass) {
      // Keep the settings sheet and its scroll position stable while the
      // vehicle telemetry updates behind it.
      this._hass = hass;
      this._syncVehicles();
      return;
    }
    super.hass = hass;
    if (!this._remoteLoaded && this._config) {
      this._remoteLoaded = true;
      this._loadUserData();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._settingsDirty) this._commitSettings();
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _userDataKey() {
    const device = (this._config && this._config.device_id) || this._deviceId || "default";
    return `deepal_card_${device}`;
  }

  async _loadUserData() {
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    try {
      const result = await this._hass.callWS({
        type: "frontend/get_user_data",
        key: this._userDataKey(),
      });
      const value = cardSettingsOnly(result && result.value);
      if (Object.keys(value).length) {
        this._local = { ...value, ...this._local };
        this._config = mergeCardConfig(this._yaml, this._local);
        this._render();
      }
    } catch (error) {
      // User data is optional; the YAML configuration is the source of truth.
    }
  }

  _uiKey() {
    return `deepal_card_ui_${(this._config && this._config.device_id) || this._deviceId || "default"}`;
  }

  _saveUiState() {
    try {
      if (!this._settingsOpen) {
        sessionStorage.removeItem(this._uiKey());
        return;
      }
      sessionStorage.setItem(this._uiKey(), JSON.stringify({
        t: Date.now(),
        tab: this._settingsTab,
        scroll: this._settingsScroll || 0,
      }));
    } catch (error) {
      // Private browsing can disable sessionStorage; the dialog still works.
    }
  }

  _restoreUiState() {
    try {
      const value = JSON.parse(sessionStorage.getItem(this._uiKey()) || "null");
      if (value && Date.now() - value.t < 30000) {
        this._settingsOpen = true;
        this._settingsTab = value.tab || "hero";
        this._settingsScroll = value.scroll || 0;
      }
    } catch (error) {
      // Ignore a malformed or unavailable sessionStorage.
    }
  }

  _patch(patch) {
    if (!patch || !Object.keys(patch).length) return;
    this._local = { ...this._local, ...cardSettingsOnly(patch) };
    this._config = mergeCardConfig(this._yaml, this._local);
    this._settingsDirty = true;
    this._render();
  }

  _commitSettings() {
    if (!this._settingsDirty) return;
    this._settingsDirty = false;
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._persist(), 0);
  }

  async _persist() {
    try {
      await this._saveYaml();
      this._toast = { type: "ok", text: this._t("settings_saved") };
    } catch (error) {
      await this._saveRemote();
      this._toast = {
        type: "warn",
        text: this._t(error && error.message === "ambiguous" ? "settings_ambiguous" : "settings_local"),
      };
    }
    if (this._toast) {
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this._toast = null;
        this._render();
      }, 5000);
      this._render();
    }
  }

  async _saveRemote() {
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    try {
      await this._hass.callWS({
        type: "frontend/set_user_data",
        key: this._userDataKey(),
        value: this._local,
      });
    } catch (error) {
      // A read-only user still gets the in-memory configuration for this view.
    }
  }

  async _saveYaml() {
    const hass = this._hass;
    if (!hass || typeof hass.callWS !== "function" || !this._config.device_id) {
      throw new Error("local");
    }
    if (hass.user && hass.user.is_admin === false) throw new Error("local");
    if (typeof location === "undefined") throw new Error("local");
    const segment = String(location.pathname || "").split("/")[1] || "lovelace";
    const urlPath = segment === "lovelace" ? null : segment;
    const config = await hass.callWS({
      type: "lovelace/config",
      url_path: urlPath,
      force: true,
    });
    const found = [];
    const visit = (node) => {
      if (Array.isArray(node)) {
        node.forEach(visit);
        return;
      }
      if (node && typeof node === "object") {
        if (node.type === `custom:${CARD_TAG}` && node.device_id === this._config.device_id) {
          found.push(node);
        }
        Object.values(node).forEach(visit);
      }
    };
    visit(config);
    if (found.length !== 1) throw new Error("ambiguous");
    Object.assign(found[0], cardSettingsOnly(this._local));
    await hass.callWS({
      type: "lovelace/config/save",
      url_path: urlPath,
      config,
    });
    this._yaml = { ...found[0] };
    this._local = {};
    this._config = mergeCardConfig(this._yaml, {});
  }

  _heroStyle(vehicle) {
    const style = this._config.hero_style || "auto";
    if (style !== "auto") return style;
    if (vehicle.profile === "s07") return "photo";
    if (vehicle.profile === "generic") return "image";
    return "iso";
  }

  _heroAspect(style, vehicle) {
    if (this._config.image_aspect) return this._config.image_aspect;
    if (style === "planta") {
      return vehicle &&
        (vehicle.profile === PANEL_PROFILE_S05_EV ||
          vehicle.profile === PANEL_PROFILE_S05_PHEV ||
          vehicle.profile === PANEL_PROFILE_S07)
        ? "750 / 550"
        : "16 / 9";
    }
    if (style === "iso") return "3 / 2";
    return "16 / 9";
  }

  _heroStageHtml(vehicle, style) {
    const hass = this._hass;
    let html = "";
    const charging = isOn(hass, entityFor(vehicle, "binary_sensor", "charging"));
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    const chargingLayout = layoutFor(vehicle)?.charging;
    const isS05 =
      vehicle.profile === PANEL_PROFILE_S05_EV ||
      vehicle.profile === PANEL_PROFILE_S05_PHEV;
    if (style === "iso" && isS05 && chargingLayout && (charging || plugged)) {
      return `<div class="stage stage-charging">
        <img src="${assetUrl(chargingLayout.base, vehicle)}" alt="">
        <img src="${assetUrl(
          charging ? chargingLayout.layers.charging : chargingLayout.layers.plugged,
          vehicle,
        )}" alt="">
      </div>`;
    }
    if (style === "iso") {
      html = vehicleCompactStageHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    } else if (style === "planta") {
      html = vehicleStageHtml(hass, vehicle, { rotate: true });
      if (!html) html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
    } else if (style === "photo") {
      html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehicleCompactStageHtml(hass, vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    } else {
      html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    }
    return html || `<div class="hero-empty"><ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon></div>`;
  }

  _heroChips(vehicle, show = null) {
    const hass = this._hass;
    const chips = [];
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null && (!show || show.has("lock"))) {
      chips.push(
        `<span class="hero-chip ${locked ? "" : "warn"}">
          <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
          ${escapeHtml(locked ? this._t("locked") : this._t("unlocked"))}
        </span>`,
      );
    }
    const charging = isOn(hass, entityFor(vehicle, "binary_sensor", "charging"));
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    if (charging || plugged) {
      chips.push(
        `<span class="hero-chip on">
          <ha-icon icon="${PANEL_ICONS.charging}"></ha-icon>
          ${escapeHtml(charging ? this._t("charging") : this._t("plugged"))}
        </span>`,
      );
    }
    return chips.join("");
  }

  _renderHero(vehicle) {
    const hass = this._hass;
    const show = new Set(this._config.hero_show || []);
    const style = this._heroStyle(vehicle);
    const name = vehicle.name || this._t("title");
    const model = vehicle.model || "";
    const plate = formatState(hass, entityFor(vehicle, "sensor", "license_plate"));
    const range = formatIntegerState(hass, entityFor(vehicle, "sensor", "range"));
    const fuelRange = formatIntegerState(hass, entityFor(vehicle, "sensor", "fuel_range"));
    const connectedId = entityFor(vehicle, "binary_sensor", "connected");
    const connected = stateFor(hass, connectedId);
    const updatedId = entityFor(vehicle, "sensor", "updated");
    const updatedState = stateFor(hass, updatedId);
    const updated = updatedState
      ? formatRelativeTime(this._language, updatedState.state)
      : null;
    const title = [
      show.has("name") ? `<span class="hero-name">${escapeHtml(name)}</span>` : "",
      show.has("model") && model && !name.toUpperCase().includes(model.toUpperCase())
        ? `<span class="hero-model">${escapeHtml(model)}</span>`
        : "",
      show.has("plate") && plate ? `<span class="hero-plate">${escapeHtml(plate)}</span>` : "",
    ].join("");
    const rangeParts = [
      range ? `<span class="big">${escapeHtml(range)}</span>` : "",
      range ? `<span class="unit">${escapeHtml(this._t("range"))}</span>` : "",
    ].join("");
    const split = [];
    if (fuelRange) {
      split.push(
        `<span><ha-icon icon="${PANEL_ICONS.fuel}"></ha-icon>${escapeHtml(fuelRange)}</span>`,
      );
    }
    const meta = [
      show.has("cloud") && connected
        ? `<span class="hero-cloud ${connected.state === "on" ? "ok" : "bad"}" title="${escapeHtml(connected.state === "on" ? this._t("online") : this._t("offline"))}">
            <ha-icon icon="${connected.state === "on" ? PANEL_ICONS.cloud : PANEL_ICONS.cloud_off}"></ha-icon>
          </span>`
        : "",
    ].join("");
    const chips = this._heroChips(vehicle, show);
    return `
      <div class="hero" style="--hero-aspect:${escapeHtml(this._heroAspect(style, vehicle))};--hero-scale:${this._config.image_scale || 1}">
        <div class="hero-stage" data-style="${escapeHtml(style)}">${this._heroStageHtml(vehicle, style)}</div>
        <div class="hero-shade"></div>
        <div class="hero-top">
          <div class="hero-title">${title}</div>
          <div class="hero-actions">${meta}</div>
        </div>
        ${show.has("range") && rangeParts ? `<div class="hero-range">${rangeParts}${split.length ? `<span class="split">${split.join("")}</span>` : ""}</div>` : ""}
        <div class="hero-bottom">
          <div class="hero-chips">${chips}</div>
          ${show.has("updated") && updated ? `<span class="hero-updated">${escapeHtml(updated)}</span>` : ""}
        </div>
      </div>`;
  }

  _tone(value) {
    if (value === null || value === undefined || value === "unavailable" || value === "unknown") return "warn";
    return "";
  }

  _actionDefs(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const defs = [];
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null) {
      defs.push({
        id: "lock",
        icon: locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock,
        label: locked ? this._t("unlock_doors") : this._t("lock_doors"),
        value: locked ? this._t("locked") : this._t("unlocked"),
        tone: locked ? "" : "warn",
        confirm: locked ? "unlock" : "lock",
        execute: () => this._executeAction("lock-toggle"),
      });
    }
    const coverDef = (id, icon, openLabel, closedLabel, confirmKey) => {
      const state = stateFor(hass, entity("cover", id));
      if (!state) return;
      const open = state.state === "open";
      defs.push({
        id,
        icon,
        label: open ? closedLabel : openLabel,
        value: open ? this._t("open") : this._t("closed"),
        tone: open ? "warn" : "",
        confirm: open ? null : confirmKey,
        execute: () => this._executeAction("cover-toggle", { key: id }),
      });
    };
    coverDef("windows", PANEL_ICONS.window, this._t("open_windows"), this._t("close_windows"), "windows");
    coverDef("trunk", PANEL_ICONS.trunk, this._t("open_trunk"), this._t("close_trunk"), "trunk");

    const climateId = entity("climate", "cabin");
    const climateState = stateFor(hass, climateId);
    if (climateId && climateState) {
      const on = climateState.state !== "off";
      defs.push({
        id: "climate",
        icon: PANEL_ICONS.climate,
        label: this._t("climate"),
        value: on ? this._t("on") : this._t("off"),
        tone: on ? "on" : "",
        modal: "climate",
      });
    }

    const tireValues = [
      ["tire_front_left", "tire_alarm_front_left"],
      ["tire_front_right", "tire_alarm_front_right"],
      ["tire_rear_left", "tire_alarm_rear_left"],
      ["tire_rear_right", "tire_alarm_rear_right"],
    ]
      .map(([key, alarmKey]) => this._tireDisplay(vehicle, key, alarmKey))
      .filter(Boolean);
    if (tireValues.length) {
      defs.push({
        id: "tires",
        icon: PANEL_ICONS.tire,
        label: this._t("tires"),
        value: tireValues[0].text,
        tone: tireValues.some((item) => item.warn) ? "warn" : "",
        modal: "tires",
      });
    }

    for (const [id, icon, label, key, confirmKey] of [
      ["flash", PANEL_ICONS.flash, this._t("flash_lights"), "flash_lights", "flash"],
      ["honk", PANEL_ICONS.horn, this._t("honk_horn"), "honk_horn", "honk"],
      ["find", PANEL_ICONS.flash_and_honk, this._t("flash_and_honk"), "flash_and_honk", "find"],
    ]) {
      if (!entity("button", key)) continue;
      defs.push({
        id,
        icon,
        label,
        value: "",
        confirm: confirmKey,
        execute: () => this._executeAction("press", { key }),
      });
    }
    const hidden = new Set(this._config.buttons_hidden || []);
    const order = this._config.buttons || CARD_BUTTONS;
    return order
      .filter((id) => !hidden.has(id))
      .map((id) => defs.find((def) => def.id === id))
      .filter(Boolean);
  }

  _needsConfirm(def) {
    return Boolean(def && def.confirm && (this._config.confirm || []).includes(def.confirm));
  }

  _runAction(id) {
    const def = this._actionDefs(this._vehicle).find((item) => item.id === id);
    if (!def) return;
    if (def.modal) {
      this._modal = def.modal;
      this._render();
      return;
    }
    if (def.static || !def.execute) return;
    if (this._needsConfirm(def)) {
      this._confirm = def;
      this._render();
      return;
    }
    this._confirm = null;
    def.execute();
  }

  _actionHtml(def) {
    const labels = this._config.button_labels || "both";
    const showTitle = labels === "title" || labels === "both";
    const showValue = labels === "status" || labels === "both";
    const tag = def.static ? "div" : "button";
    const size = ["s", "m", "l"].includes(this._config.button_size)
      ? this._config.button_size
      : "m";
    const attrs = def.static
      ? `class="action static ${def.tone || ""} size-${size}"`
      : `class="action ${def.tone || ""} size-${size}" data-action="card-action" data-id="${escapeHtml(def.id)}" title="${escapeHtml(def.label)}" aria-label="${escapeHtml(def.label)}"`;
    return `<${tag} ${attrs}>
      <ha-icon icon="${def.icon}"></ha-icon>
      ${showTitle ? `<span class="action-label">${escapeHtml(def.label)}</span>` : ""}
      ${showValue && def.value ? `<span class="action-value">${escapeHtml(def.value)}</span>` : ""}
    </${tag}>`;
  }

  _sectionActions(vehicle) {
    const defs = this._actionDefs(vehicle);
    if (!defs.length) return "";
    const size = ["s", "m", "l"].includes(this._config.button_size)
      ? this._config.button_size
      : "m";
    const layout = ["grid", "scroll", "split", "fit"].includes(this._config.button_layout)
      ? this._config.button_layout
      : "grid";
    let body = "";
    if (layout === "scroll") {
      body = `<div class="actions-scroll">${defs.map((def) => this._actionHtml(def)).join("")}</div>`;
    } else if (layout === "split") {
      const primary = Math.max(1, Math.min(defs.length, Number(this._config.button_primary) || 4));
      const main = defs.slice(0, primary);
      const more = defs.slice(primary);
      body = `<div class="actions-split">
        <div class="actions-main" style="--primary:${main.length}">${main.map((def) => this._actionHtml(def)).join("")}</div>
        ${more.length && this._moreOpen ? `<div class="actions-more">${more.map((def) => this._actionHtml(def)).join("")}</div>` : ""}
        ${more.length ? `<button class="actions-more-toggle" data-action="more-actions"><ha-icon icon="${PANEL_ICONS.more}"></ha-icon><span>${escapeHtml(this._t("more"))}</span></button>` : ""}
      </div>`;
    } else {
      body = `<div class="actions-${layout}">${defs.map((def) => this._actionHtml(def)).join("")}</div>`;
    }
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="mdi:gesture-tap-button"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("controls"))}</span>
      </div>
      <div class="actions size-${size}">${body}</div>
    </div>`;
  }

  _metric(label, value, cls = "") {
    return `<div class="metric ${cls}">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div>`;
  }

  _sectionStatus(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const metrics = [];
    const add = (labelKey, entityId, formatter = null) => {
      if (!entityId) return;
      const value = formatter ? formatter() : formatState(hass, entityId);
      if (value === null) return;
      metrics.push(this._metric(this._t(labelKey), value));
    };
    add("odometer", entity("sensor", "odometer"), () =>
      formatIntegerState(hass, entity("sensor", "odometer")),
    );
    if (entity("sensor", "charge_status")) {
      add("charge_status", entity("sensor", "charge_status"), () =>
        chargeStatusText(hass, vehicle, (key) => this._t(key)),
      );
    } else {
      add("vehicle_status", entity("sensor", "vehicle_status"));
    }
    add("battery", entity("sensor", "battery"), () =>
      formatIntegerState(hass, entity("sensor", "battery")),
    );
    add("range", entity("sensor", "range"), () =>
      formatIntegerState(hass, entity("sensor", "range")),
    );
    if (!metrics.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.car}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("status"))}</span>
      </div>
      <div class="metrics">${metrics.join("")}</div>
    </div>`;
  }

  _sectionEnergy(vehicle) {
    if (!hasFuelEntities(vehicle)) return "";
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const values = [
      ["battery", "battery"],
      ["range", "range"],
      ["fuel", "fuel_level"],
      ["fuel_range", "fuel_range"],
      ["fuel_tank_capacity", "fuel_tank_capacity"],
    ]
      .map(([labelKey, key]) => {
        const id = entity("sensor", key);
        return id
          ? this._metric(
              this._t(labelKey),
              formatIntegerState(this._hass, id),
            )
          : "";
      })
      .filter(Boolean);
    if (!values.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.fuel}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("energy"))}</span>
      </div>
      <div class="metrics">${values.join("")}</div>
    </div>`;
  }

  _tireDisplay(vehicle, key, alarmKey) {
    const hass = this._hass;
    const id = entityFor(vehicle, "sensor", key);
    if (!id) return null;
    const state = stateFor(hass, id);
    if (!state) return null;
    const raw = Number.parseFloat(state.state);
    if (!Number.isFinite(raw)) return null;
    const sourceUnit = String(state.attributes.unit_of_measurement || "bar").toLowerCase();
    let bar = raw;
    if (sourceUnit === "kpa") bar = raw / 100;
    else if (sourceUnit === "psi") bar = raw * 0.0689476;
    else if (raw > 50) bar = raw / 100;
    const unit = this._config.tire_unit || "bar";
    const value =
      unit === "kPa" ? Math.round(bar * 100) : unit === "psi" ? (bar / 0.0689476).toFixed(1) : bar.toFixed(2);
    const alarm = isOn(hass, entityFor(vehicle, "binary_sensor", alarmKey));
    const low = Number(this._config.tire_min) > 0 && bar < Number(this._config.tire_min);
    const high = Number(this._config.tire_max) > 0 && bar > Number(this._config.tire_max);
    return { text: `${value} ${unit}`, warn: alarm || low || high };
  }

  _sectionTires(vehicle) {
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const tire = (key, alarmKey, labelKey) => {
      if (!entity("sensor", key)) return "";
      const display = this._tireDisplay(vehicle, key, alarmKey);
      if (!display) return "";
      return `<div class="tile static ${display.warn ? "warn" : ""}">
        <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(this._t(labelKey))}</span>
          <span class="tile-value">${escapeHtml(display.text)}</span>
        </span>
      </div>`;
    };
    const tires = [
      tire("tire_front_left", "tire_alarm_front_left", "front_left"),
      tire("tire_front_right", "tire_alarm_front_right", "front_right"),
      tire("tire_rear_left", "tire_alarm_rear_left", "rear_left"),
      tire("tire_rear_right", "tire_alarm_rear_right", "rear_right"),
    ].filter(Boolean);
    if (!tires.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("tires"))}</span>
      </div>
      <div class="tiles">${tires.join("")}</div>
    </div>`;
  }

  _sectionInfo(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const tiles = [];
    const integerInfo = new Set([
      "odometer",
      "range",
      "battery",
      "fuel_level",
      "fuel_range",
      "trip_mileage",
      "mileage_yesterday",
    ]);
    for (const id of this._config.info || []) {
      const spec = CARD_INFO_ITEMS[id];
      if (!spec) continue;
      const [domain, key, labelKey, iconKey] = spec;
      const entityId = entity(domain, key);
      const value = integerInfo.has(id)
        ? formatIntegerState(hass, entityId)
        : formatState(hass, entityId);
      if (value === null) continue;
      tiles.push(`<div class="info-tile static">
        <ha-icon icon="${PANEL_ICONS[iconKey] || PANEL_ICONS.info}"></ha-icon>
        <div><div class="info-value">${escapeHtml(value)}</div><div class="info-label">${escapeHtml(this._t(labelKey))}</div></div>
      </div>`);
    }
    for (const item of this._config.info_custom || []) {
      const value = formatState(hass, item.entity);
      if (value === null) continue;
      const label = item.label || item.entity;
      tiles.push(`<button class="info-tile" data-action="more-info" data-entity="${escapeHtml(item.entity)}">
        <ha-icon icon="${escapeHtml(item.icon || "mdi:information-outline")}"></ha-icon>
        <div><div class="info-value">${escapeHtml(value)}</div><div class="info-label">${escapeHtml(label)}</div></div>
      </button>`);
    }
    if (!tiles.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.car}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("info"))}</span>
      </div>
      <div class="info-grid">${tiles.join("")}</div>
    </div>`;
  }

  _sectionDiagnostics(vehicle) {
    const hass = this._hass;
    const mode = this._config.diag_mode === "all" ? "all" : "alerts";
    const selected = Array.isArray(this._config.diag) ? new Set(this._config.diag) : null;
    const ignored = new Set(this._config.diag_ignore || []);
    const items = [];
    for (const [key, icon] of PANEL_WARNINGS) {
      if (selected && !selected.has(key)) continue;
      const id = entityFor(vehicle, "binary_sensor", key);
      if (!id || ignored.has(id)) continue;
      const state = stateFor(hass, id);
      if (!state) continue;
      const on = state.state === "on";
      if (mode === "alerts" && !on) continue;
      items.push(`<span class="chip ${on ? "warn" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
        ${escapeHtml(this._t(key))}${mode === "all" ? `: ${escapeHtml(this._t(on ? "on" : "off"))}` : ""}
      </span>`);
    }
    for (const item of this._config.diag_custom || []) {
      if (ignored.has(item.entity)) continue;
      const state = stateFor(hass, item.entity);
      if (!state) continue;
      const on = ["on", "true", "problem", "alarm", "low"].includes(String(state.state).toLowerCase());
      if (mode === "alerts" && !on) continue;
      items.push(`<span class="chip ${on ? "warn" : ""}">
        <ha-icon icon="${escapeHtml(item.icon || PANEL_ICONS.alert)}"></ha-icon>
        ${escapeHtml(item.label || item.entity)}${mode === "all" ? `: ${escapeHtml(this._t(on ? "on" : "off"))}` : ""}
      </span>`);
    }
    if (!items.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.alert}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("diagnostics"))}</span>
      </div>
      <div class="chips">${items.join("")}</div>
    </div>`;
  }

  _chargingConnected(vehicle) {
    return (
      isOn(this._hass, entityFor(vehicle, "binary_sensor", "charger_plugged")) ||
      isOn(this._hass, entityFor(vehicle, "binary_sensor", "charging"))
    );
  }

  _sectionHtml(key, vehicle) {
    switch (key) {
      case "actions":
        return this._sectionActions(vehicle);
      case "status":
        return this._sectionStatus(vehicle);
      case "climate":
        return this._renderClimate(vehicle);
      case "charging":
        return this._chargingConnected(vehicle) ? this._renderCharging(vehicle) : "";
      case "driving":
        return vehicle.profile === PANEL_PROFILE_S07 ? this._renderDriving(vehicle) : "";
      case "energy":
        return this._sectionEnergy(vehicle);
      case "info":
        return this._sectionInfo(vehicle);
      case "diagnostics":
        return this._sectionDiagnostics(vehicle);
      case "tires":
        return this._sectionTires(vehicle);
      default:
        return "";
    }
  }

  _renderSections(vehicle) {
    const hidden = new Set(this._config.hidden || []);
    return (this._config.order || CARD_SECTIONS)
      .filter((key) => !hidden.has(key))
      .map((key) => this._sectionHtml(key, vehicle))
      .filter(Boolean)
      .join("");
  }

  _seatControlHtml(vehicle, key, label) {
    const id = entityFor(vehicle, "number", key);
    if (!id) return "";
    const state = stateFor(this._hass, id);
    return `<div class="control">
      <span class="label">${escapeHtml(label)}</span>
      <div class="stepper">
        <button data-action="number-step" data-key="${key}" data-delta="-1" aria-label="-">&minus;</button>
        <span class="value">${escapeHtml(state ? state.state : "—")}</span>
        <button data-action="number-step" data-key="${key}" data-delta="1" aria-label="+">+</button>
      </div>
    </div>`;
  }

  _climateModalHtml(vehicle) {
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const climateId = entity("climate", "cabin");
    const climateState = stateFor(this._hass, climateId);
    const on = Boolean(climateState && climateState.state !== "off");
    const target = climateState?.attributes?.temperature;
    const inside = formatState(this._hass, entity("sensor", "inside_temperature"));
    const humidity = formatState(this._hass, entity("sensor", "cabin_humidity"));
    const seats = [
      ["seat_heating_front_left", `${this._t("seat_heating")} · ${this._t("front_left")}`],
      ["seat_heating_front_right", `${this._t("seat_heating")} · ${this._t("front_right")}`],
      ["seat_ventilation_front_left", `${this._t("seat_ventilation")} · ${this._t("front_left")}`],
      ["seat_ventilation_front_right", `${this._t("seat_ventilation")} · ${this._t("front_right")}`],
      ["seat_heating_rear_left", `${this._t("seat_heating")} · ${this._t("rear_left")}`],
      ["seat_heating_rear_right", `${this._t("seat_heating")} · ${this._t("rear_right")}`],
      ["seat_ventilation_rear_left", `${this._t("seat_ventilation")} · ${this._t("rear_left")}`],
      ["seat_ventilation_rear_right", `${this._t("seat_ventilation")} · ${this._t("rear_right")}`],
    ]
      .map(([key, label]) => this._seatControlHtml(vehicle, key, label))
      .filter(Boolean);
    const steeringId = entity("switch", "steering_wheel_heating");
    const steeringOn = isOn(this._hass, steeringId);
    const steering = steeringId
      ? `<button class="tile ${steeringOn ? "on" : ""}" data-action="toggle-switch" data-key="steering_wheel_heating">
          <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
          <span class="tile-body">
            <span class="tile-label">${escapeHtml(this._t("steering_wheel"))}</span>
            <span class="tile-value">${escapeHtml(this._t(steeringOn ? "on" : "off"))}</span>
          </span>
        </button>`
      : "";
    const metrics = [
      inside ? this._metric(this._t("inside_temperature"), inside) : "",
      humidity ? this._metric(this._t("cabin_humidity"), humidity) : "",
    ].filter(Boolean);
    return `<div class="modal-columns">
      <div class="modal-col">
        <div class="modal-section">
          <h4>${escapeHtml(this._t("climate"))}</h4>
          ${metrics.length ? `<div class="metrics">${metrics.join("")}</div>` : ""}
          <div class="center">
            <div class="stepper large">
              <button data-action="temp-step" data-delta="-0.5" aria-label="-">&minus;</button>
              <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
              <button data-action="temp-step" data-delta="0.5" aria-label="+">+</button>
            </div>
          </div>
          <div class="segmented">
            <button class="segment" aria-pressed="${on}" data-action="climate-mode" data-mode="heat_cool">
              <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon><span>${escapeHtml(this._t("climate_on"))}</span>
            </button>
            <button class="segment" aria-pressed="${!on}" data-action="climate-mode" data-mode="off">
              <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon><span>${escapeHtml(this._t("climate_off"))}</span>
            </button>
          </div>
        </div>
      </div>
      <div class="modal-col">
        <div class="modal-section">
          <h4>${escapeHtml(this._t("seats"))}</h4>
          ${seats.length ? `<div class="steppers">${seats.join("")}</div>` : ""}
          ${steering ? `<div class="tiles">${steering}</div>` : ""}
        </div>
      </div>
    </div>`;
  }

  _tiresModalHtml(vehicle) {
    const tires = [
      ["tire_front_left", "tire_alarm_front_left", "front_left"],
      ["tire_front_right", "tire_alarm_front_right", "front_right"],
      ["tire_rear_left", "tire_alarm_rear_left", "rear_left"],
      ["tire_rear_right", "tire_alarm_rear_right", "rear_right"],
    ]
      .map(([key, alarmKey, labelKey]) => {
        const display = this._tireDisplay(vehicle, key, alarmKey);
        if (!display) return "";
        return `<div class="tire-card ${display.warn ? "warn" : ""}">
          <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
          <div>
            <div class="tire-label">${escapeHtml(this._t(labelKey))}</div>
            <div class="tire-value">${escapeHtml(display.text)}</div>
          </div>
        </div>`;
      })
      .filter(Boolean);
    return tires.length
      ? `<div class="tire-grid">${tires.join("")}</div>`
      : `<div class="empty">${escapeHtml(this._t("unavailable"))}</div>`;
  }

  _renderModal() {
    if (!this._modal || !this._vehicle) return "";
    const title = this._t(this._modal === "tires" ? "tires" : "climate");
    const body = this._modal === "tires"
      ? this._tiresModalHtml(this._vehicle)
      : this._climateModalHtml(this._vehicle);
    return `<div class="modal-sheet">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head">
          <h3>${escapeHtml(title)}</h3>
          <button class="settings-close" data-action="close-modal" aria-label="${escapeHtml(this._t("close"))}">
            <ha-icon icon="${PANEL_ICONS.close}"></ha-icon>
          </button>
        </div>
        <div class="modal-body">${body}</div>
      </div>
    </div>`;
  }

  _renderConfirm() {
    if (!this._confirm) return "";
    const [titleKey, textKey] = CARD_CONFIRM_TEXT[this._confirm.confirm] || ["confirm_title", "confirm_text"];
    return `<div class="confirm-sheet">
      <div class="confirm-box" role="dialog" aria-modal="true">
        <h3>${escapeHtml(this._t(titleKey))}</h3>
        <p>${escapeHtml(this._t(textKey))}</p>
        <div class="confirm-actions">
          <button data-action="confirm-no">${escapeHtml(this._t("cancel"))}</button>
          <button class="go" data-action="confirm-yes">${escapeHtml(this._t("confirm"))}</button>
        </div>
      </div>
    </div>`;
  }

  _renderToast() {
    if (!this._toast || this._config.toasts === false) return "";
    return `<div class="card-toast pos-${this._config.toast_position === "top" ? "top" : "bottom"} ${this._toast.type || ""}">${escapeHtml(this._toast.text)}</div>`;
  }

  _renderSettings() {
    return `<div class="settings-sheet"><deepal-card-settings></deepal-card-settings></div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `<style>${PANEL_CSS}</style>
      <div class="card-root" data-pad="${escapeHtml(this._config.card_padding || "normal")}">
        ${vehicle ? this._renderHero(vehicle) : ""}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${this._renderToast()}
        ${vehicle ? this._renderSections(vehicle) : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`}
        ${vehicle && this._config.show_settings !== false ? `<button class="card-footer" data-action="open-settings"><ha-icon icon="${PANEL_ICONS.settings}"></ha-icon><span>${escapeHtml(this._t("settings"))}</span></button>` : ""}
        ${this._renderModal()}
        ${this._settingsOpen ? this._renderSettings() : ""}
        ${this._renderConfirm()}
      </div>`;
  }

  _render() {
    const previous = this.shadowRoot.querySelector("deepal-card-settings");
    if (previous && previous._tab) this._settingsTab = previous._tab;
    if (previous && previous.shadowRoot) {
      const body = previous.shadowRoot.querySelector(".settings-body");
      if (body) this._settingsScroll = body.scrollTop;
    }
    super._render();
    const settings = this.shadowRoot.querySelector("deepal-card-settings");
    if (settings) {
      settings.hass = this._hass;
      settings.tab = this._settingsTab;
      settings.config = this._config;
      if (this._settingsScroll) {
        requestAnimationFrame(() => {
          const body = settings.shadowRoot && settings.shadowRoot.querySelector(".settings-body");
          if (body) body.scrollTop = this._settingsScroll;
        });
      }
    }
    this._saveUiState();
  }

  _renderKey() {
    return [
      super._renderKey(),
      this._modal || "",
      this._confirm ? this._confirm.id : "",
      this._moreOpen ? "more" : "",
      this._toast ? `${this._toast.type}:${this._toast.text}` : "",
    ].join("|");
  }

  _handleCustomClick(target) {
    const action = target.dataset.action;
    if (action === "open-settings") {
      this._settingsOpen = true;
      this._settingsTab = "hero";
      this._settingsScroll = 0;
      this._modal = null;
      this._saveUiState();
      this._render();
      return true;
    }
    if (action === "close-modal") {
      this._modal = null;
      this._render();
      return true;
    }
    if (action === "card-action") {
      this._runAction(target.dataset.id);
      return true;
    }
    if (action === "more-actions") {
      this._moreOpen = !this._moreOpen;
      this._render();
      return true;
    }
    if (action === "more-info") {
      const entityId = target.dataset.entity;
      if (entityId) {
        this.dispatchEvent(new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId },
        }));
      }
      return true;
    }
    if (action === "confirm-yes") {
      const def = this._confirm;
      this._confirm = null;
      this._render();
      if (def && def.execute) def.execute();
      return true;
    }
    if (action === "confirm-no") {
      this._confirm = null;
      this._render();
      return true;
    }
    return false;
  }
}

class DeepalCardSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "hero";
    this._config = null;
    this._hass = null;
    this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
  }

  set hass(value) {
    this._hass = value;
  }

  set config(value) {
    this._config = value;
    this._render();
  }

  set tab(value) {
    this._tab = ["hero", "sections", "actions", "sensors", "appearance"].includes(value) ? value : "hero";
    if (this._config) this._render();
  }

  get embedded() {
    return this.hasAttribute("embedded");
  }

  _t(key, values) {
    const language =
      this._config && this._config.language && this._config.language !== "auto"
        ? this._config.language
        : panelLanguage(this._hass || {});
    return translate(panelLanguage({ locale: { language } }), key, values);
  }

  _emit(patch) {
    this.dispatchEvent(new CustomEvent("settings-change", {
      detail: patch,
      bubbles: true,
      composed: true,
    }));
  }

  _tabs() {
    const tabs = [
      ["hero", "settings_hero"],
      ["sections", "settings_sections"],
      ["actions", "settings_actions"],
      ["sensors", "settings_sensors"],
      ["appearance", "settings_appearance"],
    ];
    return `<div class="settings-tabs">${tabs.map(([id, label]) =>
      `<button class="settings-tab ${this._tab === id ? "on" : ""}" data-settings-tab="${id}">${escapeHtml(this._t(label))}</button>`
    ).join("")}</div>`;
  }

  _select(key, value, options) {
    return `<select data-setting="${key}">${options.map(([id, label]) =>
      `<option value="${escapeHtml(id)}" ${String(id) === String(value) ? "selected" : ""}>${escapeHtml(this._t(label))}</option>`
    ).join("")}</select>`;
  }

  _check(key, value, label) {
    return `<label class="setting-row"><span>${escapeHtml(this._t(label))}</span><input type="checkbox" data-setting="${key}" ${value ? "checked" : ""}></label>`;
  }

  _arrayCheck(key, item, values, label) {
    return `<label class="setting-row"><span>${escapeHtml(this._t(label))}</span><input type="checkbox" data-array="${key}" data-value="${item}" ${(values || []).includes(item) ? "checked" : ""}></label>`;
  }

  _orderList(key, values, all, labelOf, hiddenKey) {
    const hidden = new Set((hiddenKey && this._config[hiddenKey]) || []);
    return `<div class="settings-group">${(values || all).map((id, index) => {
      const isHidden = hidden.has(id);
      return `<div class="setting-row ${isHidden ? "off" : ""}">
        <span>${escapeHtml(this._t(labelOf(id)))}</span>
        <span class="move">
          <button data-order="${key}" data-id="${id}" data-dir="-1" ${index === 0 ? "disabled" : ""} aria-label="${escapeHtml(this._t("move_up"))}"><ha-icon icon="${PANEL_ICONS.up}"></ha-icon></button>
          <button data-order="${key}" data-id="${id}" data-dir="1" ${index === (values || all).length - 1 ? "disabled" : ""} aria-label="${escapeHtml(this._t("move_down"))}"><ha-icon icon="${PANEL_ICONS.down}"></ha-icon></button>
          ${hiddenKey ? `<input type="checkbox" data-hide="${hiddenKey}" data-value="${id}" ${isHidden ? "" : "checked"} aria-label="${escapeHtml(this._t("show"))}">` : ""}
        </span>
      </div>`;
    }).join("")}</div>`;
  }

  _tabHero() {
    const c = this._config;
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("settings_hero"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("image_style"))}</span>${this._select("hero_style", c.hero_style, [
        ["auto", "auto"], ["planta", "planta"], ["iso", "isometric"], ["photo", "photo"], ["image", "image_entity"],
      ])}</label>
      <label class="setting-row"><span>${escapeHtml(this._t("image_scale"))}</span><input type="number" step="0.05" min="0.5" max="2" data-setting="image_scale" value="${escapeHtml(c.image_scale)}"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("image_aspect"))}</span><input type="text" data-setting="image_aspect" value="${escapeHtml(c.image_aspect || "")}" placeholder="3 / 2"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("card_padding"))}</span>${this._select("card_padding", c.card_padding, [["normal", "normal"], ["half", "half"], ["none", "none"]])}</label>
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("show_on_hero"))}</h4>
      ${CARD_HERO_ITEMS.map((item) => this._arrayCheck("hero_show", item, c.hero_show, item === "model" ? "model" : item === "plate" ? "plate" : item)).join("")}
    </div>`;
  }

  _tabSections() {
    return `<p class="settings-hint">${escapeHtml(this._t("sections_hint"))}</p>
      ${this._orderList("order", this._config.order, CARD_SECTIONS, (id) => `section_${id}`, "hidden")}`;
  }

  _tabActions() {
    const c = this._config;
    return `<p class="settings-hint">${escapeHtml(this._t("actions_hint"))}</p>
      ${this._orderList("buttons", c.buttons, CARD_BUTTONS, (id) => (id === "find" ? "flash_and_honk" : id), "buttons_hidden")}
      <div class="settings-group">
        <h4>${escapeHtml(this._t("settings_actions"))}</h4>
        <label class="setting-row"><span>${escapeHtml(this._t("button_layout"))}</span>${this._select("button_layout", c.button_layout, [["grid", "grid"], ["scroll", "scroll"], ["split", "split"], ["fit", "fit"]])}</label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_primary"))}</span><input type="number" min="1" max="6" data-setting="button_primary" value="${escapeHtml(c.button_primary)}"></label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_size"))}</span>${this._select("button_size", c.button_size, [["s", "s"], ["m", "m"], ["l", "l"]])}</label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_labels"))}</span>${this._select("button_labels", c.button_labels, [["none", "none"], ["status", "status"], ["title", "title"], ["both", "both"]])}</label>
      </div>
      <div class="settings-group">
        <h4>${escapeHtml(this._t("confirm"))}</h4>
        ${CARD_CONFIRM_ITEMS.map((item) => this._arrayCheck("confirm", item, c.confirm, item === "find" ? "flash_and_honk" : item === "flash" ? "flash_lights" : item === "honk" ? "honk_horn" : item)).join("")}
      </div>`;
  }

  _tabSensors() {
    const c = this._config;
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("info"))}</h4>
      ${CARD_INFO_IDS.map((item) => this._arrayCheck("info", item, c.info, CARD_INFO_ITEMS[item][2])).join("")}
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("diagnostics"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("diag_mode"))}</span>${this._select("diag_mode", c.diag_mode, [["alerts", "alerts_only"], ["all", "all_warnings"]])}</label>
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("tires"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_unit"))}</span>${this._select("tire_unit", c.tire_unit, [["bar", "bar"], ["kPa", "kPa"], ["psi", "psi"]])}</label>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_min"))}</span><input type="number" step="0.1" data-setting="tire_min" value="${escapeHtml(c.tire_min)}"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_max"))}</span><input type="number" step="0.1" data-setting="tire_max" value="${escapeHtml(c.tire_max)}"></label>
    </div>`;
  }

  _tabAppearance() {
    const c = this._config;
    const languages = [
      ["auto", "automatic"],
      ...Object.keys(PANEL_TEXTS).map((code) => [
        code,
        PANEL_LANGUAGE_NAMES[code] || code.toUpperCase(),
      ]),
    ];
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("appearance"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("language"))}</span>${this._select("language", c.language, languages)}</label>
      ${this._check("toasts", c.toasts !== false, "toasts")}
      <label class="setting-row"><span>${escapeHtml(this._t("toast_position"))}</span>${this._select("toast_position", c.toast_position, [["bottom", "bottom"], ["top", "top"]])}</label>
      ${this._check("show_settings", c.show_settings !== false, "show_settings")}
    </div>`;
  }

  _body() {
    if (!this._config) return "";
    if (this._tab === "sections") return this._tabSections();
    if (this._tab === "actions") return this._tabActions();
    if (this._tab === "sensors") return this._tabSensors();
    if (this._tab === "appearance") return this._tabAppearance();
    return this._tabHero();
  }

  _render() {
    if (!this._config) return;
    this.shadowRoot.innerHTML = `<style>${PANEL_CSS}</style>
      <div class="settings-panel ${this.embedded ? "embedded" : ""}">
        <div class="settings-head">
          <h3>${escapeHtml(this._t("settings"))}</h3>
          ${this.embedded ? "" : `<button class="settings-close" data-settings-close aria-label="${escapeHtml(this._t("close"))}"><ha-icon icon="${PANEL_ICONS.close}"></ha-icon></button>`}
        </div>
        ${this._tabs()}
        <div class="settings-body">${this._body()}</div>
      </div>`;
  }

  _onClick(event) {
    const tab = event.target.closest("[data-settings-tab]");
    if (tab) {
      this._tab = tab.dataset.settingsTab;
      this._render();
      return;
    }
    if (event.target.closest("[data-settings-close]")) {
      this.dispatchEvent(new CustomEvent("settings-close", { bubbles: true, composed: true }));
      return;
    }
    const order = event.target.closest("[data-order]");
    if (order) {
      const key = order.dataset.order;
      const list = [...(this._config[key] || [])];
      const index = list.indexOf(order.dataset.id);
      const next = index + Number(order.dataset.dir);
      if (index < 0 || next < 0 || next >= list.length) return;
      [list[index], list[next]] = [list[next], list[index]];
      this._emit({ [key]: list });
    }
  }

  _onChange(event) {
    const input = event.target;
    if (input.dataset.setting) {
      let value = input.type === "checkbox" ? input.checked : input.value;
      if (input.type === "number") value = Number(value);
      if (["image_aspect"].includes(input.dataset.setting) && !value) value = null;
      this._emit({ [input.dataset.setting]: value });
      return;
    }
    if (input.dataset.array) {
      const key = input.dataset.array;
      const set = new Set(this._config[key] || []);
      if (input.checked) set.add(input.dataset.value);
      else set.delete(input.dataset.value);
      this._emit({ [key]: [...set] });
      return;
    }
    if (input.dataset.hide) {
      const key = input.dataset.hide;
      const set = new Set(this._config[key] || []);
      if (input.checked) set.delete(input.dataset.value);
      else set.add(input.dataset.value);
      this._emit({ [key]: [...set] });
    }
  }
}

class DeepalCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._settings = null;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._draw();
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (this._settings) {
      this._settings.hass = value;
      if (first) this._draw();
      return;
    }
    this._draw();
  }

  _draw() {
    const vehicles = discoverVehicles(this._hass || {});
    const selected = this._config.device_id || (vehicles[0] && vehicles[0].deviceId) || "";
    this.shadowRoot.innerHTML = `<style>${PANEL_CSS}</style>
      <div class="card-editor">
        <label class="editor-field"><span>${escapeHtml(translate(panelLanguage(this._hass || {}), "vehicle"))}</span>
          <select data-device>
            ${vehicles.length ? "" : `<option value="">${escapeHtml(translate(panelLanguage(this._hass || {}), "no_vehicle"))}</option>`}
            ${vehicles.map((vehicle) => `<option value="${escapeHtml(vehicle.deviceId)}" ${vehicle.deviceId === selected ? "selected" : ""}>${escapeHtml(vehicle.name)}${vehicle.model ? ` · ${escapeHtml(vehicle.model)}` : ""}</option>`).join("")}
          </select>
        </label>
        <deepal-card-settings embedded></deepal-card-settings>
      </div>`;
    const settings = this.shadowRoot.querySelector("deepal-card-settings");
    settings.hass = this._hass;
    settings.tab = "hero";
    settings.config = mergeCardConfig(this._config, null);
    settings.addEventListener("settings-change", (event) => {
      this._config = { ...this._config, ...event.detail };
      settings.config = mergeCardConfig(this._config, null);
      this._emit();
    });
    this.shadowRoot.querySelector("[data-device]").addEventListener("change", (event) => {
      this._config = { ...this._config, device_id: event.target.value };
      this._emit();
      this._draw();
    });
    this._settings = settings;
  }

  _emit() {
    const { type, device_id, ...rest } = this._config;
    const config = { type: `custom:${CARD_TAG}`, ...rest };
    if (device_id) config.device_id = device_id;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
  }
}
