// GENERATED FILE - do not edit; run scripts/build_panel.py after changing src/ or texts/.
const PANEL_VERSION = "1.4.0-beta.5";

// ---- 10_constantes.js ----
// Constants shared by the panel modules. The build script prepends the
// PANEL_VERSION constant before this file.
const PANEL_TAG = "deepal-panel";
const CARD_TAG = "deepal-card";
const PANEL_BASE_LANGUAGE = "en";
// Languages that borrow another language's texts verbatim.
const PANEL_BORROWED_LANGUAGES = { ca: "es", gl: "es", eu: "es" };
const PANEL_ASSETS_URL = "/deepal/frontend/assets";

// Tabs, in order: [key, icon]. The key is also the text key "tab_<key>".
const PANEL_TABS = [
  ["status", "mdi:car"],
  ["climate", "mdi:air-conditioner"],
  ["charging", "mdi:battery-charging"],
];

// Layered S05 views. Every file shares the canvas size of its base image,
// so the panel only stacks them in order. Paths are relative to the assets
// URL. Models without a layout fall back to the vehicle image entity.
const PANEL_S05_LAYOUT = {
  status: {
    // The base is the bare body: hood, trunk and doors are separate pieces
    // that must always be drawn, closed or open, like the hand-made panel.
    base: "s05/estado_planta/Ocar1.png",
    layers: {
      hood_closed: "s05/estado_planta/Ohood0.png",
      hood_open: "s05/estado_planta/Ohood1.png",
      trunk_closed: "s05/estado_planta/Otrunk0.png",
      trunk_open: "s05/estado_planta/Otrunk1.png",
      door_front_left_closed: "s05/estado_planta/OLF0.png",
      door_front_left_open: "s05/estado_planta/OLF1.png",
      door_front_right_closed: "s05/estado_planta/ORF0.png",
      door_front_right_open: "s05/estado_planta/ORF1.png",
      door_rear_left_closed: "s05/estado_planta/OLB0.png",
      door_rear_left_open: "s05/estado_planta/OLB1.png",
      door_rear_right_closed: "s05/estado_planta/ORB0.png",
      door_rear_right_open: "s05/estado_planta/ORB1.png",
      window_front_left_open: "s05/estado_planta/OwindowsLF1.png",
      window_front_right_open: "s05/estado_planta/OwindowsRF1.png",
      window_rear_left_open: "s05/estado_planta/OwindowsLB1.png",
      window_rear_right_open: "s05/estado_planta/OwindowsRB1.png",
      door_window_front_left_open: "s05/estado_planta/OopenDoor-windowsLF1.png",
      door_window_front_right_open: "s05/estado_planta/OopenDoor-windowsRF1.png",
      door_window_rear_left_open: "s05/estado_planta/OopenDoor-windowsLB1.png",
      door_window_rear_right_open: "s05/estado_planta/OopenDoor-windowsRB1.png",
      lights_on: "s05/estado_planta/OlowBeam1.png",
    },
  },
  climate: {
    base: "s05/aa/carAc.png",
    layers: { climate_on: "s05/aa/carAcOpen.png" },
  },
  charging: {
    base: "s05/bateria/carBattery.png",
    layers: {
      plugged: "s05/bateria/chargingLineOff.png",
      charging: "s05/bateria/chargingLineOn.png",
    },
  },
};

// Entity keys (translation_key) the panel looks up, grouped by platform.
// Optional keys are skipped when the vehicle does not expose them.
const PANEL_KEYS = {
  sensor: {
    battery: "battery_level",
    range: "remaining_range",
    odometer: "total_odometer",
    charge_current: "charge_current",
    remaining_time: "remaining_charge_time",
    inside_temperature: "inside_temperature",
    tire_front_left: "tire_pressure_front_left",
    tire_front_right: "tire_pressure_front_right",
    tire_rear_left: "tire_pressure_rear_left",
    tire_rear_right: "tire_pressure_rear_right",
  },
  binary_sensor: {
    charging: "charging",
    charger_plugged: "charger_plugged",
    engine: "engine",
    doors_locked: "doors_lock_state",
    any_door_open: "any_door_open",
    door_front_left: "door_front_left",
    door_front_right: "door_front_right",
    door_rear_left: "door_rear_left",
    door_rear_right: "door_rear_right",
    window_front_left: "window_open_front_left",
    window_front_right: "window_open_front_right",
    window_rear_left: "window_open_rear_left",
    window_rear_right: "window_open_rear_right",
    trunk: "trunk",
    hood: "hood",
    low_beam: "low_beam",
    high_beam: "high_beam",
    position_lamp: "position_lamp",
    tire_alarm_front_left: "tire_alarm_front_left",
    tire_alarm_front_right: "tire_alarm_front_right",
    tire_alarm_rear_left: "tire_alarm_rear_left",
    tire_alarm_rear_right: "tire_alarm_rear_right",
    rear_fog_lamp: "rear_fog_lamp",
  },
  lock: { doors: "doors" },
  cover: { windows: "windows", trunk: "trunk" },
  climate: { cabin: "cabin_climate" },
  number: {
    seat_heating_front_left: "seat_heating_level_front_left",
    seat_heating_front_right: "seat_heating_level_front_right",
    seat_ventilation_front_left: "seat_ventilation_level_front_left",
    seat_ventilation_front_right: "seat_ventilation_level_front_right",
  },
  switch: { steering_wheel_heating: "steering_wheel_heating" },
  button: {
    refresh: "refresh_vehicle_data",
    flash_lights: "flash_lights",
    honk_horn: "honk_horn",
  },
  image: { vehicle_image: "vehicle_image" },
};

