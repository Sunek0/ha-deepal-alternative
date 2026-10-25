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

// Panel paths mapped to the directory names used by the official model ZIP.
const DYNAMIC_ASSET_DIRS = {
  estado_planta: "overlook",
  overlook: "overlook",
  side: "side",
  aa: "ac",
  bateria: "battery",
  asientos: "seat",
};
const DYNAMIC_ASSET_CATEGORIES = {
  estado_planta: "status",
  overlook: "status",
  side: "hero",
  aa: "climate",
  bateria: "charging",
  asientos: "seats",
};

/** Absolute URL of an asset, preferring the vehicle's official pack. */
function assetUrl(path, vehicle) {
  const parts = String(path).split("/");
  const directory = parts[1];
  const category = DYNAMIC_ASSET_CATEGORIES[directory];
  const assets = vehicle && vehicle.modelAssets;
  if (assets && category && assets.categories.includes(category)) {
    const mapped = DYNAMIC_ASSET_DIRS[directory];
    const relative = parts.slice(2).join("/");
    return `${assets.base}/${mapped}/${relative}?v=${assets.md5 || PANEL_VERSION}`;
  }
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

/** Upper-case alphanumerics of the vehicle model, for containment checks. */
function normalizeModelText(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

/** Whether the vehicle exposes the integration's fuel sensors. */
function hasFuelEntities(vehicle) {
  return PANEL_FUEL_ENTITY_KEYS.some((key) =>
    Boolean(entityFor(vehicle, "sensor", key)),
  );
}

/**
 * Model profile of a vehicle: S05 EV, S05 PHEV, S07 or generic.
 *
 * The registry model carries the integration's series name; inside the S05
 * family the fuel sensors (created only for fuel vehicles) split EV and PHEV,
 * the same discriminator the integration uses.
 */
function detectProfile(vehicle) {
  const model = normalizeModelText(vehicle && vehicle.model);
  if (PANEL_S05_MODEL_TOKENS.some((token) => model.includes(token))) {
    return hasFuelEntities(vehicle)
      ? PANEL_PROFILE_S05_PHEV
      : PANEL_PROFILE_S05_EV;
  }
  if (PANEL_S07_MODEL_TOKENS.some((token) => model.includes(token))) {
    return PANEL_PROFILE_S07;
  }
  return PANEL_PROFILE_GENERIC;
}

/**
 * Artwork and layout of a vehicle's model, or null when the model has none:
 * the vehicle image entity and the entity-driven sections are the fallback.
 */
function layoutFor(vehicle) {
  if (!vehicle) return null;
  if (vehicle.profile === PANEL_PROFILE_S07) return PANEL_MODEL_LAYOUTS.s07;
  if (
    vehicle.profile === PANEL_PROFILE_S05_EV ||
    vehicle.profile === PANEL_PROFILE_S05_PHEV
  ) {
    return PANEL_MODEL_LAYOUTS.s05;
  }
  return null;
}

/**
 * Group the integration entities into vehicles by device id.
 *
 * Reads the frontend registries only: `hass.entities` carries the platform,
 * device and translation key of every entity, and `hass.devices` the vehicle
 * names. No entity id is assumed, so the panel works on any installation.
 * Every vehicle also carries its detected model profile.
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
        profile: null,
        entities: {},
      };
      vehicles.set(entry.device_id, vehicle);
    }
    vehicle.entities[domain] = vehicle.entities[domain] || {};
    vehicle.entities[domain][entry.translation_key] = entry.entity_id;
  }
  for (const vehicle of vehicles.values()) {
    vehicle.profile = detectProfile(vehicle);
    const imageId = vehicle.entities.image?.vehicle_image;
    const imageState = imageId && hass.states ? hass.states[imageId] : null;
    const attributes = (imageState && imageState.attributes) || {};
    const base = attributes.model_assets_base;
    const categories = attributes.model_assets_categories;
    vehicle.modelAssets =
      base && Array.isArray(categories)
        ? {
            base,
            categories,
            md5: attributes.model_assets_md5 || "",
          }
        : null;
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

/** Relative age of an ISO timestamp ("3 min ago"), or null when unreadable. */
function formatRelativeTime(language, value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const steps = [
    { limit: 60, unit: "second" },
    { limit: 3600, unit: "minute", div: 60 },
    { limit: 86400, unit: "hour", div: 3600 },
    { limit: 2592000, unit: "day", div: 86400 },
    { limit: Infinity, unit: "month", div: 2592000 },
  ];
  for (const step of steps) {
    if (Math.abs(seconds) < step.limit) {
      const amount = step.div ? Math.round(seconds / step.div) : seconds;
      try {
        return new Intl.RelativeTimeFormat(language, {
          numeric: "auto",
          style: "short",
        }).format(-amount, step.unit);
      } catch (error) {
        return null;
      }
    }
  }
  return null;
}

/** Value of a time entity as HH:MM, or null when it has no usable state. */
function formatTime(hass, entityId) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  const raw = String(state.state);
  return /^\d{1,2}:\d{2}/.test(raw) ? raw.slice(0, 5).padStart(5, "0") : raw;
}
