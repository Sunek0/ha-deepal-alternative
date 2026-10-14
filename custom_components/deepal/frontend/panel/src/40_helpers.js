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