// ---- 20_textos.js ----
// GENERATED FILE - do not edit; run scripts/build_panel.py after changing src/ or texts/.

// UI strings, embedded from frontend/panel/texts/*.json.
const PANEL_TEXTS = {
  "en": {
    "alarm": "Alarm",
    "battery": "Battery",
    "card_description": "Vehicle status, picture and essential controls for a Deepal car",
    "card_name": "Deepal vehicle",
    "charge_current": "Current",
    "charge_session_current": "Current session",
    "charge_session_last": "Last session",
    "charging": "Charging",
    "climate": "Climate",
    "climate_off": "Turn off",
    "climate_on": "Turn on",
    "close": "Close",
    "close_trunk": "Close trunk",
    "close_windows": "Close windows",
    "closed": "Closed",
    "command_failed": "The command failed",
    "doors": "Doors",
    "engine": "Engine",
    "flash_lights": "Flash",
    "front_left": "Front left",
    "front_right": "Front right",
    "high_beam": "High beam",
    "honk_horn": "Horn",
    "hood": "Hood",
    "inside_temperature": "Inside",
    "level": "Level",
    "lights": "Lights",
    "lock": "Lock",
    "lock_doors": "Lock doors",
    "locked": "Locked",
    "low_beam": "Low beam",
    "no_vehicle": "No vehicle configured yet",
    "not_plugged": "Cable unplugged",
    "odometer": "Odometer",
    "off": "Off",
    "on": "On",
    "open": "Open",
    "open_trunk": "Open trunk",
    "open_windows": "Open windows",
    "plugged": "Cable plugged",
    "position_lamp": "Position",
    "range": "Range",
    "rear_left": "Rear left",
    "rear_right": "Rear right",
    "refresh": "Refresh",
    "refresh_hint": "Request fresh data from the vehicle",
    "remaining_time": "Time left",
    "seat_heating": "Heating",
    "seat_ventilation": "Ventilation",
    "seats": "Seats",
    "session_end_level": "End level",
    "session_ended": "Ended",
    "session_start_level": "Start level",
    "session_started": "Started",
    "steering_wheel": "Steering wheel",
    "tab_charging": "Charging",
    "tab_climate": "Climate",
    "tab_status": "Status",
    "target_temperature": "Target temperature",
    "tires": "Tires",
    "title": "Deepal",
    "trunk": "Trunk",
    "unavailable": "Unavailable",
    "unknown": "Unknown",
    "unlock": "Unlock",
    "unlock_doors": "Unlock doors",
    "unlocked": "Unlocked",
    "vehicle": "Vehicle",
    "windows": "Windows",
  },
  "es": {
    "alarm": "Alarma",
    "battery": "Batería",
    "card_description": "Estado, imagen y controles esenciales de un coche Deepal",
    "card_name": "Vehículo Deepal",
    "charge_current": "Corriente",
    "charge_session_current": "Carga en curso",
    "charge_session_last": "Última carga",
    "charging": "Cargando",
    "climate": "Climatización",
    "climate_off": "Apagar",
    "climate_on": "Encender",
    "close": "Cerrar",
    "close_trunk": "Cerrar maletero",
    "close_windows": "Subir ventanillas",
    "closed": "Cerrado",
    "command_failed": "El comando ha fallado",
    "doors": "Puertas",
    "engine": "Motor",
    "flash_lights": "Destello",
    "front_left": "Del. izq.",
    "front_right": "Del. der.",
    "high_beam": "Largas",
    "honk_horn": "Claxon",
    "hood": "Capó",
    "inside_temperature": "Interior",
    "level": "Nivel",
    "lights": "Luces",
    "lock": "Cerrar",
    "lock_doors": "Cerrar puertas",
    "locked": "Cerrado",
    "low_beam": "Cortas",
    "no_vehicle": "Aún no hay ningún vehículo configurado",
    "not_plugged": "Cable desconectado",
    "odometer": "Kilómetros",
    "off": "Apagado",
    "on": "Encendido",
    "open": "Abrir",
    "open_trunk": "Abrir maletero",
    "open_windows": "Bajar ventanillas",
    "plugged": "Cable conectado",
    "position_lamp": "Posición",
    "range": "Autonomía",
    "rear_left": "Tras. izq.",
    "rear_right": "Tras. der.",
    "refresh": "Actualizar",
    "refresh_hint": "Pide datos nuevos al coche",
    "remaining_time": "Tiempo restante",
    "seat_heating": "Calefacción",
    "seat_ventilation": "Ventilación",
    "seats": "Asientos",
    "session_end_level": "Nivel final",
    "session_ended": "Fin",
    "session_start_level": "Nivel inicial",
    "session_started": "Inicio",
    "steering_wheel": "Volante",
    "tab_charging": "Carga",
    "tab_climate": "Clima",
    "tab_status": "Estado",
    "target_temperature": "Temperatura",
    "tires": "Neumáticos",
    "title": "Deepal",
    "trunk": "Maletero",
    "unavailable": "No disponible",
    "unknown": "Desconocido",
    "unlock": "Abrir",
    "unlock_doors": "Abrir puertas",
    "unlocked": "Abierto",
    "vehicle": "Vehículo",
    "windows": "Ventanillas",
  },
};

