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
 * Layered picture of the vehicle's model profile, or the vehicle image entity
 * when the model has no artwork.
 *
 * Every piece is drawn, closed or open: the base image (Ocar1) is the bare
 * body and the doors, hood and trunk come as separate layers.
 */
function vehicleStageHtml(hass, vehicle) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const layout = layoutFor(vehicle);

  if (layout && layout.status) {
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
    const stage = layout.status;
    return `<div class="stage stage-status">
      <img src="${assetUrl(stage.base)}" alt="">
      ${layers
        .map((name) => `<img src="${assetUrl(stage.layers[name])}" alt="">`)
        .join("")}
    </div>`;
  }

  const imageId = entity("image", "vehicle_image");
  const picture = imageId ? attributeFor(hass, imageId, "entity_picture") : null;
  if (!picture) return "";
  return vehiclePhotoHtml(hass, vehicle);
}

/** Vehicle image entity as a picture ("" when the image is unavailable). */
function vehiclePhotoHtml(hass, vehicle) {
  const imageId = entityFor(vehicle, "image", "vehicle_image");
  const picture = imageId
    ? attributeFor(hass, imageId, "entity_picture")
    : null;
  if (!picture) return "";
  return `<img class="vehicle-photo" src="${escapeHtml(picture)}" alt="">`;
}

/** Profile hero picture (its 3/4 view), or "" when the model has none. */
function vehicleHeroHtml(vehicle) {
  const hero = layoutFor(vehicle)?.hero;
  return hero ? `<img class="vehicle-photo" src="${assetUrl(hero)}" alt="">` : "";
}

/**
 * State chips shared by the panel status view and the dashboard cards.
 * `options.lock` puts the general closure (padlock) first — the complete card
 * uses it because its vitals carry no lock state; `options.openingsOnly` keeps
 * just the door, window, trunk and hood chips for the compact card.
 */
function vehicleChipsHtml(hass, vehicle, t, options = {}) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const chips = [];
  const chip = (label, stateText, active, warn = false) =>
    `<span class="chip ${active ? (warn ? "warn" : "on") : ""}">${escapeHtml(label)}: ${escapeHtml(stateText)}</span>`;
  const chipFor = (labelKey, active) =>
    chip(t(labelKey), active ? t("open") : t("closed"), active, active);

  if (options.lock) {
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null) {
      chips.push(
        `<span class="chip ${locked ? "" : "warn"}">
          <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
          ${escapeHtml(locked ? t("locked") : t("unlocked"))}
        </span>`,
      );
    }
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

  if (options.openingsOnly) return chips.join("");

  const lightKeys = [
    "low_beam",
    "high_beam",
    "position_lamp",
    "rear_fog_lamp",
  ].filter((key) => isOn(hass, entity("binary_sensor", key)));
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

/** Locked state shared by the chips, the vitals strip and the lock control. */
function lockStateFor(hass, vehicle) {
  const lockId = entityFor(vehicle, "lock", "doors");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  if (lockState) return lockState.state === "locked";
  const binaryId = entityFor(vehicle, "binary_sensor", "doors_locked");
  const binary = stateFor(hass, binaryId);
  if (binary) return binary.state !== "on";
  return null;
}

/** Translated charge status, falling back to the charging and plug flags. */
function chargeStatusText(hass, vehicle, t) {
  const statusId = entityFor(vehicle, "sensor", "charge_status");
  const status = stateFor(hass, statusId);
  if (status) return formatState(hass, statusId);
  if (isOn(hass, entityFor(vehicle, "binary_sensor", "charging"))) {
    return t("charging");
  }
  if (isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"))) {
    return t("plugged");
  }
  return t("not_plugged");
}

/**
 * Persistent vitals: battery (with a charging bolt), range, lock state and
 * data freshness. Rendered on every tab, above the segmented control. The
 * dashboard cards pass `{ lock: false }` to leave the lock state to their
 * own state chips.
 */
function vitalsHtml(hass, vehicle, t, options = {}) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const vital = (label, value, icon, cls = "", title = "") => `
    <div class="vital ${cls}" title="${escapeHtml(title)}">
      <ha-icon icon="${icon}"></ha-icon>
      <div class="vital-body">
        <span class="vital-label">${escapeHtml(label)}</span>
        <span class="vital-value">${escapeHtml(value ?? "—")}</span>
      </div>
    </div>`;
  const items = [];

  const charging = isOn(hass, entity("binary_sensor", "charging"));
  items.push(
    vital(
      t("battery"),
      formatState(hass, entity("sensor", "battery")),
      charging ? PANEL_ICONS.bolt : PANEL_ICONS.battery,
      charging ? "on" : "",
    ),
  );

  items.push(
    vital(
      t("range"),
      formatState(hass, entity("sensor", "range")),
      PANEL_ICONS.range,
    ),
  );

  const locked =
    options.lock === false ? null : lockStateFor(hass, vehicle);
  if (locked !== null) {
    items.push(
      vital(
        t("central_lock"),
        locked ? t("locked") : t("unlocked"),
        locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock,
        locked ? "" : "warn",
      ),
    );
  }

  const connectedId = entity("binary_sensor", "connected");
  const connectedState = stateFor(hass, connectedId);
  const connected = connectedState ? connectedState.state === "on" : null;
  const updatedId = entity("sensor", "updated");
  const updatedState = stateFor(hass, updatedId);
  const relative = updatedState
    ? formatRelativeTime(
        panelLanguage(hass),
        updatedState.state,
      )
    : null;
  const absolute = updatedState
    ? formatDateTime(panelLanguage(hass), updatedState.state)
    : "";
  items.push(
    vital(
      t("updated"),
      relative || (connected === true ? t("online") : null),
      connected === false ? PANEL_ICONS.cloud_off : PANEL_ICONS.cloud,
      connected === false ? "warn" : "",
      absolute,
    ),
  );

  return `<div class="vitals">${items.join("")}</div>`;
}

/** Active health warnings, in the panel's stable order. */
function activeWarnings(hass, vehicle) {
  return PANEL_WARNINGS.filter(([key]) =>
    isOn(hass, entityFor(vehicle, "binary_sensor", key)),
  );
}

/** Warnings section: rendered only while at least one warning is active. */
function warningsHtml(hass, vehicle, t) {
  const active = activeWarnings(hass, vehicle);
  if (!active.length) return "";
  return `<div class="section">
    <div class="section-head">
      <ha-icon icon="${PANEL_ICONS.alert}"></ha-icon>
      <span class="section-title">${escapeHtml(t("warnings"))}</span>
    </div>
    <div class="chips">${active
      .map(
        ([key, icon]) =>
          `<span class="chip warn"><ha-icon icon="${icon}"></ha-icon>${escapeHtml(t(key))}</span>`,
      )
      .join("")}</div>
  </div>`;
}