// ---- 30_estilos.js ----
// Panel styles. Everything is scoped to the shadow root and built on Home
// Assistant theme variables so the panel follows light and dark themes.

const PANEL_CSS = `
:host {
  display: block;
  height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}
.panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: 12px 16px 32px;
  overflow-y: auto;
}
.header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.header h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.spacer { flex: 1; }
.vehicle-select {
  display: flex;
  align-items: center;
  gap: 6px;
}
.vehicle-select select {
  background: var(--card-background-color);
  color: var(--primary-text-color);
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 14px;
}
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: var(--card-background-color);
  color: var(--primary-text-color);
  cursor: pointer;
  touch-action: manipulation;
}
.icon-button:hover { background: var(--secondary-background-color); }
.tabs {
  display: flex;
  border-bottom: 1px solid var(--divider-color);
}
.tab {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: none;
  color: var(--secondary-text-color);
  font-size: 14px;
  padding: 10px 8px;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  touch-action: manipulation;
}
.tab[aria-selected="true"] {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}
.view { display: flex; flex-direction: column; gap: 12px; }
.card {
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  box-shadow: var(--ha-card-box-shadow, none);
  border: 1px solid var(--divider-color);
  padding: 12px 16px;
}
.card h2 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--secondary-text-color);
}
.card-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px;
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  color: var(--primary-text-color);
}
.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
}
.stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--ha-card-border-radius, 12px);
}
.stage-status { aspect-ratio: 1 / 1; }
.stage-climate { aspect-ratio: 1125 / 642; }
.stage-charging { aspect-ratio: 3 / 2; }
.stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 13px;
  background: var(--secondary-background-color);
  color: var(--primary-text-color);
}
.chip.on { background: var(--primary-color); color: var(--text-primary-color, white); }
.chip.warn { background: var(--error-color); color: var(--text-primary-color, white); }
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric .label { font-size: 12px; color: var(--secondary-text-color); }
.metric .value { font-size: 18px; font-weight: 600; }
.tires {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.tire {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--secondary-background-color);
}
.tire.alarm { background: var(--error-color); color: var(--text-primary-color, white); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 10px;
  background: var(--primary-color);
  color: var(--text-primary-color, white);
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
  touch-action: manipulation;
}
.action.secondary {
  background: var(--secondary-background-color);
  color: var(--primary-text-color);
}
.action:disabled { opacity: 0.5; cursor: default; }
.stepper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stepper button {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--divider-color);
  background: var(--card-background-color);
  color: var(--primary-text-color);
  cursor: pointer;
}
.controls-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control .row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.temperature {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}
.temperature .value { font-size: 28px; font-weight: 600; }
.empty {
  padding: 24px;
  text-align: center;
  color: var(--secondary-text-color);
}
.error {
  background: var(--error-color);
  color: var(--text-primary-color, white);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
}
.session {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.session .metric .value { font-size: 15px; }
.row { display: flex; align-items: center; gap: 8px; }
.row.actions { justify-content: center; flex-wrap: wrap; }
.action-chip { border: none; cursor: pointer; }
.vehicle-photo {
  display: block;
  width: 100%;
  border-radius: var(--ha-card-border-radius, 12px);
}
.stepper .value { min-width: 28px; text-align: center; font-weight: 600; }
@media (max-width: 600px) {
  .panel { padding: 8px 8px 24px; }
  .grid, .controls-grid { grid-template-columns: 1fr; }
  .tab { padding: 8px; font-size: 13px; }
}
:host([narrow]) .grid,
:host([narrow]) .controls-grid {
  grid-template-columns: 1fr;
}
`;

const PANEL_ICONS = {
  refresh: "mdi:refresh",
  lock: "mdi:lock",
  unlock: "mdi:lock-open-variant",
  flash: "mdi:car-light-alert",
  horn: "mdi:bullhorn",
  window: "mdi:window-closed-variant",
  trunk: "mdi:car-back",
  car: "mdi:car",
  climate: "mdi:air-conditioner",
  charging: "mdi:battery-charging",
  battery: "mdi:car-battery",
  tire: "mdi:tire",
  seat_heating: "mdi:car-seat-heater",
  seat_ventilation: "mdi:car-seat-cooler",
  steering: "mdi:steering",
};

// ---- 40_helpers.js ----
// Shared helpers: language, texts, entity discovery and formatting.

const PANEL_DOMAINS = Object.keys(PANEL_KEYS);

/** Resolve the Home Assistant UI language to one of the shipped texts. */
function panelLanguage(hass) {
  const raw =
    (hass && hass.locale && hass.locale.language) ||
    (hass && hass.language) ||
    PANEL_BASE_LANGUAGE;
  const base = String(raw).toLowerCase().split("-")[0];
  return PANEL_BORROWED_LANGUAGES[base] || base;
}

/** Translate a key for the given language, with English fallback. */
function translate(language, key, values) {
  const texts = PANEL_TEXTS[language] || PANEL_TEXTS[PANEL_BASE_LANGUAGE];
  let text = key in texts ? texts[key] : key;
  if (values) {
    for (const [name, value] of Object.entries(values)) {
      text = text.split(`{${name}}`).join(value);
    }
  }
  return text;
}

/** Absolute URL of a bundled asset, versioned for cache busting. */
function assetUrl(path) {
  return `${PANEL_ASSETS_URL}/${path}?v=${PANEL_VERSION}`;
}

/** Escape a value before inserting it into generated HTML. */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/**
 * Group the integration entities into vehicles by device id.
 *
 * Reads the frontend registries only: `hass.entities` carries the platform,
 * device and translation key of every entity, and `hass.devices` the vehicle
 * names. No entity id is assumed, so the panel works on any installation.
 */
function discoverVehicles(hass) {
  const vehicles = new Map();
  const entities = (hass && hass.entities) || {};
  for (const entry of Object.values(entities)) {
    if (entry.platform !== "deepal") continue;
    if (!entry.device_id || !entry.translation_key) continue;
    if (entry.disabled_by || entry.hidden_by) continue;
    const domain = String(entry.entity_id).split(".")[0];
    if (!PANEL_DOMAINS.includes(domain)) continue;
    let vehicle = vehicles.get(entry.device_id);
    if (!vehicle) {
      const device = ((hass && hass.devices) || {})[entry.device_id] || {};
      vehicle = {
        deviceId: entry.device_id,
        name: device.name_by_user || device.name || "Deepal",
        model: device.model || "",
        entities: {},
      };
      vehicles.set(entry.device_id, vehicle);
    }
    vehicle.entities[domain] = vehicle.entities[domain] || {};
    vehicle.entities[domain][entry.translation_key] = entry.entity_id;
  }
  return [...vehicles.values()].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

/**
 * Entity id of a vehicle key, or undefined when the vehicle lacks it.
 *
 * Views use the friendly keys of PANEL_KEYS; a raw translation key also
 * resolves because the lookup falls back to the given name.
 */
function entityFor(vehicle, domain, key) {
  const ids = vehicle.entities[domain];
  if (!ids) return undefined;
  const translationKey =
    (PANEL_KEYS[domain] && PANEL_KEYS[domain][key]) || key;
  return ids[translationKey];
}

/** Entity state, or null for unknown/unavailable/missing states. */
function stateFor(hass, entityId) {
  if (!entityId) return null;
  const state = hass.states[entityId];
  if (!state || state.state === "unknown" || state.state === "unavailable") {
    return null;
  }
  return state;
}

/** True when the entity exists and reports "on". */
function isOn(hass, entityId) {
  const state = stateFor(hass, entityId);
  return state !== null && state.state === "on";
}

/** Localized entity value, or null when there is nothing to show. */
function formatState(hass, entityId) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  if (hass.formatEntityState) {
    return hass.formatEntityState(state);
  }
  const unit = state.attributes.unit_of_measurement;
  return unit ? `${state.state} ${unit}` : state.state;
}

/** Numeric attribute of an entity, or null. */
function attributeFor(hass, entityId, name) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  const value = state.attributes[name];
  return value === undefined ? null : value;
}

/** Localized date and time for an ISO timestamp, falling back to the raw value. */
function formatDateTime(language, value) {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(language, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch (error) {
    return String(value);
  }
}

// ---- 45_vehiculo.js ----
// Shared vehicle rendering used by the sidebar panel and the dashboard card:
// the layered status picture, the state chips and the pointer-freeze helper
// that keeps clicks reliable while states update.

/**
 * Never replace the DOM while a pointer is pressed inside the element: a
 * state update between pointerdown and pointerup would detach the button
 * under the finger and swallow the click. Updates are deferred to release.
 */
function installPointerFreeze(element) {
  element._pointerDown = false;
  element._renderPending = false;
  element.shadowRoot.addEventListener("pointerdown", () => {
    element._pointerDown = true;
  });
  element._releasePointer = () => {
    if (!element._pointerDown) return;
    element._pointerDown = false;
    if (element._renderPending) {
      element._renderPending = false;
      element._render();
    }
  };
  window.addEventListener("pointerup", element._releasePointer, true);
  window.addEventListener("pointercancel", element._releasePointer, true);
  element._removePointerFreeze = () => {
    window.removeEventListener("pointerup", element._releasePointer, true);
    window.removeEventListener("pointercancel", element._releasePointer, true);
  };
}

/** Language of a standalone element (no hass yet), for the card picker. */
function browserLanguage() {
  const raw =
    (typeof document !== "undefined" &&
      document.documentElement &&
      document.documentElement.lang) ||
    (typeof navigator !== "undefined" && navigator.language) ||
    PANEL_BASE_LANGUAGE;
  return panelLanguage({ locale: { language: raw } });
}

/**
 * Layered S05 picture, or the vehicle image entity for other models.
 *
 * Every piece is drawn, closed or open: the base image (Ocar1) is the bare
 * body and the doors, hood and trunk come as separate layers.
 */
function vehicleStageHtml(hass, vehicle) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const model = `${vehicle.model || ""} ${vehicle.name || ""}`;

  if (/s05/i.test(model)) {
    const layers = [
      isOn(hass, entity("binary_sensor", "hood"))
        ? "hood_open"
        : "hood_closed",
      isOn(hass, entity("binary_sensor", "trunk"))
        ? "trunk_open"
        : "trunk_closed",
    ];
    const part = (doorKey, windowKey, position) => {
      const doorOpen = isOn(hass, entity("binary_sensor", doorKey));
      const windowOpen = isOn(hass, entity("binary_sensor", windowKey));
      if (doorOpen && windowOpen) layers.push(`door_window_${position}_open`);
      else if (doorOpen) layers.push(`door_${position}_open`);
      else if (windowOpen) layers.push(`window_${position}_open`);
      else layers.push(`door_${position}_closed`);
    };
    part("door_front_left", "window_front_left", "front_left");
    part("door_front_right", "window_front_right", "front_right");
    part("door_rear_left", "window_rear_left", "rear_left");
    part("door_rear_right", "window_rear_right", "rear_right");
    if (
      ["low_beam", "high_beam", "position_lamp"].some((key) =>
        isOn(hass, entity("binary_sensor", key)),
      )
    ) {
      layers.push("lights_on");
    }
    const layout = PANEL_S05_LAYOUT.status;
    return `<div class="stage stage-status">
      <img src="${assetUrl(layout.base)}" alt="">
      ${layers
        .map((name) => `<img src="${assetUrl(layout.layers[name])}" alt="">`)
        .join("")}
    </div>`;
  }

  const imageId = entity("image", "vehicle_image");
  const picture = imageId ? attributeFor(hass, imageId, "entity_picture") : null;
  if (!picture) return "";
  return `<div class="card"><img class="vehicle-photo" src="${escapeHtml(picture)}" alt=""></div>`;
}

/** State chips shared by the panel status view and the dashboard card. */
function vehicleChipsHtml(hass, vehicle, t) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const chips = [];
  const chip = (label, stateText, active, warn = false) =>
    `<span class="chip ${active ? (warn ? "warn" : "on") : ""}">${escapeHtml(label)}: ${escapeHtml(stateText)}</span>`;
  const chipFor = (labelKey, active) =>
    chip(t(labelKey), active ? t("open") : t("closed"), active, active);

  const lockId = entity("lock", "doors");
  const lockedBinary = entity("binary_sensor", "doors_locked");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  const locked = lockState ? lockState.state === "locked" : null;
  if (lockId && locked !== null) {
    chips.push(
      `<span class="chip ${locked ? "" : "on"}">
        <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
        ${escapeHtml(locked ? t("locked") : t("unlocked"))}
      </span>`,
    );
  } else if (lockedBinary) {
    const unlocked = isOn(hass, lockedBinary);
    chips.push(
      chip(t("doors"), unlocked ? t("unlocked") : t("locked"), unlocked, unlocked),
    );
  }

  const anyDoorOpen = [
    "door_front_left",
    "door_front_right",
    "door_rear_left",
    "door_rear_right",
  ].some((key) => isOn(hass, entity("binary_sensor", key)));
  chips.push(chipFor("doors", anyDoorOpen));

  const anyWindowOpen = [
    "window_front_left",
    "window_front_right",
    "window_rear_left",
    "window_rear_right",
  ].some((key) => isOn(hass, entity("binary_sensor", key)));
  chips.push(chipFor("windows", anyWindowOpen));

  chips.push(chipFor("trunk", isOn(hass, entity("binary_sensor", "trunk"))));
  chips.push(chipFor("hood", isOn(hass, entity("binary_sensor", "hood"))));

  const lightKeys = ["low_beam", "high_beam", "position_lamp"].filter((key) =>
    isOn(hass, entity("binary_sensor", key)),
  );
  chips.push(
    chip(
      t("lights"),
      lightKeys.length ? lightKeys.map((key) => t(key)).join(", ") : t("off"),
      lightKeys.length > 0,
    ),
  );

  const engineOn = isOn(hass, entity("binary_sensor", "engine"));
  chips.push(chip(t("engine"), engineOn ? t("on") : t("off"), engineOn));

  return chips.join("");
}

// ---- 50_panel.js ----
// Panel shell: header, vehicle selector, tabs, action dispatch and error
// feedback. The three views live in 60_estado.js, 61_clima.js and
// 62_carga.js and hang off the prototype.

class DeepalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "status";
    this._deviceId = null;
    this._error = "";
    this._vehicles = [];
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

  _syncVehicles() {
    this._vehicles = discoverVehicles(this._hass || {});
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
        const value = Math.min(
          max,
          Math.max(min, Number(state.state) + Number(target.dataset.delta || 0)),
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
    const target = event.target.closest("[data-action='select-vehicle']");
    if (!target) return;
    this._deviceId = target.value;
    this._render();
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
    } catch (error) {
      // A render error must never leave the panel stuck on the old view.
      console.error("Deepal panel render failed", error);
      this.shadowRoot.innerHTML = `
        <style>${PANEL_CSS}</style>
        <div class="panel">
          <div class="error">${escapeHtml(
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
    const tabs = this._tabsHtml();
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
        <header class="header">
          <h1><ha-icon icon="mdi:car-electric"></ha-icon>${escapeHtml(this._t("title"))}</h1>
          ${selector}
          <div class="spacer"></div>
          ${
            refresh
              ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>`
              : ""
          }
        </header>
        ${this._error ? `<div class="error">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `<nav class="tabs" role="tablist">${tabs}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }

  _renderView(vehicle) {
    if (this._tab === "climate") return this._renderClimate(vehicle);
    if (this._tab === "charging") return this._renderCharging(vehicle);
    return this._renderStatus(vehicle);
  }

  _tabsHtml() {
    return PANEL_TABS.map(
      ([key, icon]) => `
      <button class="tab" role="tab" aria-selected="${this._tab === key}" data-action="tab" data-tab="${key}">
        <ha-icon icon="${icon}"></ha-icon>
        <span>${escapeHtml(this._t(`tab_${key}`))}</span>
      </button>`,
    ).join("");
  }
}

// ---- 60_estado.js ----
// Status view: the layered S05 picture (or the vehicle image fallback), the
// state chips, the tire pressures and the essential controls.

DeepalPanel.prototype._renderStatus = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const metric = (labelKey, value) => `
    <div class="card"><div class="metric">
      <span class="label">${escapeHtml(t(labelKey))}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div></div>`;

  const metrics = [
    metric("battery", formatState(hass, entity("sensor", "battery"))),
    metric("range", formatState(hass, entity("sensor", "range"))),
    metric("odometer", formatState(hass, entity("sensor", "odometer"))),
    metric(
      "charging",
      isOn(hass, entity("binary_sensor", "charging")) ? t("on") : t("off"),
    ),
    metric(
      "plugged",
      isOn(hass, entity("binary_sensor", "charger_plugged"))
        ? t("plugged")
        : t("not_plugged"),
    ),
  ];

  const chips = vehicleChipsHtml(hass, vehicle, t);

  const tire = (key, alarmKey, labelKey) => {
    const id = entity("sensor", key);
    if (!id) return "";
    const alarm = isOn(hass, entity("binary_sensor", alarmKey));
    const value = formatState(hass, id) || "—";
    return `<div class="tire ${alarm ? "alarm" : ""}">
      <span>${escapeHtml(t(labelKey))}</span>
      <span><ha-icon icon="${PANEL_ICONS.tire}"></ha-icon> ${escapeHtml(value)}</span>
    </div>`;
  };
  const tires = [
    tire("tire_front_left", "tire_alarm_front_left", "front_left"),
    tire("tire_front_right", "tire_alarm_front_right", "front_right"),
    tire("tire_rear_left", "tire_alarm_rear_left", "rear_left"),
    tire("tire_rear_right", "tire_alarm_rear_right", "rear_right"),
  ].join("");

  const actions = [];
  const lockId = entity("lock", "doors");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  const locked = lockState ? lockState.state === "locked" : null;
  if (lockId && locked !== null) {
    actions.push(
      `<button class="action secondary" data-action="lock-toggle">
        <ha-icon icon="${locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock}"></ha-icon>
        ${escapeHtml(locked ? t("unlock_doors") : t("lock_doors"))}
      </button>`,
    );
  }
  const windowsId = entity("cover", "windows");
  if (windowsId) {
    const open = stateFor(hass, windowsId)?.state === "open";
    actions.push(
      `<button class="action secondary" data-action="cover-toggle" data-key="windows">
        <ha-icon icon="${PANEL_ICONS.window}"></ha-icon>
        ${escapeHtml(open ? t("close_windows") : t("open_windows"))}
      </button>`,
    );
  }
  const trunkId = entity("cover", "trunk");
  if (trunkId) {
    const open = stateFor(hass, trunkId)?.state === "open";
    actions.push(
      `<button class="action secondary" data-action="cover-toggle" data-key="trunk">
        <ha-icon icon="${PANEL_ICONS.trunk}"></ha-icon>
        ${escapeHtml(open ? t("close_trunk") : t("open_trunk"))}
      </button>`,
    );
  }
  if (entity("button", "flash_lights")) {
    actions.push(
      `<button class="action secondary" data-action="press" data-key="flash_lights">
        <ha-icon icon="${PANEL_ICONS.flash}"></ha-icon>${escapeHtml(t("flash_lights"))}
      </button>`,
    );
  }
  if (entity("button", "honk_horn")) {
    actions.push(
      `<button class="action secondary" data-action="press" data-key="honk_horn">
        <ha-icon icon="${PANEL_ICONS.horn}"></ha-icon>${escapeHtml(t("honk_horn"))}
      </button>`,
    );
  }

  return `
    ${vehicleStageHtml(hass, vehicle)}
    <div class="chips">${chips}</div>
    <div class="grid">${metrics.join("")}</div>
    ${
      tires
        ? `<div class="card"><h2>${escapeHtml(t("tires"))}</h2><div class="tires">${tires}</div></div>`
        : ""
    }
    ${actions.length ? `<div class="actions">${actions.join("")}</div>` : ""}`;
};

// ---- 61_clima.js ----
// Climate view: cabin climate control, seat heating/ventilation and the
// steering wheel. Every control hides itself when the vehicle does not
// expose its entity.

DeepalPanel.prototype._renderClimate = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const climateId = entity("climate", "cabin");
  const climateState = climateId ? stateFor(hass, climateId) : null;
  const climateOn = climateState ? climateState.state !== "off" : false;

  const layout = PANEL_S05_LAYOUT.climate;
  const stage = `<div class="stage stage-climate">
    <img src="${assetUrl(layout.base)}" alt="">
    ${climateOn ? `<img src="${assetUrl(layout.layers.climate_on)}" alt="">` : ""}
  </div>`;

  let climateCard = "";
  if (climateId) {
    const target = climateState?.attributes?.temperature;
    const inside = formatState(hass, entity("sensor", "inside_temperature"));
    climateCard = `<div class="card">
      <h2>${escapeHtml(t("climate"))}</h2>
      <div class="temperature stepper">
        <button data-action="temp-step" data-delta="-0.5">−</button>
        <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
        <button data-action="temp-step" data-delta="0.5">+</button>
      </div>
      <div class="row actions">
        <button class="action ${climateOn ? "secondary" : ""}" data-action="climate-mode" data-mode="heat_cool">
          ${escapeHtml(t("climate_on"))}
        </button>
        <button class="action ${climateOn ? "" : "secondary"}" data-action="climate-mode" data-mode="off">
          ${escapeHtml(t("climate_off"))}
        </button>
      </div>
      ${
        inside
          ? `<div class="metric"><span class="label">${escapeHtml(t("inside_temperature"))}</span><span class="value">${escapeHtml(inside)}</span></div>`
          : ""
      }
    </div>`;
  }

  const seatControl = (key, label) => {
    const id = entity("number", key);
    if (!id) return "";
    const state = stateFor(hass, id);
    return `<div class="control">
      <span class="label">${escapeHtml(label)}</span>
      <div class="stepper">
        <button data-action="number-step" data-key="${key}" data-delta="-1">−</button>
        <span class="value">${escapeHtml(state ? state.state : "—")}</span>
        <button data-action="number-step" data-key="${key}" data-delta="1">+</button>
      </div>
    </div>`;
  };
  const seatControls = [
    seatControl(
      "seat_heating_front_left",
      `${t("seat_heating")} · ${t("front_left")}`,
    ),
    seatControl(
      "seat_heating_front_right",
      `${t("seat_heating")} · ${t("front_right")}`,
    ),
    seatControl(
      "seat_ventilation_front_left",
      `${t("seat_ventilation")} · ${t("front_left")}`,
    ),
    seatControl(
      "seat_ventilation_front_right",
      `${t("seat_ventilation")} · ${t("front_right")}`,
    ),
  ].join("");

  const steeringId = entity("switch", "steering_wheel_heating");
  const steeringOn = steeringId ? isOn(hass, steeringId) : false;
  const steeringControl = steeringId
    ? `<button class="action ${steeringOn ? "" : "secondary"}" data-action="toggle-switch" data-key="steering_wheel_heating">
        <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
        ${escapeHtml(t("steering_wheel"))}: ${escapeHtml(steeringOn ? t("on") : t("off"))}
      </button>`
    : "";

  const seatsCard =
    seatControls || steeringControl
      ? `<div class="card">
          <h2>${escapeHtml(t("seats"))}</h2>
          <div class="controls-grid">${seatControls}</div>
          ${steeringControl ? `<div class="row actions">${steeringControl}</div>` : ""}
        </div>`
      : "";

  if (!climateCard && !seatsCard) {
    return `<div class="empty">${escapeHtml(t("unavailable"))}</div>`;
  }
  return `${stage}${climateCard}${seatsCard}`;
};

// ---- 62_carga.js ----
// Charging view: battery and session state, the charging picture and the
// session summaries the charging sensor exposes as attributes.

DeepalPanel.prototype._renderCharging = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const charging = isOn(hass, entity("binary_sensor", "charging"));
  const plugged = isOn(hass, entity("binary_sensor", "charger_plugged"));
  const layout = PANEL_S05_LAYOUT.charging;
  const stage = `<div class="stage stage-charging">
    <img src="${assetUrl(layout.base)}" alt="">
    ${
      plugged
        ? `<img src="${assetUrl(charging ? layout.layers.charging : layout.layers.plugged)}" alt="">`
        : ""
    }
  </div>`;

  const metric = (labelKey, value) => `
    <div class="card"><div class="metric">
      <span class="label">${escapeHtml(t(labelKey))}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div></div>`;
  const metrics = [
    metric("battery", formatState(hass, entity("sensor", "battery"))),
    metric("charging", charging ? t("on") : t("off")),
    metric("plugged", plugged ? t("plugged") : t("not_plugged")),
    metric(
      "charge_current",
      formatState(hass, entity("sensor", "charge_current")),
    ),
    metric(
      "remaining_time",
      formatState(hass, entity("sensor", "remaining_time")),
    ),
  ];

  const chargingId = entity("binary_sensor", "charging");
  const current = chargingId
    ? attributeFor(hass, chargingId, "current_charge")
    : null;
  const last = chargingId ? attributeFor(hass, chargingId, "last_charge") : null;
  const session = (labelKey, data) => {
    if (!data) return "";
    const level = (value) => (value == null ? "—" : `${value} %`);
    const rows = [];
    if (data.start) {
      rows.push([
        t("session_started"),
        formatDateTime(this._language, data.start),
      ]);
    }
    if (data.end) {
      rows.push([t("session_ended"), formatDateTime(this._language, data.end)]);
    }
    if (data.start_level != null) {
      rows.push([t("session_start_level"), level(data.start_level)]);
    }
    if (data.end_level != null) {
      rows.push([t("session_end_level"), level(data.end_level)]);
    }
    if (!rows.length) return "";
    return `<div class="card"><h2>${escapeHtml(t(labelKey))}</h2><div class="session">
      ${rows
        .map(
          ([label, value]) =>
            `<div class="metric"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></div>`,
        )
        .join("")}
    </div></div>`;
  };

  return `${stage}
    <div class="grid">${metrics.join("")}</div>
    ${session("charge_session_current", current)}
    ${session("charge_session_last", last)}`;
};

// ---- 70_tarjeta.js ----
// Dashboard card: the sidebar panel inside a card. It is configured with one
// vehicle (device selector) and inherits the three views, the action handling
// and the update guards from the panel element.

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

  _renderHtml() {
    const vehicle = this._vehicle;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        <div class="card-title">
          <ha-icon icon="mdi:car-electric"></ha-icon>
          ${escapeHtml(vehicle ? vehicle.name : this._t("title"))}
          <div class="spacer"></div>
          ${
            refresh
              ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>`
              : ""
          }
        </div>
        ${this._error ? `<div class="error">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `<nav class="tabs" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}

// ---- 90_registro.js ----
// Register the frontend elements with Home Assistant.

if (!customElements.get(PANEL_TAG)) {
  customElements.define(PANEL_TAG, DeepalPanel);
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, DeepalCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TAG,
    name: translate(browserLanguage(), "card_name"),
    description: translate(browserLanguage(), "card_description"),
    // No live preview in the picker: the card renders the full panel, and a
    // preview can race the module load and fail with "custom element not
    // found". The card is added from the list and configured afterwards.
    preview: false,
    documentationURL: "https://github.com/Sunek0/ha-deepal-alternative",
  });
}
